"""Composite criterion extraction helpers.

The extractor schema now has a native `composite_groups` field while
the flat `criteria` list remains the compatibility view. These helpers
build the same parent/subcheck shape for fixer backfills and legacy
extractions that predate the native field.
"""

from __future__ import annotations

import re
from typing import Literal

from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    CompositeOperator,
    ConditionCriterion,
    EntityMention,
    ExtractedCriterion,
    FreeTextCriterion,
    MeasurementCriterion,
    MedicationCriterion,
)
from clinical_demo.matcher.concept_lookup import lookup_lab
from clinical_demo.terminology import (
    ReviewedMappingKind,
    get_reviewed_mapping_registry,
    get_reviewed_medication_class_registry,
)

_COMPOSITE_SPLITTERS: tuple[tuple[CompositeOperator, re.Pattern[str]], ...] = (
    ("any_of", re.compile(r"\s*;\s+OR\s+", re.IGNORECASE)),
    ("all_of", re.compile(r"\s*;\s+AND\s+", re.IGNORECASE)),
)
_MEASUREMENT_SUBCHECK_RE = re.compile(
    r"(?P<surface>.+?)\s*(?P<operator>>=|<=|>|<|=|≥|≤)\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|[A-Za-z][A-Za-z0-9/%.*^{}_-]*)?",
    re.IGNORECASE,
)
_PAREN_LIST_RE = re.compile(r"\([^)]*,[^)]*\)")
_INLINE_DISJUNCTION_RE = re.compile(r"\b(?:or|and/or)\b", re.IGNORECASE)
_TEMPORAL_QUALIFIER_RE = re.compile(
    r"\b(?:within|in the past|past|prior|last)\s+\d+\s+"
    r"(?:day|days|week|weeks|month|months|year|years)\b",
    re.IGNORECASE,
)
_TREATMENT_LIST_RE = re.compile(
    r"\btreatment with any of the following\b|\bany of the following drugs\b",
    re.IGNORECASE,
)
_PROMOTABLE_MENTION_TYPES = frozenset({"Condition", "Drug"})


def build_composite_criterion_groups(
    criterion: ExtractedCriterion,
    *,
    criterion_index: int,
) -> list[CompositeCriterionGroup]:
    """Build representational composite groups for explicit OR/AND bundles."""

    for operator, splitter in _COMPOSITE_SPLITTERS:
        parts = [_clean_composite_part(part) for part in splitter.split(criterion.source_text)]
        parts = [part for part in parts if part]
        if len(parts) < 2:
            continue
        group_id = f"criterion:{criterion_index}:group:001"
        return [
            CompositeCriterionGroup(
                group_id=group_id,
                operator=operator,
                parent_criterion_index=criterion_index,
                parent_source_text=criterion.source_text,
                subchecks=[
                    _composite_subcheck(
                        parent=criterion,
                        operator=operator,
                        group_id=group_id,
                        index=index,
                        source_text=part,
                    )
                    for index, part in enumerate(parts, start=1)
                ],
            )
        ]
    if criterion.kind == "free_text":
        return _mention_backed_composite_groups(criterion, criterion_index=criterion_index)
    return []


def _composite_subcheck(
    *,
    parent: ExtractedCriterion,
    operator: CompositeOperator,
    group_id: str,
    index: int,
    source_text: str,
) -> CompositeCriterionSubcheck:
    return CompositeCriterionSubcheck(
        subcheck_id=f"{group_id}:subcheck:{index:03d}",
        operator=operator,
        source_text=source_text,
        criterion=_subcheck_criterion(parent, source_text=source_text, operator=operator),
    )


def _subcheck_criterion(
    parent: ExtractedCriterion,
    *,
    source_text: str,
    operator: CompositeOperator,
) -> ExtractedCriterion:
    measurement = _measurement_subcheck(source_text)
    if measurement is not None:
        return ExtractedCriterion(
            kind="measurement_threshold",
            polarity=parent.polarity,
            source_text=source_text,
            negated=parent.negated,
            mood=parent.mood,
            age=None,
            sex=None,
            condition=None,
            medication=None,
            measurement=measurement,
            temporal_window=None,
            free_text=None,
            mentions=[],
        )

    return ExtractedCriterion(
        kind="free_text",
        polarity=parent.polarity,
        source_text=source_text,
        negated=parent.negated,
        mood=parent.mood,
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=None,
        temporal_window=None,
        free_text=FreeTextCriterion(
            note=f"composite_subcheck operator={operator}; parent_kind={parent.kind}"
        ),
        mentions=[],
    )


