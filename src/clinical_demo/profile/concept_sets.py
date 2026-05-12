"""Curated concept sets for the matcher and the eval seed labeler.

**Status: legacy curated code lists.** D-69 adds the first NLM API
client for VSAC value-set expansion, but these constants remain the
matcher-wired source of truth until a terminology resolver is wired
through `concept_lookup.py` and the eval harness.

A `ConceptSet` is a *named* group of coded concepts (SNOMED conditions,
LOINC labs, RxNorm meds). The matcher uses these to answer questions
like "does the patient have any T2DM-coded condition" without
hard-coding code lists everywhere.

Keep this file small and curated. We expand it deliberately when a
new criterion type appears in our seed-set or in a real trial we care
about — not preemptively. The point is auditability: a reviewer can
read this file in a minute and see exactly which codes the matcher
treats as evidence of which clinical concept.
"""

from __future__ import annotations

from clinical_demo.profile.profile import ConceptSet

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"

# ---- conditions (SNOMED) ----

T2DM = ConceptSet(
    name="Type 2 diabetes mellitus",
    system=SNOMED,
    codes=frozenset(
        {
            "44054006",  # Diabetes mellitus type 2
            "73211009",  # Diabetes mellitus (unspecified) — Synthea uses this
        }
    ),
)

T1DM = ConceptSet(
    name="Type 1 diabetes mellitus",
    system=SNOMED,
    codes=frozenset({"46635009"}),  # Diabetes mellitus type 1
)

PREDIABETES = ConceptSet(
    name="Prediabetes",
    system=SNOMED,
    codes=frozenset({"15777000"}),
)

HYPERTENSION = ConceptSet(
    name="Essential hypertension",
    system=SNOMED,
    codes=frozenset(
        {
            "59621000",  # Essential hypertension
            "38341003",  # Hypertensive disorder
        }
    ),
)

HYPERLIPIDEMIA = ConceptSet(
    name="Hyperlipidemia",
    system=SNOMED,
    codes=frozenset(
        {
            "55822004",  # Hyperlipidemia
            "267432004",  # Pure hypercholesterolemia
        }
    ),
)

CHRONIC_KIDNEY_DISEASE = ConceptSet(
    name="Chronic kidney disease",
    system=SNOMED,
    codes=frozenset(
        {
            "431855005",  # Chronic kidney disease stage 1
            "431856006",  # Chronic kidney disease stage 2
            "433144002",  # Chronic kidney disease stage 3
            "431857002",  # Chronic kidney disease stage 4
            "433146000",  # Chronic kidney disease stage 5
        }
    ),
)

CKD_STAGE_3_OR_4 = ConceptSet(
    name="Chronic kidney disease stage 3 or 4",
    system=SNOMED,
    codes=frozenset(
        {
            "433144002",  # Chronic kidney disease stage 3
            "431857002",  # Chronic kidney disease stage 4
        }
    ),
)

FRACTURE = ConceptSet(
    name="Bone fracture",
    system=SNOMED,
    codes=frozenset(
        {
            "263102004",  # Fracture subluxation of wrist
            "65966004",  # Fracture of forearm
            "16114001",  # Fracture of ankle
            "58150001",  # Fracture of clavicle
            "443165006",  # Pathological fracture due to osteoporosis (disorder)
            "359817006",  # Closed fracture of hip
            "33737001",  # Fracture of rib
        }
    ),
)

# ---- labs (LOINC) ----
# These are *single-code* sets at v0 — included as ConceptSets for API
# uniformity with conditions; expand to multi-code synonyms only if we
# see a real trial demanding them.

HBA1C = ConceptSet(
    name="HbA1c (hemoglobin A1c)",
    system=LOINC,
    codes=frozenset({"4548-4"}),
)

LDL_CHOLESTEROL = ConceptSet(
    name="LDL cholesterol",
    system=LOINC,
    codes=frozenset({"18262-6"}),
)

EGFR = ConceptSet(
    name="Estimated glomerular filtration rate (eGFR)",
    system=LOINC,
    codes=frozenset({"33914-3"}),
)

BMI = ConceptSet(
    name="Body mass index",
    system=LOINC,
    codes=frozenset({"39156-5"}),
)

HEMOGLOBIN = ConceptSet(
    name="Hemoglobin",
    system=LOINC,
    codes=frozenset({"718-7"}),
)

PLATELET_COUNT = ConceptSet(
    name="Platelet count",
    system=LOINC,
    codes=frozenset({"777-3"}),
)

C_PEPTIDE = ConceptSet(
    name="C-peptide",
    system=LOINC,
    codes=frozenset({"1986-9"}),
)

ASPARTATE_AMINOTRANSFERASE = ConceptSet(
    name="Aspartate aminotransferase",
    system=LOINC,
    codes=frozenset({"1920-8"}),
)

ALANINE_AMINOTRANSFERASE = ConceptSet(
    name="Alanine aminotransferase",
    system=LOINC,
    codes=frozenset({"1742-6"}),
)

TOTAL_BILIRUBIN = ConceptSet(
    name="Total bilirubin",
    system=LOINC,
    codes=frozenset({"1975-2"}),
)

ABSOLUTE_NEUTROPHIL_COUNT = ConceptSet(
    name="Absolute neutrophil count",
    system=LOINC,
    codes=frozenset({"751-8"}),
)

SERUM_CREATININE = ConceptSet(
    name="Serum creatinine",
    system=LOINC,
    codes=frozenset({"38483-4"}),
)

GLUCOSE = ConceptSet(
    name="Glucose",
    system=LOINC,
    codes=frozenset({"2339-0"}),
)

TRIGLYCERIDES = ConceptSet(
    name="Triglycerides",
    system=LOINC,
    codes=frozenset({"2571-8"}),
)

