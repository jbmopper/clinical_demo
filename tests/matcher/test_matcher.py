"""Per-kind matcher tests.

Each `CriterionKind` has its own pass / fail / indeterminate paths;
we cover them explicitly so a regression in one kind doesn't hide
behind a high aggregate pass rate.

Tests organised by kind, then by outcome class. Polarity / negation
interactions are smoke-tested at the top-level dispatcher in
`test_dispatch.py`; the truth table for the polarity helper is in
`test_polarity.py`.
"""

from __future__ import annotations

from datetime import date

from clinical_demo.extractor.schema import EntityMention
from clinical_demo.matcher import MATCHER_VERSION, match_criterion
from clinical_demo.profile.profile import ConceptSet
from tests.matcher._fixtures import (
    AS_OF,
    crit_age,
    crit_condition,
    crit_free_text,
    crit_measurement,
    crit_medication,
    crit_sex,
    crit_temporal_window,
    make_condition,
    make_lab,
    make_medication,
    make_profile,
    make_trial,
)

# ---------- age ----------


def test_age_pass_within_lower_bound() -> None:
    """Patient at minimum age satisfies a `>= min` criterion."""
    profile = make_profile(birth=date(2007, 1, 1))  # turns 18 on 2025-01-01
    v = match_criterion(crit_age(minimum_years=18.0), profile, make_trial())
    assert v.verdict == "pass"
    assert v.reason == "ok"
    assert v.matcher_version == MATCHER_VERSION


def test_age_fail_below_lower_bound() -> None:
    """Underage patient fails an inclusion-side adult criterion."""
    profile = make_profile(birth=date(2010, 1, 1))  # age 14 on 2025-01-01
    v = match_criterion(crit_age(minimum_years=18.0), profile, make_trial())
    assert v.verdict == "fail"
    assert v.reason == "ok"


def test_age_fail_above_upper_bound() -> None:
    profile = make_profile(birth=date(1940, 1, 1))  # age 85
    v = match_criterion(crit_age(minimum_years=18.0, maximum_years=80.0), profile, make_trial())
    assert v.verdict == "fail"


def test_age_evidence_includes_trial_field_when_present() -> None:
    """Trial-side structured age fields are cited as auxiliary
    evidence so the reviewer can compare the LLM's restatement to
    the source."""
    profile = make_profile(birth=date(1990, 1, 1))
    trial = make_trial(minimum_age="18 Years", maximum_age="80 Years")
    v = match_criterion(crit_age(minimum_years=18.0), profile, trial)
    kinds = {e.kind for e in v.evidence}
    assert "demographics" in kinds
    assert "trial_field" in kinds


# ---------- sex ----------


def test_sex_all_passes_regardless() -> None:
    """`ALL` short-circuits to pass; reason stays `ok`."""
    profile = make_profile(sex="female")
    v = match_criterion(crit_sex(sex="ALL"), profile, make_trial())
    assert v.verdict == "pass"


def test_sex_match_passes() -> None:
    profile = make_profile(sex="female")
    v = match_criterion(crit_sex(sex="FEMALE"), profile, make_trial())
    assert v.verdict == "pass"


def test_sex_mismatch_fails() -> None:
    profile = make_profile(sex="male")
    v = match_criterion(crit_sex(sex="FEMALE"), profile, make_trial())
    assert v.verdict == "fail"


def test_sex_unknown_patient_returns_indeterminate() -> None:
    """`other`/`unknown` patient sex against a specific MALE/FEMALE
    requirement is indeterminate — matcher doesn't guess."""
    profile = make_profile(sex="unknown")
    v = match_criterion(crit_sex(sex="MALE"), profile, make_trial())
    assert v.verdict == "indeterminate"
    assert v.reason == "no_data"


# ---------- condition ----------


def test_condition_present_pass() -> None:
    """T2DM-coded condition active on `as_of` satisfies a present
    criterion."""
    profile = make_profile(conditions=[make_condition(code="44054006", display="T2DM")])
    v = match_criterion(crit_condition(text="type 2 diabetes"), profile, make_trial())
    assert v.verdict == "pass"
    assert any(e.kind == "condition" for e in v.evidence)


