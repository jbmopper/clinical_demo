Public-Artifact-Safety: synthetic

# Run Movement Review

- baseline: `e8efb7bcce35`
- comparison: `f77c112ef220`
- changed cases: 9/49
- changed criteria: 362/1076
- criterion directions: determinate_changed=1 / indeterminate_to_determinate=64 / reason_changed=297

## Case Movements

| Pair | Slice | Baseline | Comparison |
|---|---|---:|---:|
| `2e555528__NCT06475781` | hypertension-industry | indeterminate | fail |
| `3a364909__NCT07362459` | nsclc | indeterminate | fail |
| `407ef75b__NCT06941441` | hypertension-academic | indeterminate | fail |
| `56cfe6a5__NCT06475781` | hypertension-industry | indeterminate | fail |
| `56cfe6a5__NCT06941441` | hypertension-academic | indeterminate | fail |
| `83f922a9__NCT05967689` | nsclc | indeterminate | pass_pending_review |
| `9cbf47d8__NCT07362459` | nsclc | indeterminate | fail |
| `a06bce31__NCT06941441` | hypertension-academic | indeterminate | fail |
| `e7d52393__NCT06568471` | hyperlipidemia | indeterminate | fail |

## Criterion Movements

| Pair | # | Kind | Movement | Direction | Compiled predicate | Source |
|---|---:|---|---|---|---|---|
| `060e72d3__NCT05713006` | 2 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Pathologically confirmed diagnosis of NSCLC |
| `060e72d3__NCT05713006` | 3 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Stage IIIB - IV by the American Joint Committee of Cancer Version 8. |
| `060e72d3__NCT05713006` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Recurrent disease (at least 180 days from curative intent treatment) |
| `060e72d3__NCT05713006` | 5 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | ALK rearrangements tested by FDA-approved tests (IHQ or FISH) |
| `060e72d3__NCT05713006` | 6 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Karnofsky PS scale ≥ 70% |
| `060e72d3__NCT05713006` | 8 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Measurable disease as referred by RECIST version 1.1 |
| `060e72d3__NCT05713006` | 9 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Symptomatic brain metastases could receive prior treatment with radiotherapy or surgery for at le... |
| `060e72d3__NCT05713006` | 10 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Asymptomatic brain metastases could not receive local therapy before study inclusion. |
| `060e72d3__NCT05713006` | 11 | condition_absent | indeterminate->pass | indeterminate_to_determinate | condition_presence | Negative highly sensitive pregnancy test (serum or urine) within 72 days before first dose interv... |
| `060e72d3__NCT05713006` | 14 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Adequate organ function (hematological, liver, and renal function) |
| `060e72d3__NCT05713006` | 15 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Life expectancy of at least 12 weeks |
| `060e72d3__NCT05713006` | 21 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Active hepatitis virus infection (any serotype) or chronic infection with a potential risk of rea... |
| `060e72d3__NCT05713006` | 22 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Active HIV infection. |
| `060e72d3__NCT05713006` | 23 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Breastfeeding. |
| `1293efbb__NCT06524960` | 6 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Serum calcium (corrected for albumin) within normal limits per site's local lab |
| `1293efbb__NCT06524960` | 10 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Vitamin D3 deficiency (< 30 ng/ml) |
| `1293efbb__NCT06524960` | 16 | free_text | indeterminate->indeterminate | reason_changed | compound | Treatment with any of the following drugs in past year: immunosuppressants, anticonvulsant therap... |
| `1293efbb__NCT06964087` | 3 | free_text | indeterminate->fail | indeterminate_to_determinate | condition_presence | Diagnosis of T1DM within the last 20 years for Part A, within 1 to 10 years [N=15 at >5 to 10, N=... |
| `1293efbb__NCT06964087` | 4 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | For Parts B and C only, T-cell phenotype Th40 level greater than or equal to 35% of CD3+ leukocyt... |
| `1293efbb__NCT06964087` | 12 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | Patients with a history of venous and arterial thromboembolic events including, but not limited t... |
| `28db1c55__NCT06941441` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Baseline RHC performed during the Screening Period documenting a minimum PVR of ≥ 5 WU and a pulm... |
| `28db1c55__NCT06941441` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Receiving stable background therapy for PAH for >90 days and will continue receiving throughout t... |
| `28db1c55__NCT06941441` | 9 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Diagnosis of PH WHO Groups 2, 3, 4, or 5 |
| `28db1c55__NCT06941441` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Hemoglobin at screening above gender-specific ULN |
| `28db1c55__NCT06941441` | 13 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | Uncontrolled systemic hypertension as evidenced by sitting systolic BP > 160 mmHg or sitting dias... |
| `28db1c55__NCT06941441` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Pregnant or breastfeeding females |
| `28db1c55__NCT06941441` | 16 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Currently enrolled in or have completed any other investigational product study within 30 days fo... |
| `28db1c55__NCT06941441` | 18 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of full pneumonectomy |
| `28db1c55__NCT06941441` | 22 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Cerebrovascular accident within 3 months prior to the screening visit |
| `28db1c55__NCT06941441` | 23 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Acutely decompensated heart failure within 14 days prior to the screening visit, as per investiga... |
| `28db1c55__NCT06941441` | 24 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Significant (≥ 2+ regurgitation) mitral regurgitation or aortic regurgitation valvular disease |
| `28db1c55__NCT06941441` | 25 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Received intravenous inotropes (e.g., dobutamine, dopamine, norepinephrine, vasopressin) within 3... |
| `28db1c55__NCT07297797` | 4 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | the 24-hour mean systolic blood pressure assessed by ABPM at Screening is ≥ 130 mmHg and < 160 mmHg. |
| `28db1c55__NCT07297797` | 8 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Occurrence of any cardiovascular or cerebrovascular event within 6 months prior to screening; |
| `28db1c55__NCT07297797` | 9 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Presence of uncontrolled severe arrhythmia within 6 months prior to screening; |
| `28db1c55__NCT07297797` | 11 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Other diseases requiring Renin-Angiotensin-Aldosterone System (RAAS) inhibitor therapy, besides h... |
| `28db1c55__NCT07297797` | 13 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Use of any medication affecting blood pressure within 4 weeks prior to screening, or planned use... |
| `2e555528__NCT06475781` | 0 | condition_present | indeterminate->fail | indeterminate_to_determinate | compound | A clinical diagnosis of PH-ILD. |
| `2e555528__NCT06475781` | 9 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Subjects must have a baseline 6-minute walk distance ≥100 meters and ≤500 meters. |
| `2e555528__NCT06475781` | 14 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Subjects must have clinical laboratory values within normal ranges or <1.5 times the upper limit... |
| `2e555528__NCT06475781` | 15 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Pulmonary function test (PFT) showing a percent predicted forced vital capacity (FVC) <70% of pre... |
| `2e555528__NCT06475781` | 18 | condition_absent | indeterminate->pass | indeterminate_to_determinate | compound | Subject has another concomitant diagnosis of pulmonary hypertension not otherwise considered to b... |
| `2e555528__NCT06475781` | 19 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Subject has evidence of clinically significant left-sided heart disease within 6 months as define... |
| `2e555528__NCT06475781` | 21 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | The subject is receiving >10 L/min of oxygen supplementation by any mode of delivery at rest. |
| `2e555528__NCT06475781` | 25 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Any current active malignancy (this does not include localized cancers such as basal or squamous... |
| `2e555528__NCT06475781` | 27 | condition_absent | indeterminate->pass | indeterminate_to_determinate | condition_presence | The subject has a history of congenital heart disease irrespective of any prior treatment of surg... |
| `2e555528__NCT06475781` | 33 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | compound | Uncontrolled hypertension as evidenced by systolic blood pressure >160 mmHg or diastolic blood pr... |
| `2e555528__NCT06475781` | 34 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Concomitant disease that confers a life expectancy of <6 months at screening. |
| `2e555528__NCT06475781` | 37 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of liver dysfunction, including subjects with moderate (Child-Pugh B) or severe (Child Pu... |
| `2e555528__NCT06475781` | 39 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Worse than mild untreated sleep apnea (5-14.9 events/hour). Treated sleep apnea is permitted. |
| `2e555528__NCT06941441` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Baseline RHC performed during the Screening Period documenting a minimum PVR of ≥ 5 WU and a pulm... |
| `2e555528__NCT06941441` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Receiving stable background therapy for PAH for >90 days and will continue receiving throughout t... |
| `2e555528__NCT06941441` | 9 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Diagnosis of PH WHO Groups 2, 3, 4, or 5 |
| `2e555528__NCT06941441` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Hemoglobin at screening above gender-specific ULN |
| `2e555528__NCT06941441` | 13 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | Uncontrolled systemic hypertension as evidenced by sitting systolic BP > 160 mmHg or sitting dias... |
| `2e555528__NCT06941441` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Pregnant or breastfeeding females |
| `2e555528__NCT06941441` | 16 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Currently enrolled in or have completed any other investigational product study within 30 days fo... |
| `2e555528__NCT06941441` | 18 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of full pneumonectomy |
| `2e555528__NCT06941441` | 22 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Cerebrovascular accident within 3 months prior to the screening visit |
| `2e555528__NCT06941441` | 23 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Acutely decompensated heart failure within 14 days prior to the screening visit, as per investiga... |
| `2e555528__NCT06941441` | 24 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Significant (≥ 2+ regurgitation) mitral regurgitation or aortic regurgitation valvular disease |
| `2e555528__NCT06941441` | 25 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Received intravenous inotropes (e.g., dobutamine, dopamine, norepinephrine, vasopressin) within 3... |
| `38f38890__NCT06217302` | 1 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Duration of T1D ≥ 8 years; |
| `38f38890__NCT06217302` | 5 | medication_present | indeterminate->pass | indeterminate_to_determinate | medication_exposure | Receiving standard of care, including renin angiotensin system blockers (RASB) at a clinically ap... |
| `38f38890__NCT06217302` | 7 | free_text | indeterminate->fail | indeterminate_to_determinate | compound | a. Blood pressure ≤155/95 mmHg at screening, or b. BP ≤155/95 mmHg at the end of the run-in perio... |
| `38f38890__NCT06217302` | 10 | free_text | indeterminate->pass | indeterminate_to_determinate | medication_exposure | Use of any SGLT inhibitor in the previous 2 months; |
| `38f38890__NCT06217302` | 13 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Use of anti tumor necrosis factor (TNF) alpha biologic medications at screening; |
| `38f38890__NCT06217302` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Known allergies, hypersensitivity, or intolerance to SOTA; |
| `38f38890__NCT06217302` | 15 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of ≥3 severe hypoglycemic events (requiring third-party assistance for correction) within... |
| `38f38890__NCT06217302` | 17 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Blood beta-hydroxybutyrate (BHB) >0.6 mmol/L for >2 hours on >2 occasions during the Run-in period; |
| `38f38890__NCT06217302` | 18 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Inadequate beta hydroxybutyrate (BHB) testing (<50% of the prescribed measurements) during Run-in; |
| `38f38890__NCT06217302` | 19 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of primary renal glycosuria; |
| `38f38890__NCT06217302` | 20 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of biopsy-proven non-diabetic chronic kidney disease (CKD); |
| `38f38890__NCT06217302` | 24 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Cancer treatment (excluding non-melanoma skin cancer treated by excision, carcinoma in situ of th... |
| `38f38890__NCT06217302` | 25 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Illicit drug abuse within 6 months of screening; |
| `38f38890__NCT06217302` | 26 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Heavy alcohol use (for men, 5 drinks or more on any day or 15 drinks or more per week; for women,... |
| `38f38890__NCT06217302` | 27 | condition_absent | indeterminate->fail | indeterminate_to_determinate | trial_exposure | Participation in another interventional clinical research study within 30 days of screening; |
| `38f38890__NCT06217302` | 30 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Any condition that may render the patient unable to comply with study requirements and/or complet... |
| `38f38890__NCT07489209` | 1 | condition_present | indeterminate->fail | indeterminate_to_determinate | condition_presence | Genetic diagnosis or clinical diagnosis of HoFH. |
| `38f38890__NCT07489209` | 4 | medication_present | indeterminate->pass | indeterminate_to_determinate | medication_exposure | Receiving stable and tolerable lipid-lowering treatment or other drugs for chronic diseases treat... |
| `38f38890__NCT07489209` | 16 | condition_absent | indeterminate->indeterminate | reason_changed | compound | Had New York Heart Association (NYHA) grade III-IV heart failure within 12 months prior to random... |
| `38f38890__NCT07489209` | 22 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | compound | Uncontrolled hypertension at screening (blood pressure >160/100 mmHg). |
| `3a364909__NCT06220266` | 0 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Natural menopause, last menstrual period more than one year ago. |
| `3a364909__NCT06220266` | 6 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | have diabetes or uncontrolled high blood pressure, including HbA1c >9, Systolic blood pressure >1... |
| `3a364909__NCT06220266` | 8 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Ever had an organ transplant |
| `3a364909__NCT06220266` | 11 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | have other serious medical conditions that require close monitoring |
| `3a364909__NCT07362459` | 2 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | ECOG Performance Status score of 0 to 1. |
| `3a364909__NCT07362459` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | An expected survival of ≥ 3 months. |
| `3a364909__NCT07362459` | 7 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | No prior systemic anti-tumor therapy for the studied disease. |
| `3a364909__NCT07362459` | 8 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | At least one measurable non-CNS lesion according to RECIST v1.1 criteria. |
| `3a364909__NCT07362459` | 18 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | A history of arterial thrombosis, deep vein thrombosis, cerebral infarction, transient ischemic a... |
| `3a364909__NCT07362459` | 23 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | The presence of other malignant tumors. |
| `3a364909__NCT07362459` | 32 | condition_absent | indeterminate->fail | indeterminate_to_determinate | trial_exposure | Current participation in another clinical trial, with the exception of observational (non-interve... |
| `3beee40e__NCT06143566` | 0 | condition_present | indeterminate->pass | indeterminate_to_determinate | condition_presence | Patients with Type 2 DM |
| `3beee40e__NCT06143566` | 5 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Hyperkalemia > 5.0 |
| `3beee40e__NCT06143566` | 6 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Contraindication to any component of polypill |
| `3beee40e__NCT07394114` | 4 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Other types of diabetes besides T2DM. |
| `3beee40e__NCT07394114` | 5 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Acute complications of diabetes (such as diabetic ketoacidosis, diabetic lactic acidosis, or hype... |
| `3beee40e__NCT07394114` | 6 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | History of a level 3 hypoglycemic episode or a history of asymptomatic hypoglycemic episodes with... |
| `3beee40e__NCT07394114` | 7 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | History or family history of medullary thyroid carcinoma (MTC), thyroid C-cell hyperplasia, or mu... |
| `3beee40e__NCT07394114` | 9 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Investigator determines that the subject has a condition or disease affecting gastric emptying or... |
| `3beee40e__NCT07394114` | 10 | medication_absent | indeterminate->pass | indeterminate_to_determinate | medication_exposure | Use of any antidiabetic medications within 12 weeks prior to signing the ICF; excluding short-ter... |
| `3beee40e__NCT07394114` | 14 | measurement_threshold | indeterminate->indeterminate | reason_changed | compound | Aspartate aminotransferase (AST) >3× upper limit of normal (ULN) and/or alanine aminotransferase... |
| `407ef75b__NCT06941441` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Baseline RHC performed during the Screening Period documenting a minimum PVR of ≥ 5 WU and a pulm... |
| `407ef75b__NCT06941441` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Receiving stable background therapy for PAH for >90 days and will continue receiving throughout t... |
| `407ef75b__NCT06941441` | 9 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Diagnosis of PH WHO Groups 2, 3, 4, or 5 |
| `407ef75b__NCT06941441` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Hemoglobin at screening above gender-specific ULN |
| `407ef75b__NCT06941441` | 13 | free_text | indeterminate->fail | indeterminate_to_determinate | compound | Uncontrolled systemic hypertension as evidenced by sitting systolic BP > 160 mmHg or sitting dias... |
| `407ef75b__NCT06941441` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Pregnant or breastfeeding females |
| `407ef75b__NCT06941441` | 16 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Currently enrolled in or have completed any other investigational product study within 30 days fo... |
| `407ef75b__NCT06941441` | 18 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of full pneumonectomy |
| `407ef75b__NCT06941441` | 22 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Cerebrovascular accident within 3 months prior to the screening visit |
| `407ef75b__NCT06941441` | 23 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Acutely decompensated heart failure within 14 days prior to the screening visit, as per investiga... |
| `407ef75b__NCT06941441` | 24 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Significant (≥ 2+ regurgitation) mitral regurgitation or aortic regurgitation valvular disease |
| `407ef75b__NCT06941441` | 25 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Received intravenous inotropes (e.g., dobutamine, dopamine, norepinephrine, vasopressin) within 3... |
| `407ef75b__NCT07297797` | 4 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | the 24-hour mean systolic blood pressure assessed by ABPM at Screening is ≥ 130 mmHg and < 160 mmHg. |
| `407ef75b__NCT07297797` | 8 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Occurrence of any cardiovascular or cerebrovascular event within 6 months prior to screening; |
| `407ef75b__NCT07297797` | 9 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Presence of uncontrolled severe arrhythmia within 6 months prior to screening; |
| `407ef75b__NCT07297797` | 11 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Other diseases requiring Renin-Angiotensin-Aldosterone System (RAAS) inhibitor therapy, besides h... |
| `407ef75b__NCT07297797` | 13 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Use of any medication affecting blood pressure within 4 weeks prior to screening, or planned use... |
| `509f9a77__NCT06941441` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Baseline RHC performed during the Screening Period documenting a minimum PVR of ≥ 5 WU and a pulm... |
| `509f9a77__NCT06941441` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Receiving stable background therapy for PAH for >90 days and will continue receiving throughout t... |
| `509f9a77__NCT06941441` | 9 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Diagnosis of PH WHO Groups 2, 3, 4, or 5 |
| `509f9a77__NCT06941441` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Hemoglobin at screening above gender-specific ULN |
| `509f9a77__NCT06941441` | 13 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | Uncontrolled systemic hypertension as evidenced by sitting systolic BP > 160 mmHg or sitting dias... |
| `509f9a77__NCT06941441` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Pregnant or breastfeeding females |
| `509f9a77__NCT06941441` | 16 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Currently enrolled in or have completed any other investigational product study within 30 days fo... |
| `509f9a77__NCT06941441` | 18 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of full pneumonectomy |
| `509f9a77__NCT06941441` | 22 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Cerebrovascular accident within 3 months prior to the screening visit |
| `509f9a77__NCT06941441` | 23 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Acutely decompensated heart failure within 14 days prior to the screening visit, as per investiga... |
| `509f9a77__NCT06941441` | 24 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Significant (≥ 2+ regurgitation) mitral regurgitation or aortic regurgitation valvular disease |
| `509f9a77__NCT06941441` | 25 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Received intravenous inotropes (e.g., dobutamine, dopamine, norepinephrine, vasopressin) within 3... |
| `509f9a77__NCT07221513` | 0 | condition_present | indeterminate->indeterminate | reason_changed | compound | Participants with HF New York Heart Association Class II-III. |
| `509f9a77__NCT07221513` | 1 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Participants will be classified as having HFrEF (LVEF ≤ 40%) or HFpEF (LVEF >40% and ≤70%). |
| `509f9a77__NCT07221513` | 2 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Right heart catheterization (RHC) based evidence of cpcPH: |
| `509f9a77__NCT07221513` | 7 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Contraindicated to RHC that can be left in place for approximately 6 hours. |
| `509f9a77__NCT07221513` | 9 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Body mass index (BMI) >45 kg/m² at screening. |
| `55c5b8d3__NCT06128278` | 3 | medication_absent | indeterminate->indeterminate | reason_changed | medication_exposure | Use of HRT or has used HRT for <6 months prior to enrollment |
| `55c5b8d3__NCT06128278` | 4 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Advanced CKD requiring dialysis |
| `55c5b8d3__NCT06128278` | 5 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | History of kidney transplant |
| `55c5b8d3__NCT06128278` | 6 | medication_absent | indeterminate->indeterminate | reason_changed | medication_exposure | Use of immunosuppressant medications (unless taking a stable dosage for a quiescent disease) |
| `55c5b8d3__NCT06128278` | 8 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Antioxidant and/or omega-3 fatty acid use within the 2 weeks prior to testing |
| `55c5b8d3__NCT06128278` | 9 | medication_absent | indeterminate->indeterminate | reason_changed | medication_exposure | Marijuana use within 2 weeks prior to testing |
| `55c5b8d3__NCT06128278` | 10 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Consumption of soy and soy-based products 3 days prior to testing |
| `55c5b8d3__NCT06128278` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | compound | Uncontrolled hypertension in CKD group (BP>140/90 mmHg) |
| `55c5b8d3__NCT06128278` | 13 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Active infection or antibiotic therapy |
| `55c5b8d3__NCT06564324` | 1 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Have documentation of ROS1 rearrangement by a positive result |
| `55c5b8d3__NCT06564324` | 2 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Have at least 1 measurable (i.e., target) lesion by Investigator assessment per RECIST v1.1. |
| `55c5b8d3__NCT06564324` | 5 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Eastern Cooperative Oncology Group (ECOG) performance status zero (0) to 1. |
| `55c5b8d3__NCT06564324` | 6 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Minimum life expectancy of 3 months or more. |
| `55c5b8d3__NCT06564324` | 8 | measurement_threshold | indeterminate->indeterminate | reason_changed | compound | Aspartate aminotransferase (AST) and alanine aminotransferase (ALT): ≤3.0 × upper limit of normal... |
| `55c5b8d3__NCT06564324` | 9 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Serum total bilirubin: ≤1.5 × ULN (≤3.0 × ULN for participants with Gilbert syndrome). |
| `55c5b8d3__NCT06564324` | 13 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Estimated creatinine clearance (CLcr) ≥45 mL/min as calculated using the method standard for the... |
| `55c5b8d3__NCT06564324` | 14 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | All toxicities from prior anticancer therapy have resolved to ≤ Grade 1 according to the National... |
| `55c5b8d3__NCT06564324` | 16 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Previously received an investigational antineoplastic agent for NSCLC. |
| `55c5b8d3__NCT06564324` | 17 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Previously received any prior TKI, including ROS1-targeted TKIs. |
| `55c5b8d3__NCT06564324` | 20 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Had major surgery within 28 days prior to randomization. Minor surgical procedures, such as cathe... |
| `55c5b8d3__NCT06564324` | 21 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Have symptomatic CNS metastases at Screening or asymptomatic disease requiring an increasing dose... |
| `55c5b8d3__NCT06564324` | 22 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Have current spinal cord compression (symptomatic or asymptomatic and detected by radiographic im... |
| `55c5b8d3__NCT06564324` | 25 | condition_absent | indeterminate->pass | indeterminate_to_determinate | condition_presence | Have clinically significant cardiovascular diseases within 6 months prior to randomization: myoca... |
| `55c5b8d3__NCT06564324` | 27 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Have ongoing cardiac dysrhythmias of ≥CTCAE Grade 2, uncontrolled atrial fibrillation of any grad... |
| `55c5b8d3__NCT06564324` | 30 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Be pregnant or breastfeeding |
| `56cfe6a5__NCT06475781` | 0 | condition_present | indeterminate->fail | indeterminate_to_determinate | compound | A clinical diagnosis of PH-ILD. |
| `56cfe6a5__NCT06475781` | 9 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Subjects must have a baseline 6-minute walk distance ≥100 meters and ≤500 meters. |
| `56cfe6a5__NCT06475781` | 14 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Subjects must have clinical laboratory values within normal ranges or <1.5 times the upper limit... |
| `56cfe6a5__NCT06475781` | 15 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Pulmonary function test (PFT) showing a percent predicted forced vital capacity (FVC) <70% of pre... |
| `56cfe6a5__NCT06475781` | 18 | condition_absent | indeterminate->pass | indeterminate_to_determinate | compound | Subject has another concomitant diagnosis of pulmonary hypertension not otherwise considered to b... |
| `56cfe6a5__NCT06475781` | 19 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Subject has evidence of clinically significant left-sided heart disease within 6 months as define... |
| `56cfe6a5__NCT06475781` | 21 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | The subject is receiving >10 L/min of oxygen supplementation by any mode of delivery at rest. |
| `56cfe6a5__NCT06475781` | 25 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Any current active malignancy (this does not include localized cancers such as basal or squamous... |
| `56cfe6a5__NCT06475781` | 27 | condition_absent | indeterminate->pass | indeterminate_to_determinate | condition_presence | The subject has a history of congenital heart disease irrespective of any prior treatment of surg... |
| `56cfe6a5__NCT06475781` | 33 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | compound | Uncontrolled hypertension as evidenced by systolic blood pressure >160 mmHg or diastolic blood pr... |
| `56cfe6a5__NCT06475781` | 34 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Concomitant disease that confers a life expectancy of <6 months at screening. |
| `56cfe6a5__NCT06475781` | 37 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of liver dysfunction, including subjects with moderate (Child-Pugh B) or severe (Child Pu... |
| `56cfe6a5__NCT06475781` | 39 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Worse than mild untreated sleep apnea (5-14.9 events/hour). Treated sleep apnea is permitted. |
| `56cfe6a5__NCT06941441` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Baseline RHC performed during the Screening Period documenting a minimum PVR of ≥ 5 WU and a pulm... |
| `56cfe6a5__NCT06941441` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Receiving stable background therapy for PAH for >90 days and will continue receiving throughout t... |
| `56cfe6a5__NCT06941441` | 9 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Diagnosis of PH WHO Groups 2, 3, 4, or 5 |
| `56cfe6a5__NCT06941441` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Hemoglobin at screening above gender-specific ULN |
| `56cfe6a5__NCT06941441` | 13 | free_text | indeterminate->fail | indeterminate_to_determinate | compound | Uncontrolled systemic hypertension as evidenced by sitting systolic BP > 160 mmHg or sitting dias... |
| `56cfe6a5__NCT06941441` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Pregnant or breastfeeding females |
| `56cfe6a5__NCT06941441` | 16 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Currently enrolled in or have completed any other investigational product study within 30 days fo... |
| `56cfe6a5__NCT06941441` | 18 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of full pneumonectomy |
| `56cfe6a5__NCT06941441` | 22 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Cerebrovascular accident within 3 months prior to the screening visit |
| `56cfe6a5__NCT06941441` | 23 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Acutely decompensated heart failure within 14 days prior to the screening visit, as per investiga... |
| `56cfe6a5__NCT06941441` | 24 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Significant (≥ 2+ regurgitation) mitral regurgitation or aortic regurgitation valvular disease |
| `56cfe6a5__NCT06941441` | 25 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Received intravenous inotropes (e.g., dobutamine, dopamine, norepinephrine, vasopressin) within 3... |
| `60b0873c__NCT06220266` | 0 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Natural menopause, last menstrual period more than one year ago. |
| `60b0873c__NCT06220266` | 6 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | have diabetes or uncontrolled high blood pressure, including HbA1c >9, Systolic blood pressure >1... |
| `60b0873c__NCT06220266` | 8 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Ever had an organ transplant |
| `60b0873c__NCT06220266` | 11 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | have other serious medical conditions that require close monitoring |
| `60b0873c__NCT07224763` | 4 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Evidence of thymic involution on chest computed tomography (CT) scan with a thymic region of inte... |
| `60b0873c__NCT07224763` | 5 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Live within 3 hours travel time of the xenotransplant center. |
| `60b0873c__NCT07224763` | 7 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Negative xeno-crossmatch at Screening and pre-transplant. |
| `60b0873c__NCT07224763` | 8 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Estimated Post Transplant Survival Calculator score >20%. |
| `60b0873c__NCT07224763` | 20 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Non-renal cause of hematological disorders associated with anemia (eg, thalassemia and sickle dis... |
| `60b0873c__NCT07224763` | 21 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Cannot discontinue chronic anticoagulation therapy (low-dose daily aspirin is permissible). |
| `60b0873c__NCT07224763` | 22 | condition_present | indeterminate->pass | indeterminate_to_determinate | condition_presence | History of major psychiatric disorders with psychiatric hospitalization and/or suicidal ideation... |
| `60b0873c__NCT07224763` | 23 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Being treated for active tuberculosis (TB), have received prophylaxis for positive FDA-approved i... |
| `60b0873c__NCT07224763` | 25 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Not able to independently perform activities of daily life. |
| `60b0873c__NCT07224763` | 26 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Have a history of medical noncompliance that may preclude adherence to the demands and requiremen... |
| `83f922a9__NCT05967689` | 3 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Cohort A participants: Documented EGFR ex20ins status, as determined by local testing performed a... |
| `83f922a9__NCT05967689` | 7 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Participants with brain metastasis must be neurologically stable. |
| `83f922a9__NCT05967689` | 11 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Cohort B participants: Documented EGFR ex20ins status, as determined by local testing performed a... |
| `83f922a9__NCT05967689` | 13 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Prior adjuvant/neoadjuvant treatment for early-stage disease must have been completed >6 months p... |
| `83f922a9__NCT05967689` | 14 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Participants with brain metastasis must be neurologically stable. |
| `83f922a9__NCT05967689` | 20 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Cohort D participants: Documented other uncommon single or compound EGFR non-ex20ins status (excl... |
| `83f922a9__NCT05967689` | 21 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Participants with brain metastasis must be neurologically stable. |
| `83f922a9__NCT05967689` | 35 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Participant has received Zipalertinib (TAS6417/CLN081) at any time |
| `83f922a9__NCT05967689` | 37 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Anticancer immunotherapy ≤28 days prior to the first dose of study treatment |
| `83f922a9__NCT05967689` | 39 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Any prior treatment with an EGFR exon20ins-targeted TKI |
| `83f922a9__NCT05967689` | 40 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Participants with leptomeningeal CNS disease. |
| `83f922a9__NCT05967689` | 44 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | History of congestive heart failure (CHF) Class III/IV according to the New York Heart Associatio... |
| `83f922a9__NCT05967689` | 45 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Serious cardiac arrhythmias requiring treatment. |
| `83f922a9__NCT05967689` | 46 | free_text | indeterminate->indeterminate | reason_changed | measurement_threshold | Resting corrected QT interval (QTc) >470 msec using Fridericia's formula (QTcF). |
| `83f922a9__NCT05967689` | 49 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Adequately treated basal or squamous cell carcinoma of the skin |
| `83f922a9__NCT05967689` | 50 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Cancer in situ of the breast or cervix |
| `83f922a9__NCT05967689` | 55 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Active bleeding disorders. |
| `83f922a9__NCT05967689` | 56 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Known hypersensitivity to the ingredients in zipalertinib or any drugs similar in structure or cl... |
| `9cbf47d8__NCT07362459` | 2 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | ECOG Performance Status score of 0 to 1. |
| `9cbf47d8__NCT07362459` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | An expected survival of ≥ 3 months. |
| `9cbf47d8__NCT07362459` | 7 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | No prior systemic anti-tumor therapy for the studied disease. |
| `9cbf47d8__NCT07362459` | 8 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | At least one measurable non-CNS lesion according to RECIST v1.1 criteria. |
| `9cbf47d8__NCT07362459` | 18 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | A history of arterial thrombosis, deep vein thrombosis, cerebral infarction, transient ischemic a... |
| `9cbf47d8__NCT07362459` | 23 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | The presence of other malignant tumors. |
| `9cbf47d8__NCT07362459` | 32 | condition_absent | indeterminate->fail | indeterminate_to_determinate | trial_exposure | Current participation in another clinical trial, with the exception of observational (non-interve... |
| `9e84e569__NCT04602754` | 10 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Known hypersensitivity to the formula components used during the clinical trial; |
| `9e84e569__NCT04602754` | 14 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Participants with total cholesterol > 500 mg/dL or triglycerides > 500 mg/dL; |
| `9e84e569__NCT04602754` | 17 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Impaired hepatic function; |
| `9e84e569__NCT04602754` | 18 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Medical history of pancreatic diseases that may suggest insulin deficiency; |
| `9e84e569__NCT04602754` | 19 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | Participants who had any cardiovascular event (acute myocardial infarction, acute coronary syndro... |
| `9e84e569__NCT04602754` | 20 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Bariatric surgery in the last two years and/ or other gastrointestinal surgeries that can cause c... |
| `9e84e569__NCT04602754` | 23 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Participants with known uncontrolled hypothyroidism or TSH levels > 5 mIU/L; |
| `9e84e569__NCT04602754` | 27 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Participants using medications that may interfere with triglyceride and cholesterol metabolism st... |
| `9e84e569__NCT04602754` | 28 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Treatment with anti-obesity drugs for less than 2 months or with dose change in the last 2 months. |
| `9e84e569__NCT06524960` | 6 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Serum calcium (corrected for albumin) within normal limits per site's local lab |
| `9e84e569__NCT06524960` | 10 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Vitamin D3 deficiency (< 30 ng/ml) |
| `9e84e569__NCT06524960` | 16 | free_text | indeterminate->indeterminate | reason_changed | compound | Treatment with any of the following drugs in past year: immunosuppressants, anticonvulsant therap... |
| `9ef4db86__NCT07082114` | 7 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Evidence of acute complications of diabetes (e.g., diabetic ketoacidosis, diabetic lactosidosis,... |
| `9ef4db86__NCT07082114` | 14 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Used strong CYP3A4 or P-gp inhibitors within 14 days prior to randomization or 5 half-lives (whic... |
| `9ef4db86__NCT07082114` | 15 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Use of any glucose-lowering medication within 4 weeks prior to signing the ICF, including but not... |
| `9ef4db86__NCT07082114` | 17 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Pregnancy or lactation. |
| `9ef4db86__NCT07082114` | 19 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Enrolled in or participated in any other clinical study of drugs or medical devices within 3 mont... |
| `9ef4db86__NCT07374328` | 6 | medication_present | indeterminate->indeterminate | reason_changed | medication_exposure | Receiving glucocorticoids. |
| `a06bce31__NCT06941441` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Baseline RHC performed during the Screening Period documenting a minimum PVR of ≥ 5 WU and a pulm... |
| `a06bce31__NCT06941441` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Receiving stable background therapy for PAH for >90 days and will continue receiving throughout t... |
| `a06bce31__NCT06941441` | 9 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Diagnosis of PH WHO Groups 2, 3, 4, or 5 |
| `a06bce31__NCT06941441` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Hemoglobin at screening above gender-specific ULN |
| `a06bce31__NCT06941441` | 13 | free_text | indeterminate->fail | indeterminate_to_determinate | compound | Uncontrolled systemic hypertension as evidenced by sitting systolic BP > 160 mmHg or sitting dias... |
| `a06bce31__NCT06941441` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Pregnant or breastfeeding females |
| `a06bce31__NCT06941441` | 16 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Currently enrolled in or have completed any other investigational product study within 30 days fo... |
| `a06bce31__NCT06941441` | 18 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of full pneumonectomy |
| `a06bce31__NCT06941441` | 22 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Cerebrovascular accident within 3 months prior to the screening visit |
| `a06bce31__NCT06941441` | 23 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Acutely decompensated heart failure within 14 days prior to the screening visit, as per investiga... |
| `a06bce31__NCT06941441` | 24 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Significant (≥ 2+ regurgitation) mitral regurgitation or aortic regurgitation valvular disease |
| `a06bce31__NCT06941441` | 25 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Received intravenous inotropes (e.g., dobutamine, dopamine, norepinephrine, vasopressin) within 3... |
| `a06bce31__NCT07221513` | 0 | condition_present | indeterminate->indeterminate | reason_changed | compound | Participants with HF New York Heart Association Class II-III. |
| `a06bce31__NCT07221513` | 1 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Participants will be classified as having HFrEF (LVEF ≤ 40%) or HFpEF (LVEF >40% and ≤70%). |
| `a06bce31__NCT07221513` | 2 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Right heart catheterization (RHC) based evidence of cpcPH: |
| `a06bce31__NCT07221513` | 7 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Contraindicated to RHC that can be left in place for approximately 6 hours. |
| `a06bce31__NCT07221513` | 9 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Body mass index (BMI) >45 kg/m² at screening. |
| `a9a2c4dd__NCT05998863` | 5 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | End-stage renal failure on dialysis |
| `a9a2c4dd__NCT05998863` | 9 | condition_absent | indeterminate->fail | indeterminate_to_determinate | condition_presence | Diabetes Type II with HbA1C ≥ 7% |
| `a9a2c4dd__NCT05998863` | 11 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Required to take calcium |
| `aa01ba4c__NCT07064473` | 6 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | At least one additional risk factor for developing heart failure (HF) |
| `aa01ba4c__NCT07064473` | 7 | condition_absent | indeterminate->fail | indeterminate_to_determinate | condition_presence | History of HF or hospitalization for HF or treatment of HF |
| `aa01ba4c__NCT07064473` | 10 | medication_present | indeterminate->indeterminate | reason_changed | medication_exposure | Treatment with an Mineralocorticoid receptor antagonist (MRA) |
| `aa01ba4c__NCT07064473` | 13 | medication_present | indeterminate->indeterminate | reason_changed | medication_exposure | A direct renin inhibitor (e.g. aliskiren) |
| `aa01ba4c__NCT07064473` | 15 | medication_present | indeterminate->indeterminate | reason_changed | medication_exposure | Other aldosterone synthase inhibitors (e.g. baxdrostat) |
| `aa01ba4c__NCT07064473` | 16 | medication_present | indeterminate->indeterminate | reason_changed | medication_exposure | Systemic mineralocorticoid replacement therapy (e.g. fludrocortisone) |
| `aa01ba4c__NCT07374328` | 6 | medication_present | indeterminate->indeterminate | reason_changed | medication_exposure | Receiving glucocorticoids. |
| `c2786fee__NCT06217302` | 1 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Duration of T1D ≥ 8 years; |
| `c2786fee__NCT06217302` | 5 | medication_present | indeterminate->pass | indeterminate_to_determinate | medication_exposure | Receiving standard of care, including renin angiotensin system blockers (RASB) at a clinically ap... |
| `c2786fee__NCT06217302` | 7 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | a. Blood pressure ≤155/95 mmHg at screening, or b. BP ≤155/95 mmHg at the end of the run-in perio... |
| `c2786fee__NCT06217302` | 10 | free_text | indeterminate->pass | indeterminate_to_determinate | medication_exposure | Use of any SGLT inhibitor in the previous 2 months; |
| `c2786fee__NCT06217302` | 13 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Use of anti tumor necrosis factor (TNF) alpha biologic medications at screening; |
| `c2786fee__NCT06217302` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Known allergies, hypersensitivity, or intolerance to SOTA; |
| `c2786fee__NCT06217302` | 15 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of ≥3 severe hypoglycemic events (requiring third-party assistance for correction) within... |
| `c2786fee__NCT06217302` | 17 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Blood beta-hydroxybutyrate (BHB) >0.6 mmol/L for >2 hours on >2 occasions during the Run-in period; |
| `c2786fee__NCT06217302` | 18 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Inadequate beta hydroxybutyrate (BHB) testing (<50% of the prescribed measurements) during Run-in; |
| `c2786fee__NCT06217302` | 19 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of primary renal glycosuria; |
| `c2786fee__NCT06217302` | 20 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of biopsy-proven non-diabetic chronic kidney disease (CKD); |
| `c2786fee__NCT06217302` | 24 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Cancer treatment (excluding non-melanoma skin cancer treated by excision, carcinoma in situ of th... |
| `c2786fee__NCT06217302` | 25 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Illicit drug abuse within 6 months of screening; |
| `c2786fee__NCT06217302` | 26 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Heavy alcohol use (for men, 5 drinks or more on any day or 15 drinks or more per week; for women,... |
| `c2786fee__NCT06217302` | 27 | condition_absent | indeterminate->fail | indeterminate_to_determinate | trial_exposure | Participation in another interventional clinical research study within 30 days of screening; |
| `c2786fee__NCT06217302` | 30 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Any condition that may render the patient unable to comply with study requirements and/or complet... |
| `c2786fee__NCT06597006` | 1 | condition_present | indeterminate->fail | indeterminate_to_determinate | condition_presence | HoFH diagnosed by genetic confirmation |
| `c2786fee__NCT06597006` | 3 | medication_present | indeterminate->pass | indeterminate_to_determinate | medication_exposure | On an optimal dose of statin (investigator's discretion), unless statin intolerant, with or witho... |
| `c2786fee__NCT06597006` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Participants on lipid-lowering therapies (such as e.g. statins, ezetimibe) must be on a stable do... |
| `c2786fee__NCT06597006` | 5 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Participants on a documented regimen of LDL-apheresis for ≥ 3 months before screening will be all... |
| `c2786fee__NCT06597006` | 6 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Documented evidence of a null (negative) mutation in both LDLR alleles |
| `c2786fee__NCT06597006` | 7 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Previous treatment (within 90 days of screening) with monoclonal antibodies directed towards PCSK9 |
| `c2786fee__NCT06597006` | 11 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Heterozygous familial hypercholesterolemia (HeFH) |
| `c2786fee__NCT06597006` | 13 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Active liver disease defined as any known current infectious, neoplastic, or metabolic pathology... |
| `c46a254d__NCT06941441` | 3 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Baseline RHC performed during the Screening Period documenting a minimum PVR of ≥ 5 WU and a pulm... |
| `c46a254d__NCT06941441` | 4 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Receiving stable background therapy for PAH for >90 days and will continue receiving throughout t... |
| `c46a254d__NCT06941441` | 9 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Diagnosis of PH WHO Groups 2, 3, 4, or 5 |
| `c46a254d__NCT06941441` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Hemoglobin at screening above gender-specific ULN |
| `c46a254d__NCT06941441` | 13 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | Uncontrolled systemic hypertension as evidenced by sitting systolic BP > 160 mmHg or sitting dias... |
| `c46a254d__NCT06941441` | 14 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Pregnant or breastfeeding females |
| `c46a254d__NCT06941441` | 16 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Currently enrolled in or have completed any other investigational product study within 30 days fo... |
| `c46a254d__NCT06941441` | 18 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of full pneumonectomy |
| `c46a254d__NCT06941441` | 22 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Cerebrovascular accident within 3 months prior to the screening visit |
| `c46a254d__NCT06941441` | 23 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Acutely decompensated heart failure within 14 days prior to the screening visit, as per investiga... |
| `c46a254d__NCT06941441` | 24 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Significant (≥ 2+ regurgitation) mitral regurgitation or aortic regurgitation valvular disease |
| `c46a254d__NCT06941441` | 25 | free_text | indeterminate->indeterminate | reason_changed | condition_presence | Received intravenous inotropes (e.g., dobutamine, dopamine, norepinephrine, vasopressin) within 3... |
| `d02b2ca5__NCT06128278` | 3 | medication_absent | indeterminate->indeterminate | reason_changed | medication_exposure | Use of HRT or has used HRT for <6 months prior to enrollment |
| `d02b2ca5__NCT06128278` | 4 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Advanced CKD requiring dialysis |
| `d02b2ca5__NCT06128278` | 5 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | History of kidney transplant |
| `d02b2ca5__NCT06128278` | 6 | medication_absent | indeterminate->indeterminate | reason_changed | medication_exposure | Use of immunosuppressant medications (unless taking a stable dosage for a quiescent disease) |
| `d02b2ca5__NCT06128278` | 8 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Antioxidant and/or omega-3 fatty acid use within the 2 weeks prior to testing |
| `d02b2ca5__NCT06128278` | 9 | medication_absent | indeterminate->indeterminate | reason_changed | medication_exposure | Marijuana use within 2 weeks prior to testing |
| `d02b2ca5__NCT06128278` | 10 | free_text | indeterminate->indeterminate | reason_changed | medication_exposure | Consumption of soy and soy-based products 3 days prior to testing |
| `d02b2ca5__NCT06128278` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | compound | Uncontrolled hypertension in CKD group (BP>140/90 mmHg) |
| `d02b2ca5__NCT06128278` | 13 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Active infection or antibiotic therapy |
| `d02b2ca5__NCT07489209` | 1 | condition_present | indeterminate->fail | indeterminate_to_determinate | condition_presence | Genetic diagnosis or clinical diagnosis of HoFH. |
| `d02b2ca5__NCT07489209` | 4 | medication_present | indeterminate->pass | indeterminate_to_determinate | medication_exposure | Receiving stable and tolerable lipid-lowering treatment or other drugs for chronic diseases treat... |
| `d02b2ca5__NCT07489209` | 16 | condition_absent | indeterminate->indeterminate | reason_changed | compound | Had New York Heart Association (NYHA) grade III-IV heart failure within 12 months prior to random... |
| `d02b2ca5__NCT07489209` | 22 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | compound | Uncontrolled hypertension at screening (blood pressure >160/100 mmHg). |
| `d362f4e5__NCT06564324` | 1 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Have documentation of ROS1 rearrangement by a positive result |
| `d362f4e5__NCT06564324` | 2 | condition_present | indeterminate->indeterminate | reason_changed | condition_presence | Have at least 1 measurable (i.e., target) lesion by Investigator assessment per RECIST v1.1. |
| `d362f4e5__NCT06564324` | 5 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Eastern Cooperative Oncology Group (ECOG) performance status zero (0) to 1. |
| `d362f4e5__NCT06564324` | 6 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Minimum life expectancy of 3 months or more. |
| `d362f4e5__NCT06564324` | 8 | measurement_threshold | indeterminate->indeterminate | reason_changed | compound | Aspartate aminotransferase (AST) and alanine aminotransferase (ALT): ≤3.0 × upper limit of normal... |
| `d362f4e5__NCT06564324` | 9 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Serum total bilirubin: ≤1.5 × ULN (≤3.0 × ULN for participants with Gilbert syndrome). |
| `d362f4e5__NCT06564324` | 13 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Estimated creatinine clearance (CLcr) ≥45 mL/min as calculated using the method standard for the... |
| `d362f4e5__NCT06564324` | 14 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | All toxicities from prior anticancer therapy have resolved to ≤ Grade 1 according to the National... |
| `d362f4e5__NCT06564324` | 16 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Previously received an investigational antineoplastic agent for NSCLC. |
| `d362f4e5__NCT06564324` | 17 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Previously received any prior TKI, including ROS1-targeted TKIs. |
| `d362f4e5__NCT06564324` | 20 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Had major surgery within 28 days prior to randomization. Minor surgical procedures, such as cathe... |
| `d362f4e5__NCT06564324` | 21 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Have symptomatic CNS metastases at Screening or asymptomatic disease requiring an increasing dose... |
| `d362f4e5__NCT06564324` | 22 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Have current spinal cord compression (symptomatic or asymptomatic and detected by radiographic im... |
| `d362f4e5__NCT06564324` | 25 | condition_absent | indeterminate->pass | indeterminate_to_determinate | condition_presence | Have clinically significant cardiovascular diseases within 6 months prior to randomization: myoca... |
| `d362f4e5__NCT06564324` | 27 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Have ongoing cardiac dysrhythmias of ≥CTCAE Grade 2, uncontrolled atrial fibrillation of any grad... |
| `d362f4e5__NCT06564324` | 30 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Be pregnant or breastfeeding |
| `d57e867e__NCT06143566` | 0 | condition_present | indeterminate->pass | indeterminate_to_determinate | condition_presence | Patients with Type 2 DM |
| `d57e867e__NCT06143566` | 1 | condition_present | pass->fail | determinate_changed | condition_presence | History of chronic kidney disease, defined as an estimated glomerular filtration rate (eGFR) of 2... |
| `d57e867e__NCT06143566` | 5 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Hyperkalemia > 5.0 |
| `d57e867e__NCT06143566` | 6 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Contraindication to any component of polypill |
| `e7d52393__NCT04040959` | 4 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | compound | Blood pressure controlled to <140/90 mmHg for the past 3 months |
| `e7d52393__NCT04040959` | 7 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Patients with advanced CKD requiring chronic dialysis |
| `e7d52393__NCT04040959` | 8 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Significant co-morbid conditions that lead the investigator to conclude that life expectancy < 1... |
| `e7d52393__NCT04040959` | 9 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of severe congestive heart failure (i.e., ejection fraction < 35%) |
| `e7d52393__NCT04040959` | 10 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Hospitalization in the past month |
| `e7d52393__NCT04040959` | 11 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Proteinuria > 5 g/day |
| `e7d52393__NCT04040959` | 12 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Immunosuppressant agents such as cyclosporine, tacrolimus, azathioprine, etanercept, infliximab,... |
| `e7d52393__NCT06568471` | 3 | medication_present | indeterminate->pass | indeterminate_to_determinate | medication_exposure | On a stable diet and lipid-lowering oral drugs (such as statins, ezetimibe or Hybutimibe, omega-3... |
| `e7d52393__NCT06568471` | 5 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Patients on a PCSK9 mAb at a dose of 75 mg, 140 mg, or 150 mg Q2W must undergo a washout period o... |
| `e7d52393__NCT06568471` | 7 | condition_absent | indeterminate->fail | indeterminate_to_determinate | condition_presence | Documented history of homozygous familial hypercholesterolemia (HoFH); |
| `e7d52393__NCT06568471` | 10 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | Poorly controlled thyroid disorder including hypothyroidism or hyperthyroidism; |
| `e7d52393__NCT06568471` | 12 | free_text | indeterminate->pass | indeterminate_to_determinate | compound | Serious arrhythmia, MI, unstable angina pectoris, PCI, CABG, implantable cardioverter defibrillat... |
| `e7d52393__NCT06568471` | 14 | condition_absent | indeterminate->indeterminate | reason_changed | compound | New York Heart Association (NYHA) Class III-IV heart failure; |
| `e7d52393__NCT06568471` | 17 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Unexplained creatine kinase (CK) > 5 x ULN (retested once is needed if suspected to be related to... |
| `e7d52393__NCT06568471` | 21 | condition_absent | indeterminate->indeterminate | reason_changed | condition_presence | History of any major drug allergy, including allergy to protein biologics; |
| `fa2d28b1__NCT06090266` | 8 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Subjects must have measurable disease per RECIST v1.1. |
| `fa2d28b1__NCT06090266` | 10 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Resolution of prior clinically significant therapy-related AEs (excluding alopecia and ≤ Grade 2... |
| `fa2d28b1__NCT06090266` | 11 | temporal_window | indeterminate->indeterminate | reason_changed | temporal_event | Minimum of 2 weeks since the last dose of other hormone therapy and 3 weeks since the last dose o... |
| `fa2d28b1__NCT06090266` | 19 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Life expectancy < 12 weeks. |
| `fa2d28b1__NCT06090266` | 20 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | Subject has an Eastern Cooperative Oncology Group (ECOG) Performance Status (PS) > 2. |
| `fa2d28b1__NCT06090266` | 27 | free_text | indeterminate->indeterminate | reason_changed | free_text_review | Recent or ongoing serious infection including the following: Any uncontrolled Grade 3 or higher (... |
| `fa2d28b1__NCT06090266` | 34 | measurement_threshold | indeterminate->indeterminate | reason_changed | measurement_threshold | QTc interval ≥ 470 msec by electrocardiogram (ECG). |
