"""Tests for the Synthea FHIR loader.

Uses one real bundle (`tests/fixtures/synthea/francisco.json`) extracted from
the upstream Synthea sample data so we exercise the actual schema rather
than a hand-rolled stub.

Coverage gaps (intentional, for v0):
- Bundles where `MedicationRequest` uses `medicationReference` instead of
  inline `medicationCodeableConcept`. Add when a downstream test needs it.
- Conditions categorized as `social-history` (so `is_clinical=False`). The
  fixture happens not to contain one; tested via a fabricated minimal case.
"""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path

import pytest

from clinical_demo.data.synthea import (
    _patient_from_bundle,
    iter_bundles,
    load_bundle,
)
from clinical_demo.domain import Patient

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthea" / "francisco.json"


@pytest.fixture(scope="module")
def francisco() -> Patient:
    return load_bundle(FIXTURE)


def test_loads_patient_demographics(francisco: Patient) -> None:
    assert francisco.patient_id == "ce032ded-978b-b56b-425f-5159d4a4038e"
    assert francisco.sex == "male"
    assert francisco.birth_date == date(1988, 1, 30)


def test_loads_conditions(francisco: Patient) -> None:
    assert len(francisco.conditions) == 3
    snomed_codes = {c.concept.code for c in francisco.conditions}
    assert {"128613002", "84757009", "703151001"} == snomed_codes
    for c in francisco.conditions:
        assert c.concept.system == "http://snomed.info/sct"
        assert c.is_clinical is True
        assert c.onset_date == date(1988, 5, 21)
        assert c.abatement_date is None


def test_loads_observations_with_loinc_and_units(francisco: Patient) -> None:
    obs = francisco.observations
    assert len(obs) >= 5
    body_heights = [o for o in obs if o.concept.code == "8302-2"]
    assert body_heights, "expected at least one body-height observation"
    h = body_heights[0]
    assert h.concept.system == "http://loinc.org"
    assert h.unit == "cm"
    assert h.value > 0


def test_loads_medication_with_inline_concept(francisco: Patient) -> None:
    assert len(francisco.medications) == 1
    med = francisco.medications[0]
    assert med.concept.code == "197591"  # RxNorm diazepam
    assert med.start_date == date(1988, 5, 21)


def test_loads_procedures(francisco: Patient) -> None:
    assert len(francisco.procedures) == 3
    codes = {procedure.concept.code for procedure in francisco.procedures}
    assert {"430193006", "54550000"} == codes
    assert all(
        procedure.concept.system == "http://snomed.info/sct" for procedure in francisco.procedures
    )
    assert all(procedure.status == "completed" for procedure in francisco.procedures)
    assert {procedure.performed_date for procedure in francisco.procedures} == {
        date(1988, 1, 30),
        date(1988, 5, 21),
        date(1988, 7, 9),
    }


def test_loads_procedure_with_performed_datetime() -> None:
    fabricated = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "gender": "female",
                    "birthDate": "1970-01-01",
                }
            },
            {
                "resource": {
                    "resourceType": "Procedure",
                    "id": "proc1",
                    "status": "completed",
                    "code": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "49795001",
                                "display": "Total pneumonectomy",
                            }
                        ]
                    },
                    "performedDateTime": "2020-02-03T00:00:00Z",
                }
            },
        ]
    }

    patient = _patient_from_bundle(fabricated)

    assert len(patient.procedures) == 1
    assert patient.procedures[0].concept.code == "49795001"
    assert patient.procedures[0].performed_date == date(2020, 2, 3)


def test_age_years_handles_birthday_not_yet_reached(francisco: Patient) -> None:
    assert francisco.age_years(date(2020, 1, 30)) == 32  # birthday today
    assert francisco.age_years(date(2020, 1, 29)) == 31  # day before
    assert francisco.age_years(date(2020, 12, 31)) == 32


def test_active_conditions_filters_by_as_of(francisco: Patient) -> None:
    before_onset = date(1988, 5, 1)
    after_onset = date(1990, 1, 1)
    assert francisco.active_conditions(before_onset) == []
    assert len(francisco.active_conditions(after_onset)) == 3


