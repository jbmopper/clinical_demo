# Data provenance and artifact policy

What belongs in git, what stays **local only**, and how eval artifacts are organized — derived from `.gitignore` rules and established `eval/` conventions.

---

## 1. Never committed (local / secrets)

| Pattern | Rationale |
|---------|-----------|
| `.env` | API keys, Langfuse secrets, optional PhysioNet credentials. |
| `data/raw/` | Upstream downloads: Synthea zip contents, Chia zip, etc. |
| `data/curated/` | Per-trial JSON, cohort manifests, cached CT extractions, Chia extraction caches — large, regenerable, sometimes LLM-costly to recreate. |
| `data/cache/` | Terminology envelopes and resolver caches — reproducible but bulky; may embed licensed API payloads. |
| `eval/runs.sqlite` (+ variants) | Append-only eval database containing full `ScorePairResult` JSON per case — can grow without bound. |

---

## 2. Committed on purpose

| Path | Rationale |
|------|-----------|
| `eval/baselines/**` except ignored globs | Small **diagnostics JSON**, **SUMMARY** markdown, **watchlists** for terminology regression — the regression story depends on pinned numbers in git. |
| `eval/calibration/*.json` (where present) | Reviewer label templates and candidate packets — typically synthetic or aggregated; must not contain restricted clinical text. Row-level patient-evidence packets generated for review are local-only unless transformed into a public summary artifact. |
| `tests/fixtures/**` | Tiny synthetic bundles and Chia snippets safe to distribute. |

**Large per-case dumps:** `eval/baselines/**/*_report.json` is **gitignored** by explicit pattern — those files exceed repo hygiene limits; reproduce from sqlite + scripts if needed.

**Public patient-evidence summaries:** Use `scripts/export_patient_evidence_public_summary.py` and `scripts/check_public_artifact_privacy.py`; see `docs/patient-evidence-eval-runbook.md` for the command sequence.

---

## 3. Run IDs and sqlite

- Each eval **run** gets a unique id persisted in sqlite with notes, timestamps, orchestrator flags, and per-case outcomes.
- **Do not** hand-edit sqlite in git — regenerate via eval CLI.

---

## 4. Public reports and talks

- Prefer **aggregate tables** (counts, rates, version strings) over pasting patient or note text.
- When showing **criterion excerpts**, use **public trial text** (CT.gov) or synthetic examples — not MIMIC or other credentialed sources.
- If a screenshot includes reviewer UI, scrub **patient ids** unless synthetic.

---

## 5. Naming hygiene

- Baseline folders dated **`YYYY-MM-DD-topic/`** make temporal comparisons obvious.
- Include **git commit hash** or run id inside diagnostic JSON when the generating script supports it (several baseline artifacts already do).

---

## 6. LLM outputs in issues/PRs

Avoid pasting **full eligibility** or **full patient charts** into GitHub issues — link to internal docs or summarize counts instead.

Related: `docs/patient-evidence-eval-runbook.md`, `docs/mimic-note-privacy-policy.md`, `docs/mimic-iv-calibration-and-governance.md`, `docs/evaluation-layers-and-gates.md`.
