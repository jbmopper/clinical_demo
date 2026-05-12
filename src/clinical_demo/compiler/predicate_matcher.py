"""Execute compiler `CheckablePredicate`s against a patient profile.

This is the first CC-05 bridge from "compiled plan object" to
"predicate source." It deliberately returns the same `MatchVerdict`
shape as the legacy matcher so scoring, rollups, retrieval, and eval
artifacts can compare the two paths without a second result dialect.
"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from clinical_demo.domain.patient import Condition, LabObservation, Medication
from clinical_demo.domain.trial import Trial
from clinical_demo.extractor.schema import ExtractedCriterion
from clinical_demo.matcher import MATCHER_VERSION
from clinical_demo.matcher.composite import CompositeOperator, roll_up_composite_verdict
from clinical_demo.matcher.modes import DEFAULT_MATCHER_ASSUMPTION_MODE, MatcherAssumptionMode
from clinical_demo.matcher.verdict import (
    ConditionEvidence,
    DemographicsEvidence,
    Evidence,
    LabEvidence,
    MatchVerdict,
    MedicationEvidence,
    MissingEvidence,
    TrialFieldEvidence,
    Verdict,
    VerdictReason,
)
from clinical_demo.profile import ConceptSet, PatientProfile, ThresholdResult
from clinical_demo.profile.profile import ThresholdOp

from .schema import (
    CheckablePredicate,
    CompiledCriterion,
    CriterionCompilationResult,
    ResolutionGap,
)

COMPILED_PREDICATE_MATCHER_VERSION = f"{MATCHER_VERSION}+compiled-predicate-v0.3"
_CLOSED_WORLD_MODES: frozenset[MatcherAssumptionMode] = frozenset(
    {"closed_world_eval", "closed_world_demo"}
)


def match_compiled_criteria(
    compilation: CriterionCompilationResult,
    profile: PatientProfile,
    trial: Trial,
    *,
    matcher_assumption_mode: MatcherAssumptionMode = DEFAULT_MATCHER_ASSUMPTION_MODE,
) -> list[MatchVerdict]:
    """Execute every compiled criterion using typed checkable predicates."""

    return [
        match_compiled_criterion(
            compiled,
            profile,
            trial,
            matcher_assumption_mode=matcher_assumption_mode,
        )
        for compiled in compilation.criteria
    ]


def match_compiled_criterion(
    compiled: CompiledCriterion,
    profile: PatientProfile,
    trial: Trial,
    *,
    matcher_assumption_mode: MatcherAssumptionMode = DEFAULT_MATCHER_ASSUMPTION_MODE,
) -> MatchVerdict:
    """Execute one compiled criterion.

    Criteria with unresolved compiler gaps surface as indeterminate
    verdicts instead of silently falling back. This is what lets the
    parity/eval lane distinguish "predicate execution not ready" from
    "predicate executed and patient did/did not satisfy it."
    """

    criterion = compiled.matcher_input
    if criterion.mood == "hypothetical":
        return _build(
            criterion,
            verdict="indeterminate",
            reason="unsupported_mood",
            rationale=(
                "Criterion is hypothetical (planned/expected); compiled predicate matcher "
                "has no patient-side data on planned events."
            ),
            evidence=[],
            assumption=matcher_assumption_mode,
            evidence_under_assumption=False,
        )

    if _is_compound_compiled(compiled):
        return _match_compiled_compound(
            compiled,
            profile,
            trial,
            matcher_assumption_mode=matcher_assumption_mode,
        )

    if not compiled.checkable_predicates:
        return _gap_verdict(compiled, matcher_assumption_mode)

    raw, reason, rationale, evidence, under_assumption = _execute_predicate(
        compiled.checkable_predicates[0],
        criterion=criterion,
        profile=profile,
        trial=trial,
        matcher_assumption_mode=matcher_assumption_mode,
    )
    return _build(
        criterion,
        verdict=_apply_polarity(raw, criterion.polarity, criterion.negated),
        reason=reason,
        rationale=rationale,
        evidence=evidence,
        assumption=matcher_assumption_mode,
        evidence_under_assumption=under_assumption,
    )


def _is_compound_compiled(compiled: CompiledCriterion) -> bool:
    return (
        compiled.compound_logic.status == "resolved"
        and compiled.compound_logic.operator in {"any_of", "all_of"}
        and bool(compiled.compound_logic.subcheck_ids)
    )


def _match_compiled_compound(
    compiled: CompiledCriterion,
    profile: PatientProfile,
    trial: Trial,
    *,
    matcher_assumption_mode: MatcherAssumptionMode,
) -> MatchVerdict:
    criterion = compiled.matcher_input
    predicate_by_source = {
        predicate.source_criterion_id: predicate for predicate in compiled.checkable_predicates
    }
    gaps_by_source: dict[str, list[ResolutionGap]] = {}
    for gap in compiled.unresolved_gaps:
        gaps_by_source.setdefault(gap.source_criterion_id, []).append(gap)

    raw_results: list[tuple[Verdict, VerdictReason, str, list[Evidence], bool]] = []
    for subcheck_id in compiled.compound_logic.subcheck_ids:
        predicate = predicate_by_source.get(subcheck_id)
        if predicate is None:
            raw_results.append(_compound_missing_predicate_result(subcheck_id, gaps_by_source))
            continue
        raw_results.append(
            _execute_predicate(
                predicate,
                criterion=criterion,
                profile=profile,
                trial=trial,
                matcher_assumption_mode=matcher_assumption_mode,
            )
        )

    operator = cast(CompositeOperator, compiled.compound_logic.operator)
    rollup = roll_up_composite_verdict(operator, [result[0] for result in raw_results])
    evidence = [evidence for result in raw_results for evidence in result[3]]
    return _build(
        criterion,
        verdict=_apply_polarity(rollup.verdict, criterion.polarity, criterion.negated),
        reason=rollup.reason,
        rationale=_compiled_compound_rationale(operator, rollup.rationale, raw_results),
        evidence=evidence,
        assumption=matcher_assumption_mode,
        evidence_under_assumption=any(result[4] for result in raw_results),
    )


def _compound_missing_predicate_result(
    subcheck_id: str,
    gaps_by_source: dict[str, list[ResolutionGap]],
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    gaps = gaps_by_source.get(subcheck_id, [])
    if not gaps:
        return (
            "indeterminate",
            "ambiguous_criterion",
            f"Composite subcheck {subcheck_id!r} has no compiled predicate.",
            [
                MissingEvidence(
                    looked_for=f"compiled predicate for {subcheck_id}",
                    note="compound subcheck has no predicate or compiler gap",
                )
            ],
            False,
        )

    return (
        "indeterminate",
        _reason_for_gaps(gaps),
        (
            f"Composite subcheck {subcheck_id!r} has unresolved compiler gaps: "
            + "; ".join(f"{gap.kind}: {gap.message}" for gap in gaps)
        ),
        [
            MissingEvidence(
                looked_for=f"{gap.domain}:{gap.kind}",
                note=gap.message,
            )
            for gap in gaps
        ],
        False,
    )


def _compiled_compound_rationale(
    operator: str,
    rollup_rationale: str,
    raw_results: list[tuple[Verdict, VerdictReason, str, list[Evidence], bool]],
) -> str:
    subcheck_summaries = [
        f"subcheck {index}: {verdict}/{reason}"
        for index, (verdict, reason, *_rest) in enumerate(raw_results, start=1)
    ]
    return (
        f"Compiled composite {operator} group: {rollup_rationale} "
        f"Subchecks: {'; '.join(subcheck_summaries) or '(none)'}."
    )


def _execute_predicate(
    predicate: CheckablePredicate,
    *,
    criterion: ExtractedCriterion,
    profile: PatientProfile,
    trial: Trial,
    matcher_assumption_mode: MatcherAssumptionMode,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    if predicate.predicate_kind == "demographic":
        return _execute_demographic(predicate, profile, trial)
    if predicate.predicate_kind == "condition_presence":
        return _execute_condition(predicate, profile, matcher_assumption_mode)
    if predicate.predicate_kind == "medication_exposure":
        return _execute_medication(predicate, profile, matcher_assumption_mode)
    if predicate.predicate_kind == "measurement_threshold":
        return _execute_measurement(predicate, profile)
    if predicate.predicate_kind == "temporal_event":
        return _execute_temporal(predicate, profile, matcher_assumption_mode)
    if predicate.predicate_kind == "trial_exposure":
        return _execute_trial_exposure(predicate, matcher_assumption_mode)
    return (
        "indeterminate",
        "unsupported_kind",
        f"Compiled predicate kind {predicate.predicate_kind!r} is not executable.",
        [],
        False,
    )


def _execute_demographic(
    predicate: CheckablePredicate,
    profile: PatientProfile,
    trial: Trial,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    if predicate.target_system == "demographic.age":
        age = profile.age_years
        evidence: list[Evidence] = [
            DemographicsEvidence(field="age_years", value=str(age), note=f"age {age}")
        ]
        if trial.minimum_age is not None:
            evidence.append(
                TrialFieldEvidence(
                    field="minimum_age",
                    value=trial.minimum_age,
                    note=f"trial minimum_age={trial.minimum_age!r}",
                )
            )
        if trial.maximum_age is not None:
            evidence.append(
                TrialFieldEvidence(
                    field="maximum_age",
                    value=trial.maximum_age,
                    note=f"trial maximum_age={trial.maximum_age!r}",
                )
            )
        ok = _age_satisfies(predicate, age)
        return (
            "pass" if ok else "fail",
            "ok",
            f"Patient age {age} {'satisfies' if ok else 'does not satisfy'} compiled age predicate.",
            evidence,
            False,
        )

    if predicate.target_system == "demographic.sex":
        expected = next(iter(predicate.target_codes), None)
        evidence = [
            DemographicsEvidence(field="sex", value=profile.sex, note=f"patient sex={profile.sex}"),
            TrialFieldEvidence(field="sex", value=trial.sex, note=f"trial sex={trial.sex}"),
        ]
        if expected == "ALL":
            return ("pass", "ok", "Compiled sex predicate accepts all sexes.", evidence, False)
        patient_sex = profile.sex.upper()
        if patient_sex not in {"MALE", "FEMALE"}:
            return (
                "indeterminate",
                "no_data",
                f"Patient sex is {profile.sex!r}; compiled predicate requires {expected}.",
                evidence,
                False,
            )
        return (
            "pass" if patient_sex == expected else "fail",
            "ok",
            f"Patient sex {profile.sex!r} {'matches' if patient_sex == expected else 'does not match'} compiled predicate {expected}.",
            evidence,
            False,
        )

    return (
        "indeterminate",
        "unsupported_kind",
        f"Unsupported demographic target {predicate.target_system!r}.",
        [],
        False,
    )


def _age_satisfies(predicate: CheckablePredicate, age: int) -> bool:
    if predicate.operator == "in_range":
        low_ok = predicate.value_low is None or age >= predicate.value_low
        high_ok = predicate.value_high is None or age <= predicate.value_high
        return low_ok and high_ok
    if predicate.value is None:
        return False
    if predicate.operator == ">=":
        return age >= predicate.value
    if predicate.operator == ">":
        return age > predicate.value
    if predicate.operator == "<=":
        return age <= predicate.value
    if predicate.operator == "<":
        return age < predicate.value
    if predicate.operator == "=":
        return age == predicate.value
    return False


def _execute_condition(
    predicate: CheckablePredicate,
    profile: PatientProfile,
    mode: MatcherAssumptionMode,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    concept_set = _concept_set(predicate)
    matches = profile.matching_active_conditions(concept_set)
    if matches:
        return (
            "pass",
            "ok",
            f"Patient has active condition matching compiled predicate {concept_set.name!r}.",
            [_condition_evidence(condition, profile) for condition in matches],
            False,
        )

    looked_for = f"active condition in {concept_set.name!r} ({len(concept_set.codes)} codes)"
    if mode in _CLOSED_WORLD_MODES:
        return (
            "fail",
            "ok",
            (
                f"Patient has no active condition matching {concept_set.name!r} "
                "(closed-world: treating absence in the curated record as negative)."
            ),
            [
                MissingEvidence(
                    looked_for=looked_for,
                    note=f"no matching active conditions on profile; absence treated as negative under {mode}",
                )
            ],
            True,
        )
    return (
        "indeterminate",
        "no_data",
        (
            f"Patient record has no active condition matching {concept_set.name!r}; "
            "under open_world this is insufficient evidence, not absence."
        ),
        [MissingEvidence(looked_for=looked_for, note="no matching active conditions on profile")],
        False,
    )


def _execute_medication(
    predicate: CheckablePredicate,
    profile: PatientProfile,
    mode: MatcherAssumptionMode,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    concept_set = _concept_set(predicate)
    matches = [
        medication
        for medication in profile.active_medications
        if medication.concept.code in concept_set.codes
        and medication.concept.system == concept_set.system
    ]
    if matches:
        return (
            "pass",
            "ok",
            f"Patient has active medication matching compiled predicate {concept_set.name!r}.",
            [_medication_evidence(medication, profile) for medication in matches],
            False,
        )

    looked_for = f"active medication in {concept_set.name!r}"
    if mode in _CLOSED_WORLD_MODES:
        return (
            "fail",
            "ok",
            (
                f"Patient has no active medication matching {concept_set.name!r} "
                "(closed-world: treating absence in the curated record as negative)."
            ),
            [
                MissingEvidence(
                    looked_for=looked_for,
                    note=f"no matching active medications on profile; absence treated as negative under {mode}",
                )
            ],
            True,
        )
    return (
        "indeterminate",
        "no_data",
        (
            f"Patient record has no active medication matching {concept_set.name!r}; "
            "under open_world this is insufficient evidence, not absence."
        ),
        [MissingEvidence(looked_for=looked_for, note="no matching active medications on profile")],
        False,
    )


def _execute_measurement(
    predicate: CheckablePredicate,
    profile: PatientProfile,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    if predicate.target_system != "http://loinc.org":
        return (
            "indeterminate",
            "unsupported_kind",
            f"Measurement predicate target system {predicate.target_system!r} is not LOINC.",
            [],
            False,
        )
    if predicate.unit is None:
        return (
            "indeterminate",
            "ambiguous_criterion",
            f"Measurement predicate {predicate.predicate_id!r} has no comparison unit.",
            [],
            False,
        )

    obs = _latest_lab_for_predicate(profile, predicate)
    if obs is None:
        return (
            "indeterminate",
            "no_data",
            f"No lab observation for compiled measurement predicate {predicate.surface!r}.",
            [
                MissingEvidence(
                    looked_for=_lab_looked_for(predicate),
                    note="patient has no observation for this lab concept set",
                )
            ],
            False,
        )
    if predicate.operator in {"in_range", "out_of_range"}:
        return _execute_measurement_range(predicate, profile, obs)
    threshold_value = _measurement_threshold_value(predicate, profile)
    if predicate.operator not in {"<", "<=", "=", ">=", ">"} or threshold_value is None:
        return (
            "indeterminate",
            "ambiguous_criterion",
            f"Measurement predicate {predicate.predicate_id!r} has incomplete threshold fields.",
            [],
            False,
        )

    result = profile.meets_threshold(
        obs.concept.code,
        _profile_op(predicate.operator),
        threshold_value,
        predicate.unit,
    )
    return _threshold_to_verdict(result, predicate, obs, profile)


def _measurement_threshold_value(
    predicate: CheckablePredicate,
    profile: PatientProfile,
) -> float | None:
    if predicate.value is not None:
        return predicate.value
    if not predicate.value_by_sex:
        return None
    return predicate.value_by_sex.get(profile.sex.upper())


def _execute_measurement_range(
    predicate: CheckablePredicate,
    profile: PatientProfile,
    obs: LabObservation,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    if predicate.value_low is None or predicate.value_high is None or predicate.unit is None:
        return (
            "indeterminate",
            "ambiguous_criterion",
            f"Range predicate {predicate.predicate_id!r} has incomplete range fields.",
            [],
            False,
        )

    low_result = profile.meets_threshold(
        obs.concept.code,
        ">=",
        predicate.value_low,
        predicate.unit,
    )
    high_result = profile.meets_threshold(
        obs.concept.code,
        "<=",
        predicate.value_high,
        predicate.unit,
    )
    for result in (low_result, high_result):
        if result in {
            ThresholdResult.NO_DATA,
            ThresholdResult.STALE_DATA,
            ThresholdResult.UNIT_MISMATCH,
        }:
            return _threshold_to_verdict(result, predicate, obs, profile)

    in_range = low_result == ThresholdResult.MEETS and high_result == ThresholdResult.MEETS
    raw = (in_range and predicate.operator == "in_range") or (
        not in_range and predicate.operator == "out_of_range"
    )
    return (
        "pass" if raw else "fail",
        "ok",
        (
            f"{predicate.surface or 'measurement'} {'satisfies' if raw else 'does not satisfy'} "
            f"{predicate.operator} [{predicate.value_low}, {predicate.value_high}] {predicate.unit}"
        ),
        [_lab_evidence(obs)],
        False,
    )


def _threshold_to_verdict(
    result: ThresholdResult,
    predicate: CheckablePredicate,
    obs: LabObservation,
    profile: PatientProfile,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    if result == ThresholdResult.MEETS:
        return (
            "pass",
            "ok",
            f"{predicate.surface or 'measurement'} satisfies compiled threshold.",
            [_lab_evidence(obs)],
            False,
        )
    if result == ThresholdResult.DOES_NOT_MEET:
        return (
            "fail",
            "ok",
            f"{predicate.surface or 'measurement'} does not satisfy compiled threshold.",
            [_lab_evidence(obs)],
            False,
        )
    if result == ThresholdResult.NO_DATA:
        return (
            "indeterminate",
            "no_data",
            f"No lab observation for compiled measurement predicate {predicate.surface!r}.",
            [
                MissingEvidence(
                    looked_for=_lab_looked_for(predicate),
                    note="patient has no observation for this lab",
                )
            ],
            False,
        )
    if result == ThresholdResult.STALE_DATA:
        return (
            "indeterminate",
            "stale_data",
            f"Patient's {predicate.surface!r} lab exists but is older than the freshness window.",
            [_lab_evidence(obs)],
            False,
        )
    return (
        "indeterminate",
        "unit_mismatch",
        f"Cannot compare {predicate.surface!r}: lab and threshold units do not match.",
        [_lab_evidence(obs)],
        False,
    )


def _execute_temporal(
    predicate: CheckablePredicate,
    profile: PatientProfile,
    mode: MatcherAssumptionMode,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    concept_set = _concept_set(predicate)
    if predicate.window_days is None:
        return (
            "indeterminate",
            "ambiguous_criterion",
            f"Temporal predicate {predicate.predicate_id!r} has no window_days.",
            [],
            False,
        )
    cutoff = profile.as_of - timedelta(days=predicate.window_days)
    matches = [
        condition
        for condition in profile.patient.conditions
        if condition.is_clinical
        and condition.concept.code in concept_set.codes
        and condition.concept.system == concept_set.system
        and condition.onset_date is not None
        and cutoff <= condition.onset_date <= profile.as_of
    ]
    if matches:
        return (
            "pass",
            "ok",
            (
                f"Patient has {concept_set.name!r} event within the last "
                f"{predicate.window_days} days."
            ),
            [
                _temporal_evidence(condition, predicate.window_days, profile)
                for condition in matches
            ],
            False,
        )

    looked_for = (
        f"{concept_set.name!r} event between {cutoff.isoformat()} and {profile.as_of.isoformat()}"
    )
    if mode in _CLOSED_WORLD_MODES:
        return (
            "fail",
            "ok",
            (
                f"Patient has no {concept_set.name!r} event within the last "
                f"{predicate.window_days} days (closed-world: treating absence as negative)."
            ),
            [
                MissingEvidence(
                    looked_for=looked_for,
                    note=f"no matching temporal events found; absence treated as negative under {mode}",
                )
            ],
            True,
        )
    return (
        "indeterminate",
        "no_data",
        (
            f"Patient record has no {concept_set.name!r} event within the last "
            f"{predicate.window_days} days; under open_world this is insufficient evidence."
        ),
        [MissingEvidence(looked_for=looked_for, note="no matching temporal events found")],
        False,
    )


def _execute_trial_exposure(
    predicate: CheckablePredicate,
    mode: MatcherAssumptionMode,
) -> tuple[Verdict, VerdictReason, str, list[Evidence], bool]:
    surface = predicate.surface or "trial exposure"
    looked_for = "patient record evidence of clinical trial or investigational-agent exposure"
    if mode in _CLOSED_WORLD_MODES:
        return (
            "fail",
            "ok",
            (
                "Patient has no recorded clinical trial or investigational-agent exposure "
                f"matching {surface!r} (closed-world: treating absence in the curated record "
                "as negative)."
            ),
            [
                MissingEvidence(
                    looked_for=looked_for,
                    note=(
                        "no matching trial-exposure rows on profile; absence treated as "
                        f"negative under {mode}"
                    ),
                )
            ],
            True,
        )
    return (
        "indeterminate",
        "no_data",
        (
            "Patient record has no clinical trial or investigational-agent exposure rows "
            f"matching {surface!r}; under open_world this is insufficient evidence, not absence."
        ),
        [
            MissingEvidence(
                looked_for=looked_for,
                note="no matching trial-exposure rows on profile",
            )
        ],
        False,
    )


def _gap_verdict(
    compiled: CompiledCriterion,
    assumption: MatcherAssumptionMode,
) -> MatchVerdict:
    criterion = compiled.matcher_input
    if criterion.kind == "free_text":
        return _build(
            criterion,
            verdict="indeterminate",
            reason="human_review_required",
            rationale="Free-text criterion; no compiled predicate was produced.",
            evidence=[],
            assumption=assumption,
            evidence_under_assumption=False,
        )

    reason = _reason_for_gaps(compiled.unresolved_gaps)
    rationale = _gap_rationale(compiled)
    evidence: list[Evidence] = [
        MissingEvidence(
            looked_for=f"{gap.domain}:{gap.kind}",
            note=gap.message,
        )
        for gap in compiled.unresolved_gaps
    ]
    return _build(
        criterion,
        verdict="indeterminate",
        reason=reason,
        rationale=rationale,
        evidence=evidence,
        assumption=assumption,
        evidence_under_assumption=False,
    )


def _reason_for_gaps(gaps: list[ResolutionGap]) -> VerdictReason:
    if any(gap.kind == "unmapped_concept" for gap in gaps):
        return "unmapped_concept"
    if any(gap.kind == "missing_unit" for gap in gaps):
        return "ambiguous_criterion"
    if any(gap.kind == "unsupported_predicate" for gap in gaps):
        return "unsupported_kind"
    return "ambiguous_criterion"


def _gap_rationale(compiled: CompiledCriterion) -> str:
    if not compiled.unresolved_gaps:
        return "Compiler did not produce an executable predicate for this criterion."
    return "Compiler did not produce an executable predicate: " + "; ".join(
        f"{gap.kind}: {gap.message}" for gap in compiled.unresolved_gaps
    )


def _condition_evidence(condition: Condition, profile: PatientProfile) -> ConditionEvidence:
    return ConditionEvidence(
        concept=condition.concept,
        onset_date=condition.onset_date,
        abatement_date=condition.abatement_date,
        note=(
            f"{condition.concept.display or condition.concept.code} "
            f"(active as of {profile.as_of.isoformat()})"
        ),
    )


def _temporal_evidence(
    condition: Condition,
    window_days: int,
    profile: PatientProfile,
) -> ConditionEvidence:
    return ConditionEvidence(
        concept=condition.concept,
        onset_date=condition.onset_date,
        abatement_date=condition.abatement_date,
        note=(
            f"{condition.concept.display or condition.concept.code} onset "
            f"{condition.onset_date.isoformat() if condition.onset_date else 'unknown'} "
            f"(within {window_days} days of {profile.as_of.isoformat()})"
        ),
    )


def _medication_evidence(medication: Medication, profile: PatientProfile) -> MedicationEvidence:
    return MedicationEvidence(
        concept=medication.concept,
        start_date=medication.start_date,
        end_date=medication.end_date,
        note=(
            f"{medication.concept.display or medication.concept.code} "
            f"(active as of {profile.as_of.isoformat()})"
        ),
    )


def _lab_evidence(obs: LabObservation) -> LabEvidence:
    return LabEvidence(
        concept=obs.concept,
        value=obs.value,
        unit=obs.unit,
        effective_date=obs.effective_date,
        note=f"{obs.value} {obs.unit} on {obs.effective_date.isoformat()}",
    )


def _latest_lab_for_predicate(
    profile: PatientProfile,
    predicate: CheckablePredicate,
) -> LabObservation | None:
    observations = [
        obs
        for code in sorted(predicate.target_codes)
        for obs in [profile.latest_lab(code)]
        if obs is not None and obs.concept.system == predicate.target_system
    ]
    if not observations:
        return None
    return max(observations, key=lambda obs: (obs.effective_date, obs.concept.code))


def _lab_looked_for(predicate: CheckablePredicate) -> str:
    return (
        f"latest lab for {predicate.target_system or 'unknown system'} "
        f"codes={','.join(sorted(predicate.target_codes))}"
    )


def _profile_op(operator: str) -> ThresholdOp:
    if operator == "=":
        return "=="
    return operator  # type: ignore[return-value]


def _concept_set(predicate: CheckablePredicate) -> ConceptSet:
    return ConceptSet(
        name=predicate.surface or predicate.predicate_id,
        system=predicate.target_system or "",
        codes=predicate.target_codes,
    )


def _apply_polarity(raw: Verdict, polarity: str, negated: bool) -> Verdict:
    if raw == "indeterminate":
        return raw
    flip = (polarity == "exclusion") ^ negated
    if not flip:
        return raw
    return "fail" if raw == "pass" else "pass"


def _build(
    criterion: ExtractedCriterion,
    *,
    verdict: Verdict,
    reason: VerdictReason,
    rationale: str,
    evidence: list[Evidence],
    assumption: MatcherAssumptionMode,
    evidence_under_assumption: bool,
) -> MatchVerdict:
    return MatchVerdict(
        criterion=criterion,
        verdict=verdict,
        reason=reason,
        rationale=rationale,
        evidence=evidence,
        matcher_version=COMPILED_PREDICATE_MATCHER_VERSION,
        assumption=assumption,
        evidence_under_assumption=evidence_under_assumption,
    )


__all__ = [
    "COMPILED_PREDICATE_MATCHER_VERSION",
    "match_compiled_criteria",
    "match_compiled_criterion",
]