def test_active_conditions_excludes_non_clinical() -> None:
    """Synthea models social findings as Conditions; verify we filter them."""
    fabricated = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "gender": "female",
                    "birthDate": "1970-01-01",
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": "c1",
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                                    "code": "social-history",
                                }
                            ]
                        }
                    ],
                    "code": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "224299000",
                                "display": "Received higher education",
                            }
                        ]
                    },
                    "onsetDateTime": "1990-01-01T00:00:00Z",
                }
            },
        ]
    }
    p = _patient_from_bundle(fabricated)
    assert len(p.conditions) == 1
    assert p.conditions[0].is_clinical is False
    assert p.active_conditions(date(2020, 1, 1)) == []


def test_latest_observation_respects_as_of(francisco: Patient) -> None:
    very_early = date(1980, 1, 1)
    assert francisco.latest_observation("8302-2", very_early) is None
    later = francisco.latest_observation("8302-2", date(2025, 1, 1))
    assert later is not None
    assert later.concept.code == "8302-2"


def test_iter_bundles_yields_patients(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "synthea"
    fixture_dir.mkdir()
    (fixture_dir / "a.json").write_bytes(FIXTURE.read_bytes())
    (fixture_dir / "b.json").write_bytes(FIXTURE.read_bytes())
    patients = list(iter_bundles(fixture_dir))
    assert len(patients) == 2
    assert all(isinstance(p, Patient) for p in patients)


def test_iter_bundles_skips_non_patient_bundles(tmp_path: Path) -> None:
    """Synthea sample dumps include hospital/practitioner-only bundles."""
    import json as _json

    fixture_dir = tmp_path / "synthea"
    fixture_dir.mkdir()
    (fixture_dir / "patient.json").write_bytes(FIXTURE.read_bytes())
    (fixture_dir / "hospitalInformation.json").write_text(
        _json.dumps(
            {
                "resourceType": "Bundle",
                "type": "transaction",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Organization",
                            "id": "org-1",
                            "name": "Some Hospital",
                        }
                    }
                ],
            }
        )
    )
    patients = list(iter_bundles(fixture_dir))
    assert len(patients) == 1


def test_load_bundle_raises_on_empty() -> None:
    with pytest.raises(ValueError, match="no entries"):
        _patient_from_bundle({"entry": []})


def test_loads_deceased_date_when_present() -> None:
    """Synthea encodes death as `Patient.deceasedDateTime`; the loader
    must surface it on the domain model so scoring can refuse to
    evaluate a deceased patient."""
    bundle = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "gender": "male",
                    "birthDate": "1950-01-01",
                    "deceasedDateTime": "2020-06-15T00:00:00-05:00",
                }
            }
        ]
    }
    patient = _patient_from_bundle(bundle)
    assert patient.deceased_date == date(2020, 6, 15)


def test_living_patient_has_no_deceased_date() -> None:
    """A bundle without `deceasedDateTime` round-trips to
    `deceased_date is None`."""
    bundle = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "alive",
                    "gender": "female",
                    "birthDate": "1990-01-01",
                }
            }
        ]
    }
    patient = _patient_from_bundle(bundle)
    assert patient.deceased_date is None


def test_loads_fixture_deceased_date_from_synthea_bundle(francisco: Patient) -> None:
    """The Francisco fixture happens to be a deceased Synthea patient
    (deceasedDateTime=1988-09-22). Pin the round-trip on real
    upstream data so the loader regresses noisily if the parser
    silently stops reading the field."""
    assert francisco.deceased_date == date(1988, 9, 22)


def test_deceased_boolean_only_falls_back_to_birth_date() -> None:
    """Defensive path for FHIR bundles that record death as a boolean
    without a date. The loader logs and treats the patient as
    deceased on `birth_date` so the scoring guard still fires; if real
    Synthea data ever does this, we'll need to revisit."""
    bundle = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "gender": "male",
                    "birthDate": "1960-04-10",
                    "deceasedBoolean": True,
                }
            }
        ]
    }
    patient = _patient_from_bundle(bundle)
    assert patient.deceased_date == date(1960, 4, 10)


