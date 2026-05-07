"""Ephemeral de-identification helpers for outbound data.

The implementation is deliberately stateful only inside an
`AnonymizationContext`. The context is meant to live for one scoring
run, preserve placeholder stability within that run, and then be
discarded. No reverse map is persisted in result envelopes.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

PrivacyStage = Literal["llm_prompt", "trace", "metadata", "public_export"]


class EntityReplacement(BaseModel):
    """One de-identified entity replacement."""

    entity_type: str
    original: str = Field(repr=False)
    replacement: str
    start: int
    end: int


class AnonymizedText(BaseModel):
    """Text after anonymization plus replacement audit metadata."""

    text: str
    replacements: list[EntityReplacement] = Field(default_factory=list)


@dataclass
class PrivacyPolicy:
    """Stage-aware anonymization defaults.

    `trace` and `llm_prompt` preserve clinical utility by replacing
    identifiers with typed placeholders. `metadata` only rewrites
    values for sensitive keys, so dashboard pivots such as model,
    prompt version, NCT id, and counts remain readable.
    """

    stage: PrivacyStage = "trace"
    enabled: bool = True
    language: str = "en"
    score_threshold: float = 0.35
    pseudonymize_metadata_keys: frozenset[str] = frozenset(
        {
            "patient_id",
            "patient",
            "subject_id",
            "person_id",
            "mrn",
            "medical_record_number",
            "note_id",
            "document_id",
        }
    )

    @classmethod
    def llm_prompt(cls) -> PrivacyPolicy:
        return cls(stage="llm_prompt")

    @classmethod
    def trace(cls) -> PrivacyPolicy:
        return cls(stage="trace")

    @classmethod
    def metadata(cls) -> PrivacyPolicy:
        return cls(stage="metadata")

    @classmethod
    def public_export(cls) -> PrivacyPolicy:
        return cls(stage="public_export")


@dataclass
class AnonymizationContext:
    """Run-local placeholder map.

    Same `(entity_type, original)` gets the same placeholder within
    this context. A new context starts fresh, which avoids building a
    durable pseudonym table.
    """

    _values: dict[tuple[str, str], str] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)
    _salt: str = field(default_factory=lambda: secrets.token_hex(3))

    def placeholder_for(self, entity_type: str, original: str) -> str:
        normalized_type = _normalize_entity_type(entity_type)
        key = (normalized_type, original)
        existing = self._values.get(key)
        if existing is not None:
            return existing
        count = self._counts.get(normalized_type, 0) + 1
        self._counts[normalized_type] = count
        placeholder = f"<{normalized_type}_{self._salt}_{count}>"
        self._values[key] = placeholder
        return placeholder


class PrivacyEngine(Protocol):
    """Narrow protocol so tests can inject deterministic engines."""

    def anonymize_text(
        self,
        text: str,
        *,
        context: AnonymizationContext,
        policy: PrivacyPolicy,
    ) -> AnonymizedText: ...


@dataclass(frozen=True)
class _DetectedEntity:
    entity_type: str
    start: int
    end: int
    score: float = 1.0


_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DATE_RE = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")
_MRN_RE = re.compile(
    r"\b(?:MRN|medical record(?: number)?|record no\.?)\s*[:#]?\s*[A-Za-z0-9-]{4,}\b", re.I
)
_PATIENT_ID_RE = re.compile(
    r"\b(?:patient|subject|person)[-_ ]?id\s*[:=]?\s*[A-Za-z0-9][A-Za-z0-9._-]{2,}\b", re.I
)
_NOTE_ID_RE = re.compile(r"\bnote_id=[A-Za-z0-9._-]+\b", re.I)


class PresidioPrivacyEngine:
    """Privacy engine using Presidio when available.

    Presidio is imported lazily so test suites and fresh checkouts do
    not need the NLP stack just to import the application. If Presidio
    cannot be initialized, deterministic regex recognizers still cover
    common identifiers and the project-specific id shapes.
    """

    def __init__(self) -> None:
        self._analyzer: Any | None = None
        self._presidio_ready = False
        self._init_attempted = False

    def anonymize_text(
        self,
        text: str,
        *,
        context: AnonymizationContext,
        policy: PrivacyPolicy,
    ) -> AnonymizedText:
        if not policy.enabled or not text:
            return AnonymizedText(text=text)

        detected = self._detect(text, policy=policy)
        if not detected:
            return AnonymizedText(text=text)

        return _replace_entities(text, detected, context=context)

    def _detect(self, text: str, *, policy: PrivacyPolicy) -> list[_DetectedEntity]:
        detected = [*_fallback_detect(text)]
        analyzer = self._get_analyzer()
        if analyzer is None:
            return _merge_entities(detected, threshold=policy.score_threshold)
        try:
            results = analyzer.analyze(
                text=text,
                language=policy.language,
                score_threshold=policy.score_threshold,
            )
        except Exception:
            return _merge_entities(detected, threshold=policy.score_threshold)

        detected.extend(
            _DetectedEntity(
                entity_type=str(result.entity_type),
                start=int(result.start),
                end=int(result.end),
                score=float(getattr(result, "score", 1.0)),
            )
            for result in results
            if int(result.start) < int(result.end)
        )
        return _merge_entities(detected, threshold=policy.score_threshold)

    def _get_analyzer(self) -> Any | None:
        if self._init_attempted:
            return self._analyzer if self._presidio_ready else None
        self._init_attempted = True
        try:
            from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        except Exception:
            return None
        try:
            analyzer = AnalyzerEngine()
            registry = analyzer.registry
            registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="FHIR_ID",
                    patterns=[
                        Pattern(
                            name="uuid",
                            regex=_UUID_RE.pattern,
                            score=0.9,
                        )
                    ],
                )
            )
            registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="PATIENT_ID",
                    patterns=[
                        Pattern(name="patient-id", regex=_PATIENT_ID_RE.pattern, score=0.8),
                        Pattern(name="note-id", regex=_NOTE_ID_RE.pattern, score=0.75),
                        Pattern(name="mrn", regex=_MRN_RE.pattern, score=0.85),
                    ],
                )
            )
        except Exception:
            return None
        self._analyzer = analyzer
        self._presidio_ready = True
        return analyzer


_DEFAULT_ENGINE = PresidioPrivacyEngine()
_CURRENT_CONTEXT: ContextVar[AnonymizationContext | None] = ContextVar(
    "clinical_demo_anonymization_context",
    default=None,
)


@contextmanager
def anonymization_context(
    context: AnonymizationContext | None = None,
) -> Iterator[AnonymizationContext]:
    """Install an ephemeral anonymization context for one run."""

    active = context or AnonymizationContext()
    token = _CURRENT_CONTEXT.set(active)
    try:
        yield active
    finally:
        _CURRENT_CONTEXT.reset(token)


def current_anonymization_context() -> AnonymizationContext:
    """Return the active run context or create an unscoped one."""

    return _CURRENT_CONTEXT.get() or AnonymizationContext()


def anonymize_text(
    text: str,
    *,
    context: AnonymizationContext | None = None,
    policy: PrivacyPolicy | None = None,
    engine: PrivacyEngine | None = None,
) -> AnonymizedText:
    """Anonymize a string with the active run context by default."""

    active_context = context or current_anonymization_context()
    active_policy = policy or PrivacyPolicy.trace()
    active_engine = engine or _DEFAULT_ENGINE
    return active_engine.anonymize_text(text, context=active_context, policy=active_policy)


def sanitize_for_trace(
    value: Any,
    *,
    context: AnonymizationContext | None = None,
    engine: PrivacyEngine | None = None,
) -> Any:
    """Recursively sanitize trace input/output payloads."""

    return _sanitize_value(value, context=context, policy=PrivacyPolicy.trace(), engine=engine)


def sanitize_for_public_export(
    value: Any,
    *,
    context: AnonymizationContext | None = None,
    engine: PrivacyEngine | None = None,
) -> Any:
    """Recursively sanitize payloads before writing public artifacts."""

    return _sanitize_value(
        value,
        context=context,
        policy=PrivacyPolicy.public_export(),
        engine=engine,
    )


def sanitize_for_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    context: AnonymizationContext | None = None,
    engine: PrivacyEngine | None = None,
) -> dict[str, Any] | None:
    """Sanitize only sensitive metadata values, preserving dashboard pivots."""

    if metadata is None:
        return None
    policy = PrivacyPolicy.metadata()
    active_context = context or current_anonymization_context()
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if _is_sensitive_metadata_key(str(key), policy):
            if isinstance(value, str):
                sanitized[str(key)] = active_context.placeholder_for("PATIENT_ID", value)
            else:
                sanitized[str(key)] = _sanitize_value(
                    value,
                    context=active_context,
                    policy=PrivacyPolicy.trace(),
                    engine=engine,
                )
        else:
            sanitized[str(key)] = value
    return sanitized


def _sanitize_value(
    value: Any,
    *,
    context: AnonymizationContext | None,
    policy: PrivacyPolicy,
    engine: PrivacyEngine | None,
) -> Any:
    active_context = context or current_anonymization_context()
    if isinstance(value, str):
        return anonymize_text(
            value,
            context=active_context,
            policy=policy,
            engine=engine,
        ).text
    if isinstance(value, Mapping):
        if policy.stage == "metadata":
            return sanitize_for_metadata(value, context=active_context, engine=engine)
        return {
            key: _sanitize_value(
                item,
                context=active_context,
                policy=policy,
                engine=engine,
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [
            _sanitize_value(item, context=active_context, policy=policy, engine=engine)
            for item in value
        ]
    return value


def _fallback_detect(text: str) -> list[_DetectedEntity]:
    specs = [
        ("US_SSN", _SSN_RE),
        ("EMAIL_ADDRESS", _EMAIL_RE),
        ("PHONE_NUMBER", _PHONE_RE),
        ("FHIR_ID", _UUID_RE),
        ("MRN", _MRN_RE),
        ("PATIENT_ID", _PATIENT_ID_RE),
        ("NOTE_ID", _NOTE_ID_RE),
        ("DATE_TIME", _DATE_RE),
    ]
    detected: list[_DetectedEntity] = []
    for entity_type, regex in specs:
        detected.extend(
            _DetectedEntity(entity_type=entity_type, start=match.start(), end=match.end())
            for match in regex.finditer(text)
        )
    return detected


def _replace_entities(
    text: str,
    entities: list[_DetectedEntity],
    *,
    context: AnonymizationContext,
) -> AnonymizedText:
    chunks: list[str] = []
    replacements: list[EntityReplacement] = []
    cursor = 0
    for entity in sorted(entities, key=lambda item: (item.start, item.end)):
        if entity.start < cursor:
            continue
        original = text[entity.start : entity.end]
        placeholder = context.placeholder_for(entity.entity_type, original)
        chunks.append(text[cursor : entity.start])
        chunks.append(placeholder)
        replacements.append(
            EntityReplacement(
                entity_type=_normalize_entity_type(entity.entity_type),
                original=original,
                replacement=placeholder,
                start=entity.start,
                end=entity.end,
            )
        )
        cursor = entity.end
    chunks.append(text[cursor:])
    return AnonymizedText(text="".join(chunks), replacements=replacements)


def _merge_entities(
    entities: list[_DetectedEntity],
    *,
    threshold: float,
) -> list[_DetectedEntity]:
    candidates = [
        entity
        for entity in entities
        if entity.score >= threshold and entity.start >= 0 and entity.end > entity.start
    ]
    candidates.sort(key=lambda entity: (entity.start, -(entity.end - entity.start), -entity.score))
    merged: list[_DetectedEntity] = []
    occupied_until = -1
    for entity in candidates:
        if entity.start < occupied_until:
            continue
        merged.append(entity)
        occupied_until = entity.end
    return merged


def _is_sensitive_metadata_key(key: str, policy: PrivacyPolicy) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in policy.pseudonymize_metadata_keys or normalized.endswith("_patient_id")


def _normalize_entity_type(entity_type: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", entity_type.upper()).strip("_")
    if normalized in {"FHIR_ID", "UUID"}:
        return "ID"
    if normalized in {"US_SSN"}:
        return "SSN"
    if normalized in {"DATE", "DATE_TIME"}:
        return "DATE"
    return normalized or "PII"
