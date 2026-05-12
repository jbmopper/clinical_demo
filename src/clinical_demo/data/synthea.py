"""Synthea FHIR R4 → domain model loader.

Synthea sample data ships as one FHIR `Bundle` (transaction) per patient, in
a single JSON file. This module loads such files and translates them into
our internal `Patient` model.

Notes on Synthea quirks (as of the Nov 2021 sample release, which is the
current FHIR R4 sample artifact even though Synthea itself has had
generator-side updates since):

- All resources are referenced via `urn:uuid:<id>` *within* the bundle. We
  build a UUID → resource index to resolve `MedicationRequest.medicationReference`.
- `Condition` is overloaded with social findings (e.g., "Received higher
  education"). We mark these `is_clinical=False` based on the FHIR category
  `social-history`. *Caveat*: Synthea categorizes many social findings as
  `encounter-diagnosis` instead, so this filter is necessary but not
  sufficient. Refining the clinical-vs-social split is a downstream
  matcher concern (codelist filter, SNOMED hierarchy walk, or
  reasoner-side judgment).
- Most Observations carry a single top-level `valueQuantity`. Panels
  (e.g., blood pressure under LOINC 85354-9) carry no top-level value
  and instead nest their measurements under `component[]`, each with
  its own LOINC code and `valueQuantity`. We expand panels into one
  `LabObservation` per component so downstream code can ask for
  systolic (8480-6) or diastolic (8462-4) by LOINC like any other lab.
  Pure categorical observations (no value, no components) are dropped.
- Race and ethnicity are encoded as US-Core extensions and intentionally
  not surfaced in v0; add when a downstream eligibility criterion needs them.
- `abatementDateTime` is rarely populated in the sample data, meaning most
  conditions are reported as still active. Eligibility logic handles this
  by treating `abatement_date is None` as "still active."
- `DocumentReference.content.attachment.data` is surfaced as unstructured
  `ClinicalNote` text. Generated `resource.text.div` narrative is ignored
  because it is display markup, not a high-trust clinical evidence field.
- Completed FHIR `Procedure` resources are surfaced as dated procedure-history
  rows so procedure/surgical-history criteria can be executed separately from
  diagnosis/Condition evidence.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections.abc import Iterator
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from clinical_demo.domain import (
    ClinicalNote,
    CodedConcept,
    Condition,
    LabObservation,
    Medication,
    Patient,
    Procedure,
    Sex,
)

logger = logging.getLogger(__name__)

# FHIR systems we recognize. Synthea uses these consistently.
_LOINC = "http://loinc.org"
_SNOMED = "http://snomed.info/sct"
_RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"

# Condition category codes
_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-category"
_NON_CLINICAL_CATEGORIES = {"social-history"}


def load_bundle(path: Path | str) -> Patient:
    """Load a single Synthea FHIR bundle (one patient) from a JSON file."""
    path = Path(path)
    with path.open() as f:
        bundle = json.load(f)
    return _patient_from_bundle(bundle)


def iter_bundles(directory: Path | str) -> Iterator[Patient]:
    """Yield Patient objects for every patient bundle in `directory`.

    Synthea's sample-data dump mixes patient bundles with sibling
    `hospitalInformation*.json` / `practitionerInformation*.json` files
    that contain only Organization/Practitioner resources. Files without
    a Patient resource are skipped with a debug log; everything else is
    parsed strictly.

    Files are visited in sorted order so iteration is deterministic.
    """
    directory = Path(directory)
    for path in sorted(directory.glob("*.json")):
        try:
            yield load_bundle(path)
        except ValueError as e:
            if "missing a Patient resource" in str(e):
                logger.debug("skipping non-patient bundle: %s", path.name)
                continue
            raise


# ---------- internals ----------


def _patient_from_bundle(bundle: dict[str, Any]) -> Patient:
    entries = bundle.get("entry", [])
    if not entries:
        raise ValueError("bundle has no entries")

    # Build UUID → resource index for intra-bundle reference resolution.
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        resource = entry["resource"]
        rid = resource.get("id")
        if rid:
            by_id[rid] = resource

    patient_resource = _find_one(entries, "Patient")

    return Patient(
        patient_id=patient_resource["id"],
        birth_date=date.fromisoformat(patient_resource["birthDate"]),
        sex=_parse_sex(patient_resource.get("gender")),
        deceased_date=_parse_deceased(patient_resource),
        conditions=[
            _parse_condition(e["resource"])
            for e in entries
            if e["resource"]["resourceType"] == "Condition"
        ],
        observations=[
            obs
            for e in entries
            if e["resource"]["resourceType"] == "Observation"
            for obs in _parse_observation(e["resource"])
        ],
        medications=[
            med
            for e in entries
            if e["resource"]["resourceType"] == "MedicationRequest"
            for med in [_parse_medication_request(e["resource"], by_id)]
            if med is not None
        ],
        procedures=[
            procedure
            for e in entries
            if e["resource"]["resourceType"] == "Procedure"
            for procedure in [_parse_procedure(e["resource"])]
            if procedure is not None
        ],
        notes=[
            note
            for e in entries
            if e["resource"]["resourceType"] == "DocumentReference"
            for note in _parse_document_reference(e["resource"])
        ],
    )


def _find_one(entries: list[dict[str, Any]], resource_type: str) -> dict[str, Any]:
    for entry in entries:
        r = entry["resource"]
        if r["resourceType"] == resource_type:
            return r
    raise ValueError(f"bundle is missing a {resource_type} resource")


def _parse_sex(gender: str | None) -> Sex:
    """FHIR uses `gender` (administrative); we expose it as `sex` for clinical clarity."""
    if gender in {"male", "female", "other", "unknown"}:
        return gender  # type: ignore[return-value]
    return "unknown"


def _parse_date(value: str | None) -> date | None:
    """Parse a FHIR dateTime or date into a `date` (drops time/zone)."""
    if not value:
        return None
    return datetime.fromisoformat(value).date()


def _parse_deceased(patient_resource: dict[str, Any]) -> date | None:
    """Resolve `Patient.deceased[x]` into a `date | None`.

    Synthea consistently uses `deceasedDateTime` when generating dead
    patients; we don't currently encounter `deceasedBoolean`. If a
    bundle ever ships with `deceasedBoolean=true` and no date, treat
    it as deceased on `birth_date` (the most conservative possible
    "the patient was already deceased by any plausible eligibility
    `as_of`") and log a warning so we notice and add real handling.
    """
    if "deceasedDateTime" in patient_resource:
        return _parse_date(patient_resource["deceasedDateTime"])
    if patient_resource.get("deceasedBoolean") is True:
        logger.warning(
            "patient %s has deceasedBoolean=true but no deceasedDateTime; "
            "treating as deceased on birth_date for safety. Capture a real "
            "date in the source bundle if possible.",
            patient_resource.get("id"),
        )
        return date.fromisoformat(patient_resource["birthDate"])
    return None


def _parse_concept(coding_owner: dict[str, Any]) -> CodedConcept:
    """Pick the first coding from a CodeableConcept.

    Synthea uses a single coding per concept in the resources we consume.
    If/when a source emits multiple codings we'll need a system-priority list.
    """
    codings = coding_owner.get("coding") or []
    if not codings:
        return CodedConcept(system="", code="", display=coding_owner.get("text"))
    first = codings[0]
    return CodedConcept(
        system=first.get("system", ""),
        code=first.get("code", ""),
        display=first.get("display") or coding_owner.get("text"),
    )


def _parse_condition(resource: dict[str, Any]) -> Condition:
    is_clinical = True
    for cat in resource.get("category", []):
        for coding in cat.get("coding", []):
            if (
                coding.get("system") == _CATEGORY_SYSTEM
                and coding.get("code") in _NON_CLINICAL_CATEGORIES
            ):
                is_clinical = False
    return Condition(
        concept=_parse_concept(resource["code"]),
        onset_date=_parse_date(resource.get("onsetDateTime")),
        abatement_date=_parse_date(resource.get("abatementDateTime")),
        is_clinical=is_clinical,
    )


def _parse_observation(resource: dict[str, Any]) -> list[LabObservation]:
    """Translate one FHIR Observation into zero or more `LabObservation`s.

    Returns:
    - One `LabObservation` if the observation has a top-level `valueQuantity`
      (the common case for single-value labs like HbA1c, LDL, eGFR).
    - One `LabObservation` per `component` entry that has its own
      `valueQuantity` (the panel case, e.g. BP packs systolic and diastolic
      under a single 85354-9 wrapper). The wrapper itself is *not* emitted —
      panels rarely have a meaningful aggregate value; downstream code
      asks for the components by LOINC.
    - An empty list for purely categorical observations or those missing
      an effective date.
    """
    eff = _parse_date(resource.get("effectiveDateTime"))
    if eff is None:
        return []

    vq = resource.get("valueQuantity")
    if vq and "value" in vq:
        return [
            LabObservation(
                concept=_parse_concept(resource["code"]),
                value=float(vq["value"]),
                unit=vq.get("unit", ""),
                effective_date=eff,
            )
        ]

    out: list[LabObservation] = []
    for comp in resource.get("component", []):
        cvq = comp.get("valueQuantity")
        if not cvq or "value" not in cvq:
            continue
        out.append(
            LabObservation(
                concept=_parse_concept(comp["code"]),
                value=float(cvq["value"]),
                unit=cvq.get("unit", ""),
                effective_date=eff,
            )
        )
    return out


def _parse_medication_request(
    resource: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
) -> Medication | None:
    """Translate a MedicationRequest into a Medication.

    Synthea may use either `medicationCodeableConcept` (inline) or
    `medicationReference` (pointer to a sibling Medication resource).
    Returns None if the medication concept cannot be resolved.
    """
    concept_owner: dict[str, Any] | None = None
    if "medicationCodeableConcept" in resource:
        concept_owner = resource["medicationCodeableConcept"]
    elif "medicationReference" in resource:
        ref = resource["medicationReference"].get("reference", "")
        # urn:uuid:abcd-... → abcd-...
        rid = ref.split(":")[-1]
        med_resource = by_id.get(rid)
        if med_resource is not None:
            concept_owner = med_resource.get("code")

    if concept_owner is None:
        return None

    start = _parse_date(resource.get("authoredOn"))
    if start is None:
        return None

    return Medication(
        concept=_parse_concept(concept_owner),
        start_date=start,
        end_date=None,  # Synthea MedicationRequest does not record a stop in v0 scope
    )


def _parse_procedure(resource: dict[str, Any]) -> Procedure | None:
    performed = _parse_procedure_date(resource)
    if performed is None:
        return None
    code = resource.get("code")
    if not isinstance(code, dict):
        return None
    return Procedure(
        concept=_parse_concept(code),
        performed_date=performed,
        status=str(resource.get("status") or "unknown"),
    )


def _parse_procedure_date(resource: dict[str, Any]) -> date | None:
    if "performedDateTime" in resource:
        return _parse_date(resource.get("performedDateTime"))
    period = resource.get("performedPeriod")
    if isinstance(period, dict):
        return _parse_date(period.get("end")) or _parse_date(period.get("start"))
    return None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def _parse_document_reference(resource: dict[str, Any]) -> list[ClinicalNote]:
    """Translate base64 DocumentReference attachments into clinical notes.

    v0 intentionally reads only `content[].attachment.data`. FHIR narrative
    markup in `resource.text.div` can be generated/display-only and should
    not become high-trust patient evidence.
    """

    notes: list[ClinicalNote] = []
    doc_id = resource.get("id") or "document-reference"
    note_date = _parse_date(resource.get("date"))
    title = _document_reference_title(resource)

    for index, content in enumerate(resource.get("content", [])):
        attachment = content.get("attachment") or {}
        encoded = attachment.get("data")
        if not encoded:
            continue
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, TypeError):
            logger.warning("skipping invalid DocumentReference attachment data: %s", doc_id)
            continue

        content_type = attachment.get("contentType")
        text = raw.decode("utf-8", errors="replace")
        if content_type and "html" in content_type.lower():
            text = _strip_html(text)
        text = _normalize_note_text(text)
        if not text:
            continue

        notes.append(
            ClinicalNote(
                note_id=f"{doc_id}:{index}",
                text=text,
                date=note_date,
                content_type=content_type,
                title=title,
            )
        )
    return notes


def _document_reference_title(resource: dict[str, Any]) -> str | None:
    if resource.get("description"):
        return str(resource["description"])
    doc_type = resource.get("type") or {}
    if doc_type.get("text"):
        return str(doc_type["text"])
    codings = doc_type.get("coding") or []
    if codings and codings[0].get("display"):
        return str(codings[0]["display"])
    return None


def _strip_html(text: str) -> str:
    parser = _TextExtractor()
    parser.feed(text)
    return parser.text()


def _normalize_note_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()