def test_blood_pressure_panel_emits_systolic_and_diastolic_components() -> None:
    """Synthea encodes BP as a panel (LOINC 85354-9) with no top-level value;
    systolic (8480-6) and diastolic (8462-4) live in `component[]`. The
    loader must expand the panel into component-level observations or the
    matcher will think the patient has no BP."""
    fabricated = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "gender": "female",
                    "birthDate": "1970-01-01",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "bp1",
                    "effectiveDateTime": "2024-06-01T00:00:00Z",
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "85354-9",
                                "display": "Blood pressure panel",
                            }
                        ]
                    },
                    "component": [
                        {
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "8480-6",
                                        "display": "Systolic blood pressure",
                                    }
                                ]
                            },
                            "valueQuantity": {"value": 132, "unit": "mm[Hg]"},
                        },
                        {
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "8462-4",
                                        "display": "Diastolic blood pressure",
                                    }
                                ]
                            },
                            "valueQuantity": {"value": 84, "unit": "mm[Hg]"},
                        },
                    ],
                }
            },
        ]
    }
    p = _patient_from_bundle(fabricated)
    assert len(p.observations) == 2
    by_code = {o.concept.code: o for o in p.observations}
    assert by_code["8480-6"].value == 132.0
    assert by_code["8480-6"].unit == "mm[Hg]"
    assert by_code["8462-4"].value == 84.0
    assert by_code["8480-6"].effective_date == date(2024, 6, 1)


def test_observation_drops_components_missing_value() -> None:
    """Defensive: a panel with one missing component still yields the others,
    not a crash and not a phantom row."""
    fabricated = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p2",
                    "gender": "male",
                    "birthDate": "1970-01-01",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "bp2",
                    "effectiveDateTime": "2024-06-01",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9"}]},
                    "component": [
                        {
                            "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]},
                            "valueQuantity": {"value": 140, "unit": "mm[Hg]"},
                        },
                        {
                            "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4"}]},
                            # no valueQuantity
                        },
                    ],
                }
            },
        ]
    }
    p = _patient_from_bundle(fabricated)
    assert len(p.observations) == 1
    assert p.observations[0].concept.code == "8480-6"


def test_document_reference_attachment_data_loads_as_clinical_note() -> None:
    encoded = base64.b64encode(b"Cardiology note: patient has uncontrolled hypertension.").decode(
        "ascii"
    )
    fabricated = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "gender": "female",
                    "birthDate": "1970-01-01",
                }
            },
            {
                "resource": {
                    "resourceType": "DocumentReference",
                    "id": "doc1",
                    "date": "2024-06-01T09:30:00Z",
                    "type": {"text": "Progress note"},
                    "content": [
                        {
                            "attachment": {
                                "contentType": "text/plain; charset=utf-8",
                                "data": encoded,
                            }
                        }
                    ],
                }
            },
        ]
    }

    patient = _patient_from_bundle(fabricated)

    assert len(patient.notes) == 1
    assert patient.notes[0].note_id == "doc1:0"
    assert patient.notes[0].date == date(2024, 6, 1)
    assert patient.notes[0].title == "Progress note"
    assert patient.notes[0].text == "Cardiology note: patient has uncontrolled hypertension."


def test_document_reference_ignores_generated_text_div() -> None:
    fabricated = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "gender": "female",
                    "birthDate": "1970-01-01",
                }
            },
            {
                "resource": {
                    "resourceType": "DocumentReference",
                    "id": "doc1",
                    "date": "2024-06-01T09:30:00Z",
                    "text": {
                        "status": "generated",
                        "div": "<div>Patient has cancer in generated narrative.</div>",
                    },
                    "content": [{"attachment": {"contentType": "text/plain"}}],
                }
            },
        ]
    }

    patient = _patient_from_bundle(fabricated)

    assert patient.notes == []