def test_condition_present_open_world_no_match_indeterminate() -> None:
    """Open-world (default) treats a missing FHIR row as silence,
    not as evidence of absence: indeterminate(no_data) with a
    MissingEvidence trail citing what we looked for. This is the
    PLAN 2.19 / D-73 honesty fix; before, the matcher returned
    `fail` here (silently flipped to `pass` for `*_absent`
    criteria), which papered over real terminology gaps."""
    profile = make_profile(conditions=[])
    v = match_criterion(crit_condition(text="type 2 diabetes"), profile, make_trial())
    assert v.verdict == "indeterminate"
    assert v.reason == "no_data"
    assert v.assumption == "open_world"
    assert v.evidence_under_assumption is False
    assert any(e.kind == "missing" for e in v.evidence)


def test_condition_present_closed_world_no_match_fails() -> None:
    """Closed-world treats the curated record as authoritative for
    resolved concepts: no T2DM row ⇒ patient does not have T2DM,
    raw=fail, and `evidence_under_assumption=True` so audits can
    spot which verdicts depend on the closed-world contract."""
    profile = make_profile(conditions=[])
    v = match_criterion(
        crit_condition(text="type 2 diabetes"),
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )
    assert v.verdict == "fail"
    assert v.reason == "ok"
    assert v.assumption == "closed_world_eval"
    assert v.evidence_under_assumption is True
    assert any(e.kind == "missing" for e in v.evidence)


def test_condition_unmapped_text_indeterminate() -> None:
    """Surface form not in the lookup table → indeterminate
    regardless of mode (closed-world cannot paper over terminology
    failures; D-73 guardrail)."""
    profile = make_profile(conditions=[make_condition()])
    v_open = match_criterion(crit_condition(text="rare unknown disease"), profile, make_trial())
    assert v_open.verdict == "indeterminate"
    assert v_open.reason == "unmapped_concept"
    assert v_open.evidence_under_assumption is False

    v_closed = match_criterion(
        crit_condition(text="rare unknown disease"),
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )
    assert v_closed.verdict == "indeterminate"
    assert v_closed.reason == "unmapped_concept"
    assert v_closed.evidence_under_assumption is False