def _mention_backed_composite_groups(
    criterion: ExtractedCriterion,
    *,
    criterion_index: int,
) -> list[CompositeCriterionGroup]:
    mentions = _promotable_mentions(criterion)
    if len(mentions) < 2 or not _has_supported_mention_composite_shape(criterion, mentions):
        return []

    group_id = f"criterion:{criterion_index}:group:001"
    operator: CompositeOperator = "any_of"
    return [
        CompositeCriterionGroup(
            group_id=group_id,
            operator=operator,
            parent_criterion_index=criterion_index,
            parent_source_text=criterion.source_text,
            subchecks=[
                CompositeCriterionSubcheck(
                    subcheck_id=f"{group_id}:subcheck:{index:03d}",
                    operator=operator,
                    source_text=mention.text.strip(),
                    criterion=_mention_subcheck_criterion(
                        parent=criterion,
                        mention=mention,
                    ),
                )
                for index, mention in enumerate(mentions, start=1)
            ],
        )
    ]


def _promotable_mentions(criterion: ExtractedCriterion) -> list[EntityMention]:
    return [
        mention
        for mention in criterion.mentions
        if mention.type in _PROMOTABLE_MENTION_TYPES and mention.text.strip()
    ]


def _has_supported_mention_composite_shape(
    criterion: ExtractedCriterion,
    mentions: list[EntityMention],
) -> bool:
    if not _mentions_have_reviewed_decisions(mentions):
        return False
    source = criterion.source_text
    if _TREATMENT_LIST_RE.search(source) and all(mention.type == "Drug" for mention in mentions):
        return True
    if _PAREN_LIST_RE.search(source) and _mentions_fit_parenthetical_list(source, mentions):
        return True
    return bool(
        _INLINE_DISJUNCTION_RE.search(source)
        and _TEMPORAL_QUALIFIER_RE.search(source)
        and len({mention.type for mention in mentions}) == 1
    )


def _mentions_have_reviewed_decisions(mentions: list[EntityMention]) -> bool:
    reviewed_mappings = get_reviewed_mapping_registry()
    medication_classes = get_reviewed_medication_class_registry()
    for mention in mentions:
        kind: ReviewedMappingKind = "condition" if mention.type == "Condition" else "medication"
        if reviewed_mappings.lookup(kind, mention.text) is not None:
            continue
        if mention.type == "Drug" and medication_classes.lookup(mention.text) is not None:
            continue
        return False
    return True


def _mentions_fit_parenthetical_list(source_text: str, mentions: list[EntityMention]) -> bool:
    for match in _PAREN_LIST_RE.finditer(source_text):
        parenthetical = match.group(0).lower()
        if all(mention.text.strip().lower() in parenthetical for mention in mentions):
            return True
    return False


def _mention_subcheck_criterion(
    *,
    parent: ExtractedCriterion,
    mention: EntityMention,
) -> ExtractedCriterion:
    if mention.type == "Condition":
        return ExtractedCriterion(
            kind="condition_present",
            polarity=parent.polarity,
            source_text=mention.text.strip(),
            negated=parent.negated,
            mood=parent.mood,
            age=None,
            sex=None,
            condition=ConditionCriterion(condition_text=mention.text.strip()),
            medication=None,
            measurement=None,
            temporal_window=None,
            free_text=None,
            mentions=[mention],
        )
    return ExtractedCriterion(
        kind="medication_present",
        polarity=parent.polarity,
        source_text=mention.text.strip(),
        negated=parent.negated,
        mood=parent.mood,
        age=None,
        sex=None,
        condition=None,
        medication=MedicationCriterion(medication_text=mention.text.strip()),
        measurement=None,
        temporal_window=None,
        free_text=None,
        mentions=[mention],
    )


def _measurement_subcheck(source_text: str) -> MeasurementCriterion | None:
    match = _MEASUREMENT_SUBCHECK_RE.search(source_text)
    if match is None:
        return None

    surface = _mapped_lab_surface(match.group("surface"))
    if surface is None:
        return None

    return MeasurementCriterion(
        measurement_text=surface,
        operator=_normalize_threshold_operator(match.group("operator")),
        value=float(match.group("value")),
        value_low=None,
        value_high=None,
        unit=match.group("unit"),
    )


def _mapped_lab_surface(text_before_operator: str) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", text_before_operator)
    for start in range(len(tokens)):
        candidate = " ".join(tokens[start:])
        if lookup_lab(candidate) is not None:
            return candidate
    return None


def _normalize_threshold_operator(operator: str) -> Literal["<", "<=", "=", ">=", ">"]:
    if operator == ">":
        return ">"
    if operator == ">=":
        return ">="
    if operator == "<":
        return "<"
    if operator == "<=":
        return "<="
    if operator == "=":
        return "="
    if operator == "≥":
        return ">="
    return "<="


def _clean_composite_part(part: str) -> str:
    return part.strip().strip("-; )")


__all__ = [
    "CompositeCriterionGroup",
    "CompositeCriterionSubcheck",
    "CompositeOperator",
    "build_composite_criterion_groups",
]
