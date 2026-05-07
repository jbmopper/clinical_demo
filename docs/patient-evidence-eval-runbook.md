# Patient-evidence eval runbook

This is the operator path for the calibrated patient-trial matching loop:

1. run an eval;
2. build a **private/local** patient-evidence packet;
3. export a **public summary** artifact;
4. label useful rows;
5. compare `none`, `retrieval_only`, and `bounded_adjudication` runs once labels have signal.

The important privacy rule is simple: row-level calibration packets are local-only. Public artifacts must go through the summary exporter and privacy gate.

---

## 1. Start from clean `main`

```bash
git switch main
git pull --ff-only
git status --short --branch
```

Expected status:

```text
## main...origin/main
```

---

## 2. Run deterministic baseline eval

Use this before spending LLM calls. It gives the private calibration builder a run id and lets you inspect mapping/retrieval failure modes.

```bash
OTEL_SDK_DISABLED=true uv run python scripts/eval.py run \
  --no-llm \
  --binding-strategy two_pass \
  --matcher-assumption-mode open_world \
  --llm-use-level none \
  --notes "matcher-v0.3 extractor-v0.6 deterministic open_world"
```

Save the printed `run_id` as `RUN_ID`.

---

## 3. Write diagnostics

```bash
OTEL_SDK_DISABLED=true uv run python scripts/eval.py report \
  --run-id RUN_ID \
  --diagnostics \
  --write-diagnostics eval/baselines/2026-05-06/composite_v06_none_diagnostics.json
```

Use a new dated path when the baseline date or comparison target changes.

---

## 4. Build the private calibration packet

```bash
OTEL_SDK_DISABLED=true uv run python scripts/build_patient_evidence_calibration.py \
  --run-id RUN_ID \
  --scope cardiometabolic_core \
  --limit 60 \
  --prune-labels
```

This writes:

- `eval/calibration/patient_evidence_candidates.json`
- `eval/calibration/patient_evidence_labels.json`

These are private/local review files unless explicitly transformed into a public summary. Do not push row-level packets that contain note rows, note ids, raw note snippets, exact patient identifiers, or missing artifact safety metadata.

The builder prints the safe public-summary export command after it finishes.

---

## 5. Export the public summary

```bash
uv run python scripts/export_patient_evidence_public_summary.py \
  --candidates eval/calibration/patient_evidence_candidates.json \
  --labels eval/calibration/patient_evidence_labels.json \
  --diagnostics eval/baselines/2026-05-06/composite_v06_none_diagnostics.json \
  --output eval/baselines/2026-05-06/composite_v06_public_summary.json
```

The summary artifact should contain aggregate counts, run/config metadata, and artifact safety metadata. It must not contain row-level patient evidence, note rows, note ids, note snippets, or exact patient identifiers.

---

## 6. Run the artifact privacy gate

```bash
uv run python scripts/check_public_artifact_privacy.py \
  eval/baselines/2026-05-06/composite_v06_public_summary.json
```

If this fails, fix the exporter or artifact. Do not bypass it by committing private packets.

---

## 7. Label the useful rows

Open the calibration UI or edit the label file through project tooling. For each useful row, fill:

- `label`
- `expected_matcher_verdict`
- `cited_source_row_ids`
- `reviewer`
- `rationale`

Do not use LLM-generated labels as gold.

Prioritize rows where the system has a fair chance to decide from available evidence:

- mapped or partly mapped cardiometabolic criteria;
- structured condition/medication/lab rows;
- note/free-text evidence rows that are citeable;
- composite criteria where subcheck evidence is visible.

Skip or defer rows that only prove known plumbing gaps unless they are needed as regression tests.

---

## 8. Compare LLM-use levels after labels have signal

Once labels have enough usable rows, run or compare:

- `none`: deterministic only;
- `retrieval_only`: attach retrieved evidence, no adjudication;
- `bounded_adjudication`: source-grounded LLM over retrieved rows.

Use the patient-evidence report command:

```bash
uv run python scripts/eval.py patient-evidence \
  --labels eval/calibration/patient_evidence_labels.json \
  --run RUN_ID:none \
  --strict-labels \
  --min-usable-labels 40 \
  --output-json eval/baselines/2026-05-06/patient_evidence_report.json \
  --output-md eval/baselines/2026-05-06/patient_evidence_report.md
```

Replace or add `--run` entries for retrieval-only and bounded-adjudication run ids as they exist.

---

## 9. What to commit

Commit:

- public summary artifacts that pass `scripts/check_public_artifact_privacy.py`;
- docs;
- tests;
- exporter or gate code.

Do not commit:

- private row-level calibration packets unless explicitly marked safe and approved;
- raw MIMIC text or row-level MIMIC-derived artifacts;
- `eval/runs.sqlite`;
- generated private candidate packets with note rows or note ids.

Related: `docs/patient-evidence-labeling-guide.md`, `docs/data-provenance-and-artifact-policy.md`, `docs/mimic-note-privacy-policy.md`, `docs/llm-use-levels-and-cost-controls.md`.