def test_condition_absent_open_world_indeterminate_after_polarity() -> None:
    """`condition_absent` polarity='inclusion' negated=True means the
    patient must NOT have the condition. Under default open-world
    semantics, raw "patient record has no T2DM row" is
    `indeterminate(no_data)` (FHIR may be silent rather than
    negative); polarity flip leaves indeterminate as indeterminate
    so the verdict surfaces honestly."""
    profile = make_profile(conditions=[])  # no T2DM row
    v = match_criterion(
        crit_condition(
            text="type 2 diabetes",
            kind="condition_absent",
            polarity="inclusion",
            negated=True,
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "no_data"
    assert v.assumption == "open_world"


def test_condition_absent_closed_world_passes_after_polarity() -> None:
    """Same setup as the open-world test, but in closed-world the
    curated record is authoritative: raw "no T2DM" → fail, the
    `condition_absent` inclusion-side negation flips it to pass."""
    profile = make_profile(conditions=[])  # no T2DM row
    v = match_criterion(
        crit_condition(
            text="type 2 diabetes",
            kind="condition_absent",
            polarity="inclusion",
            negated=True,
        ),
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )
    assert v.verdict == "pass"
    assert v.assumption == "closed_world_eval"
    assert v.evidence_under_assumption is True


# ---------- medication ----------


def test_medication_always_indeterminate_in_v0() -> None:
    """Med lookup table is intentionally empty; this is the design
    contract. If you start populating that table, this test should
    fail and you should rewrite it deliberately."""
    profile = make_profile()
    v = match_criterion(crit_medication(text="metformin"), profile, make_trial())
    assert v.verdict == "indeterminate"
    assert v.reason == "unmapped_concept"


# ---------- measurement_threshold ----------


def test_measurement_threshold_meets_passes() -> None:
    """HbA1c 7.5% satisfies `>= 7.0%`."""
    profile = make_profile(
        observations=[make_lab(loinc="4548-4", value=7.5, unit="%")],
    )
    v = match_criterion(
        crit_measurement(text="hba1c", operator=">=", value=7.0, unit="%"), profile, make_trial()
    )
    assert v.verdict == "pass"
    assert any(e.kind == "lab" for e in v.evidence)


def test_measurement_threshold_does_not_meet_fails() -> None:
    """HbA1c 6.0% fails `>= 7.0%`."""
    profile = make_profile(
        observations=[make_lab(loinc="4548-4", value=6.0, unit="%")],
    )
    v = match_criterion(
        crit_measurement(text="hba1c", operator=">=", value=7.0, unit="%"), profile, make_trial()
    )
    assert v.verdict == "fail"


def test_measurement_threshold_checks_all_codes_in_concept_set(monkeypatch) -> None:
    """Terminology-backed lab sets can contain multiple LOINCs.

    The matcher must use the patient observation that actually exists,
    not whichever code happens to come first in a frozenset.
    """
    expanded_hba1c = ConceptSet(
        name="expanded HbA1c",
        system="http://loinc.org",
        codes=frozenset({"17856-6", "4548-4", "96595-4"}),
    )
    monkeypatch.setattr(
        "clinical_demo.matcher.matcher.lookup_lab",
        lambda text: expanded_hba1c if text == "hba1c" else None,
    )
    profile = make_profile(
        observations=[make_lab(loinc="4548-4", value=6.0, unit="%")],
    )
    v = match_criterion(
        crit_measurement(text="hba1c", operator=">=", value=6.5, unit="%"),
        profile,
        make_trial(),
    )
    assert v.verdict == "fail"
    assert v.reason == "ok"
    assert v.evidence[0].kind == "lab"
    assert v.evidence[0].model_dump()["concept"]["code"] == "4548-4"


def test_measurement_no_lab_returns_no_data() -> None:
    """Honest no-data signal — the matcher's job is to surface this,
    not to silently fail the criterion."""
    profile = make_profile(observations=[])
    v = match_criterion(
        crit_measurement(text="hba1c", operator=">=", value=7.0, unit="%"), profile, make_trial()
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "no_data"
    assert any(e.kind == "missing" for e in v.evidence)


def test_measurement_unit_mismatch() -> None:
    """Threshold unit `mmol/mol` doesn't canonicalize against our
    HbA1c LOINC table → unit_mismatch (matcher fails closed)."""
    profile = make_profile(
        observations=[make_lab(loinc="4548-4", value=7.5, unit="%")],
    )
    v = match_criterion(
        crit_measurement(text="hba1c", operator=">=", value=53.0, unit="mmol/mol"),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "unit_mismatch"


def test_measurement_bp_accepts_trial_mmhg_against_synthea_ucum() -> None:
    """Trial text uses `mmHg`; Synthea stores BP components as `mm[Hg]`."""
    profile = make_profile(
        observations=[make_lab(loinc="8480-6", value=138.0, unit="mm[Hg]")],
    )
    v = match_criterion(
        crit_measurement(
            text="systolic blood pressure",
            operator=">",
            value=160.0,
            unit="mmHg",
            polarity="exclusion",
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"
    assert v.reason == "ok"
    assert any(e.kind == "lab" for e in v.evidence)


def test_measurement_bp_infers_missing_conventional_unit() -> None:
    """Bare BP thresholds in trial text conventionally mean mmHg."""
    profile = make_profile(
        observations=[make_lab(loinc="8480-6", value=138.0, unit="mm[Hg]")],
    )
    v = match_criterion(
        crit_measurement(
            text="systolic blood pressure",
            operator="<",
            value=140.0,
            unit=None,
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"
    assert v.reason == "ok"


def test_measurement_egfr_infers_missing_conventional_unit() -> None:
    """eGFR thresholds are often written as bare values in trial text."""
    profile = make_profile(
        observations=[make_lab(loinc="33914-3", value=65.0, unit="mL/min")],
    )
    v = match_criterion(
        crit_measurement(text="egfr", operator="<", value=25.0, unit=None),
        profile,
        make_trial(),
    )
    assert v.verdict == "fail"
    assert v.reason == "ok"


def test_measurement_ldl_converts_trial_mmol_l_against_patient_mg_dl() -> None:
    """LDL-C trial threshold in mmol/L should compare against Synthea mg/dL."""
    profile = make_profile(
        observations=[make_lab(loinc="18262-6", value=134.78, unit="mg/dL")],
    )
    v = match_criterion(
        crit_measurement(text="ldl-c", operator=">=", value=2.6, unit="mmol/L"),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"
    assert v.reason == "ok"


def test_measurement_equality_operator_translates_to_profile() -> None:
    """The extractor's clinical-style `=` must be translated to the
    profile's Pythonic `==`; this is the small but load-bearing glue
    between the two modules."""
    profile = make_profile(
        observations=[make_lab(loinc="4548-4", value=7.0, unit="%")],
    )
    v = match_criterion(
        crit_measurement(text="hba1c", operator="=", value=7.0, unit="%"),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"


def test_measurement_unmapped_lab_indeterminate() -> None:
    profile = make_profile()
    v = match_criterion(
        crit_measurement(text="bnp", operator=">=", value=100.0, unit="pg/mL"),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "unmapped_concept"


def test_measurement_in_range_pass() -> None:
    """HbA1c 7.5% is in [7.0, 9.0]."""
    profile = make_profile(
        observations=[make_lab(loinc="4548-4", value=7.5, unit="%")],
    )
    v = match_criterion(
        crit_measurement(
            text="hba1c",
            operator="in_range",
            value=None,
            value_low=7.0,
            value_high=9.0,
            unit="%",
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"


def test_measurement_in_range_outside_fails() -> None:
    profile = make_profile(
        observations=[make_lab(loinc="4548-4", value=10.5, unit="%")],
    )
    v = match_criterion(
        crit_measurement(
            text="hba1c",
            operator="in_range",
            value=None,
            value_low=7.0,
            value_high=9.0,
            unit="%",
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "fail"


def test_measurement_range_missing_bound_is_ambiguous() -> None:
    profile = make_profile(
        observations=[make_lab(loinc="4548-4", value=7.5, unit="%")],
    )
    v = match_criterion(
        crit_measurement(
            text="hba1c",
            operator="in_range",
            value=None,
            value_low=7.0,
            value_high=None,
            unit="%",
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "ambiguous_criterion"


def test_measurement_one_sided_op_missing_value_is_ambiguous() -> None:
    profile = make_profile()
    v = match_criterion(
        crit_measurement(text="hba1c", operator=">=", value=None, unit="%"), profile, make_trial()
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "ambiguous_criterion"


def test_measurement_missing_unit_is_ambiguous() -> None:
    profile = make_profile()
    v = match_criterion(
        crit_measurement(text="hba1c", operator=">=", value=7.0, unit=None), profile, make_trial()
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "ambiguous_criterion"


# ---------- temporal_window ----------


def test_temporal_window_recent_event_passes() -> None:
    """Recent T2DM diagnosis falls within a 365-day window."""
    profile = make_profile(
        conditions=[make_condition(code="44054006", display="T2DM", onset=date(2024, 6, 1))]
    )
    v = match_criterion(
        crit_temporal_window(event_text="type 2 diabetes", window_days=365),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"


def test_temporal_window_open_world_old_event_indeterminate() -> None:
    """Diagnosis 5 years before `as_of` is outside a 90-day window;
    under default open-world semantics that's
    `indeterminate(no_data)` (FHIR may not have captured a more
    recent event), not a hard fail."""
    profile = make_profile(
        conditions=[make_condition(code="44054006", display="T2DM", onset=date(2020, 1, 1))]
    )
    v = match_criterion(
        crit_temporal_window(event_text="type 2 diabetes", window_days=90),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "no_data"


def test_temporal_window_closed_world_old_event_fails() -> None:
    """Same setup but in closed-world: the curated record is
    authoritative, so "no event in the last 90 days" is a hard
    fail with `evidence_under_assumption=True`."""
    profile = make_profile(
        conditions=[make_condition(code="44054006", display="T2DM", onset=date(2020, 1, 1))]
    )
    v = match_criterion(
        crit_temporal_window(event_text="type 2 diabetes", window_days=90),
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )
    assert v.verdict == "fail"
    assert v.evidence_under_assumption is True


def test_temporal_window_future_direction_unsupported() -> None:
    """`within_future` lands as `unsupported_mood` — patients have no
    planned-event records in v0."""
    profile = make_profile()
    v = match_criterion(
        crit_temporal_window(
            event_text="type 2 diabetes",
            window_days=30,
            direction="within_future",
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "unsupported_mood"


def test_temporal_window_unmapped_event() -> None:
    profile = make_profile()
    v = match_criterion(
        crit_temporal_window(event_text="liver transplant", window_days=365),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "unmapped_concept"


# ---------- free_text ----------


def test_free_text_without_correlatable_mentions_stays_human_review() -> None:
    """Open-ended free-text criteria honestly defer to human review."""
    profile = make_profile()
    v = match_criterion(crit_free_text(), profile, make_trial())
    assert v.verdict == "indeterminate"
    assert v.reason == "human_review_required"


def test_free_text_single_condition_mention_promotes_to_condition_match() -> None:
    profile = make_profile(conditions=[make_condition(code="44054006", display="T2DM")])
    v = match_criterion(
        crit_free_text(
            source_text="History of type 2 diabetes",
            mentions=[EntityMention(text="type 2 diabetes", type="Condition")],
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"
    assert v.reason == "ok"
    assert "Promoted correlatable free-text condition mention" in v.rationale
    assert any(e.kind == "condition" for e in v.evidence)


def test_free_text_condition_promotion_respects_exclusion_polarity() -> None:
    profile = make_profile(conditions=[make_condition(code="44054006", display="T2DM")])
    v = match_criterion(
        crit_free_text(
            polarity="exclusion",
            source_text="History of type 2 diabetes",
            mentions=[EntityMention(text="type 2 diabetes", type="Condition")],
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "fail"
    assert v.reason == "ok"
    assert "Promoted correlatable free-text condition mention" in v.rationale


def test_free_text_bone_fracture_promotion_uses_reviewed_mapping() -> None:
    profile = make_profile(
        conditions=[make_condition(code="65966004", display="Fracture of forearm")]
    )
    v = match_criterion(
        crit_free_text(
            polarity="exclusion",
            source_text="Bone fractures within the past 12 months",
            mentions=[EntityMention(text="Bone fractures", type="Condition")],
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "fail"
    assert v.reason == "ok"
    assert "Promoted correlatable free-text condition mention" in v.rationale
    assert any(e.kind == "condition" for e in v.evidence)


def test_free_text_single_measurement_threshold_promotes_to_measurement_match() -> None:
    profile = make_profile(observations=[make_lab(loinc="39156-5", value=31.0, unit="kg/m2")])
    v = match_criterion(
        crit_free_text(
            polarity="exclusion",
            source_text="BMI > 32 kg/m2",
            mentions=[EntityMention(text="BMI", type="Measurement")],
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"
    assert v.reason == "ok"
    assert "Promoted correlatable free-text measurement mention" in v.rationale
    assert any(e.kind == "lab" for e in v.evidence)


def test_free_text_trial_exposure_open_world_stays_insufficient() -> None:
    profile = make_profile()
    v = match_criterion(
        crit_free_text(
            polarity="exclusion",
            source_text="Use of other investigational agents within 3 months of enrollment",
            mentions=[
                EntityMention(text="other investigational agents", type="Drug"),
                EntityMention(text="3 months", type="Temporal"),
            ],
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "no_data"
    assert "trial-exposure" in v.rationale


def test_free_text_trial_exposure_closed_world_absence_satisfies_exclusion() -> None:
    profile = make_profile()
    v = match_criterion(
        crit_free_text(
            polarity="exclusion",
            source_text="Use of other investigational agents within 3 months of enrollment",
            mentions=[
                EntityMention(text="other investigational agents", type="Drug"),
                EntityMention(text="3 months", type="Temporal"),
            ],
        ),
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )
    assert v.verdict == "pass"
    assert v.reason == "ok"
    assert v.evidence_under_assumption is True
    assert "investigational-agent exposure" in v.rationale


def test_free_text_trial_exposure_does_not_steal_pregnancy_test_requirement() -> None:
    profile = make_profile()
    v = match_criterion(
        crit_free_text(
            source_text=(
                "Female of childbearing potential must have a negative pregnancy test "
                "at the last screening visit and consent to use highly effective "
                "contraceptives during the trial and 3 months after the last dose of "
                "investigational drug."
            ),
            mentions=[
                EntityMention(text="negative pregnancy test", type="Observation"),
                EntityMention(text="highly effective contraceptives", type="Qualifier"),
                EntityMention(text="3 months after the last dose", type="Temporal"),
            ],
        ),
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )

    assert v.verdict == "indeterminate"
    assert v.reason == "human_review_required"


def test_free_text_medication_list_promotes_any_mapped_match(monkeypatch) -> None:
    metformin = ConceptSet(
        name="metformin (RxNorm)",
        system="http://www.nlm.nih.gov/research/umls/rxnorm",
        codes=frozenset({"860975"}),
    )
    teriparatide = ConceptSet(
        name="teriparatide (RxNorm)",
        system="http://www.nlm.nih.gov/research/umls/rxnorm",
        codes=frozenset({"999999"}),
    )
    monkeypatch.setattr(
        "clinical_demo.matcher.matcher.lookup_medication",
        lambda text: {"metformin": metformin, "teriparatide": teriparatide}.get(text),
    )
    profile = make_profile(
        medications=[
            make_medication(
                code="860975",
                start=date(2024, 7, 1),
                end=date(2024, 9, 1),
            )
        ]
    )

    v = match_criterion(
        crit_free_text(
            polarity="exclusion",
            source_text="Treatment with any of the following drugs in past year: metformin, teriparatide.",
            mentions=[
                EntityMention(text="metformin", type="Drug"),
                EntityMention(text="teriparatide", type="Drug"),
            ],
        ),
        profile,
        make_trial(),
    )

    assert v.verdict == "fail"
    assert v.reason == "ok"
    assert "Promoted correlatable free-text medication-list mention" in v.rationale
    assert any(e.kind == "medication" for e in v.evidence)


def test_free_text_medication_list_open_world_absence_stays_insufficient(monkeypatch) -> None:
    metformin = ConceptSet(
        name="metformin (RxNorm)",
        system="http://www.nlm.nih.gov/research/umls/rxnorm",
        codes=frozenset({"860975"}),
    )
    teriparatide = ConceptSet(
        name="teriparatide (RxNorm)",
        system="http://www.nlm.nih.gov/research/umls/rxnorm",
        codes=frozenset({"999999"}),
    )
    monkeypatch.setattr(
        "clinical_demo.matcher.matcher.lookup_medication",
        lambda text: {"metformin": metformin, "teriparatide": teriparatide}.get(text),
    )
    profile = make_profile()

    v = match_criterion(
        crit_free_text(
            polarity="exclusion",
            source_text="Treatment with any of the following drugs in past year: metformin, teriparatide.",
            mentions=[
                EntityMention(text="metformin", type="Drug"),
                EntityMention(text="teriparatide", type="Drug"),
            ],
        ),
        profile,
        make_trial(),
    )

    assert v.verdict == "indeterminate"
    assert v.reason == "no_data"


def test_free_text_medication_list_unmapped_surfaces_are_mapping_failures() -> None:
    profile = make_profile()
    v = match_criterion(
        crit_free_text(
            polarity="exclusion",
            source_text=(
                "Treatment with any of the following drugs in past year: "
                "immunosuppressants, anticonvulsant therapy, aromatase inhibitors."
            ),
            mentions=[
                EntityMention(text="immunosuppressants", type="Drug"),
                EntityMention(text="anticonvulsant therapy", type="Drug"),
                EntityMention(text="aromatase inhibitors", type="Drug"),
            ],
        ),
        profile,
        make_trial(),
    )

    assert v.verdict == "indeterminate"
    assert v.reason == "unmapped_concept"
    assert "listed free-text medication surface" in v.rationale


def test_free_text_multiple_drugs_without_list_cue_stays_human_review(monkeypatch) -> None:
    metformin = ConceptSet(
        name="metformin (RxNorm)",
        system="http://www.nlm.nih.gov/research/umls/rxnorm",
        codes=frozenset({"860975"}),
    )
    insulin = ConceptSet(
        name="insulin (RxNorm)",
        system="http://www.nlm.nih.gov/research/umls/rxnorm",
        codes=frozenset({"999999"}),
    )
    monkeypatch.setattr(
        "clinical_demo.matcher.matcher.lookup_medication",
        lambda text: {"metformin": metformin, "insulin": insulin}.get(text),
    )
    profile = make_profile(medications=[make_medication(code="860975")])

    v = match_criterion(
        crit_free_text(
            source_text="Metformin and insulin management requires clinician judgment.",
            mentions=[
                EntityMention(text="metformin", type="Drug"),
                EntityMention(text="insulin", type="Drug"),
            ],
        ),
        profile,
        make_trial(),
    )

    assert v.verdict == "indeterminate"
    assert v.reason == "human_review_required"


def test_free_text_multiple_typed_mentions_stays_human_review() -> None:
    profile = make_profile(conditions=[make_condition(code="44054006", display="T2DM")])
    v = match_criterion(
        crit_free_text(
            source_text="Type 2 diabetes treated with metformin",
            mentions=[
                EntityMention(text="type 2 diabetes", type="Condition"),
                EntityMention(text="metformin", type="Drug"),
            ],
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "human_review_required"


def test_free_text_unmodeled_negation_cue_stays_human_review() -> None:
    profile = make_profile(conditions=[make_condition(code="44054006", display="T2DM")])
    v = match_criterion(
        crit_free_text(
            source_text="No history of type 2 diabetes",
            mentions=[EntityMention(text="type 2 diabetes", type="Condition")],
        ),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "human_review_required"


# ---------- mood gate ----------


def test_hypothetical_mood_short_circuits_to_indeterminate() -> None:
    """`mood='hypothetical'` is rejected before dispatch — no patient
    data on planned events."""
    profile = make_profile(conditions=[make_condition()])
    v = match_criterion(
        crit_condition(text="type 2 diabetes", mood="hypothetical"),
        profile,
        make_trial(),
    )
    assert v.verdict == "indeterminate"
    assert v.reason == "unsupported_mood"


# ---------- matcher version ----------


def test_matcher_version_stamped_on_every_verdict() -> None:
    profile = make_profile()
    v = match_criterion(crit_free_text(), profile, make_trial())
    assert v.matcher_version == MATCHER_VERSION
    assert v.matcher_version.startswith("matcher-v")


# ---------- as_of awareness ----------


def test_matcher_uses_profile_as_of_for_age() -> None:
    """Profile carries `as_of`; matcher must use it (not today)."""
    profile = make_profile(birth=date(1990, 6, 15))
    # AS_OF = 2025-01-01 in conftest; turn-of-year birthday is 6/15
    # so age on 2025-01-01 is 34 (35th birthday hasn't happened).
    assert profile.age_years == 34
    v = match_criterion(crit_age(minimum_years=35.0), profile, make_trial())
    assert v.verdict == "fail"


def test_matcher_uses_as_of_for_temporal_window() -> None:
    """Cutoff is `as_of - window_days`, not today."""
    profile = make_profile(
        conditions=[make_condition(code="44054006", display="T2DM", onset=date(2024, 12, 15))]
    )
    # AS_OF = 2025-01-01; 30 days back = 2024-12-02; onset 2024-12-15 → in window
    v = match_criterion(
        crit_temporal_window(event_text="type 2 diabetes", window_days=30),
        profile,
        make_trial(),
    )
    assert v.verdict == "pass"
    assert profile.as_of == AS_OF