SYSTOLIC_BP = ConceptSet(
    name="Systolic blood pressure",
    system=LOINC,
    codes=frozenset({"8480-6"}),
)

DIASTOLIC_BP = ConceptSet(
    name="Diastolic blood pressure",
    system=LOINC,
    codes=frozenset({"8462-4"}),
)

# ---- medications (RxNorm) ----
#
# These sets are intentionally closed over the current committed Synthea
# patient vocabulary. Broader ingredient/class expansion belongs in the
# terminology compiler layer; these constants are the executable code anchors
# for reviewed medication surfaces and class members.

METFORMIN = ConceptSet(
    name="Metformin",
    system=RXNORM,
    codes=frozenset({"860975"}),  # 24 HR Metformin hydrochloride 500 MG ER Oral Tablet
)

INSULIN = ConceptSet(
    name="Insulin",
    system=RXNORM,
    codes=frozenset(
        {
            "106892",  # Humulin 70/30 Synthea representative
        }
    ),
)

ATORVASTATIN = ConceptSet(
    name="Atorvastatin",
    system=RXNORM,
    codes=frozenset({"259255"}),  # Atorvastatin 80 MG Oral Tablet
)

SIMVASTATIN = ConceptSet(
    name="Simvastatin",
    system=RXNORM,
    codes=frozenset(
        {
            "314231",  # Simvastatin 10 MG Oral Tablet
            "312961",  # Simvastatin 20 MG Oral Tablet
        }
    ),
)

ALENDRONIC_ACID = ConceptSet(
    name="Alendronic acid",
    system=RXNORM,
    codes=frozenset({"904419"}),  # Alendronic acid 10 MG Oral Tablet
)

LISINOPRIL = ConceptSet(
    name="Lisinopril",
    system=RXNORM,
    codes=frozenset(
        {
            "314076",  # Lisinopril 10 MG Oral Tablet
            "314077",  # Lisinopril 20 MG Oral Tablet
        }
    ),
)

LOSARTAN = ConceptSet(
    name="Losartan",
    system=RXNORM,
    codes=frozenset({"979492"}),  # Losartan potassium 50 MG Oral Tablet
)

CONCEPT_SETS_BY_ID: dict[str, ConceptSet] = {
    "ABSOLUTE_NEUTROPHIL_COUNT": ABSOLUTE_NEUTROPHIL_COUNT,
    "ALENDRONIC_ACID": ALENDRONIC_ACID,
    "ALANINE_AMINOTRANSFERASE": ALANINE_AMINOTRANSFERASE,
    "ASPARTATE_AMINOTRANSFERASE": ASPARTATE_AMINOTRANSFERASE,
    "ATORVASTATIN": ATORVASTATIN,
    "BMI": BMI,
    "CHRONIC_KIDNEY_DISEASE": CHRONIC_KIDNEY_DISEASE,
    "CKD_STAGE_3_OR_4": CKD_STAGE_3_OR_4,
    "C_PEPTIDE": C_PEPTIDE,
    "DIASTOLIC_BP": DIASTOLIC_BP,
    "EGFR": EGFR,
    "FRACTURE": FRACTURE,
    "GLUCOSE": GLUCOSE,
    "HBA1C": HBA1C,
    "HEMOGLOBIN": HEMOGLOBIN,
    "HYPERLIPIDEMIA": HYPERLIPIDEMIA,
    "HYPERTENSION": HYPERTENSION,
    "INSULIN": INSULIN,
    "LDL_CHOLESTEROL": LDL_CHOLESTEROL,
    "LISINOPRIL": LISINOPRIL,
    "LOSARTAN": LOSARTAN,
    "METFORMIN": METFORMIN,
    "PLATELET_COUNT": PLATELET_COUNT,
    "PREDIABETES": PREDIABETES,
    "SERUM_CREATININE": SERUM_CREATININE,
    "SIMVASTATIN": SIMVASTATIN,
    "SYSTOLIC_BP": SYSTOLIC_BP,
    "T1DM": T1DM,
    "T2DM": T2DM,
    "TOTAL_BILIRUBIN": TOTAL_BILIRUBIN,
    "TRIGLYCERIDES": TRIGLYCERIDES,
}


def concept_set_by_id(concept_set_id: str | None) -> ConceptSet | None:
    """Return a project ConceptSet referenced by reviewed registry id."""

    if concept_set_id is None:
        return None
    return CONCEPT_SETS_BY_ID.get(concept_set_id)


__all__ = [
    "ABSOLUTE_NEUTROPHIL_COUNT",
    "ALANINE_AMINOTRANSFERASE",
    "ALENDRONIC_ACID",
    "ASPARTATE_AMINOTRANSFERASE",
    "ATORVASTATIN",
    "BMI",
    "CHRONIC_KIDNEY_DISEASE",
    "CKD_STAGE_3_OR_4",
    "CONCEPT_SETS_BY_ID",
    "C_PEPTIDE",
    "DIASTOLIC_BP",
    "EGFR",
    "FRACTURE",
    "GLUCOSE",
    "HBA1C",
    "HEMOGLOBIN",
    "HYPERLIPIDEMIA",
    "HYPERTENSION",
    "INSULIN",
    "LDL_CHOLESTEROL",
    "LISINOPRIL",
    "LOSARTAN",
    "METFORMIN",
    "PLATELET_COUNT",
    "PREDIABETES",
    "RXNORM",
    "SERUM_CREATININE",
    "SIMVASTATIN",
    "SYSTOLIC_BP",
    "T1DM",
    "T2DM",
    "TOTAL_BILIRUBIN",
    "TRIGLYCERIDES",
    "concept_set_by_id",
]
