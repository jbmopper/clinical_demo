# TREC / TrialGPT benchmark plan (local scaffold vs external)

This repo ships a **local export scaffold** inspired by TrialGPT / TREC Clinical Trials framing — it is **not** official NIST/TREC ingestion. Code lives under the evals **trial benchmark** module and an export script.

---

## 1. What exists today (local)

**Dataset acquisition:** Start from the **curated eval seed** already in the repo workflow (patient ids, trial ids, as-of dates, slices). No automatic download of official TREC qrels.

**Adapter shape (`TrialBenchmarkDataset` JSON):**

- **Queries:** one per patient id — includes a **patient summary** string, as-of date, and a list of **candidate trials** (pair id, nct id, title, conditions, slice, optional relevance tag defaulting to `unknown`).
- **Criterion cases:** optional parallel list keyed by `(pair_id, criterion_index)` carrying human **expected matcher verdict** and **cited source row ids** when copied from patient-evidence labels.

**Framing string** in the artifact records that this is a local scaffold versioned (`trial-benchmark-v0.1`).

---

## 2. Metrics implemented locally

**Ranking:** Given human or downstream relevance judgments per candidate, the module can compute simple **MRR** and **recall@k** style metrics over judged subsets — useful once `relevance_by_pair` is populated.

**Criterion matching:** Reuses **patient-evidence label** expectations where present; otherwise criterion cases are placeholders.

---

## 3. How external TREC / official TrialGPT would differ

| Dimension | External benchmark | This repo’s local scaffold |
|-----------|---------------------|----------------------------|
| Topics / patient narratives | Official query distribution | Synthea-derived summaries from internal helpers |
| Trial corpus | Full CT.gov snapshot or official candidate pools | ~30 curated trials from the demo manifest |
| Relevance labels | NIST qrels or shared task keys | Mostly `unknown` unless you import labels |
| Scoring | Official evaluators, leaderboard rules | Row-citation agreement + matcher verdict accuracy against your JSON labels |

**Adapter work for a future “official” track:** ingest official query/candidate files → map candidate NCT ids into the internal `Trial` loader → ensure patient summaries align with **redaction** policy → run the same scoring pipeline → emit predictions in the required run format for the task organizer.

---

## 4. Recommended evaluation flow (when expanding)

1. Keep **local scaffold** for fast regression during development.
2. Add a **private** directory (gitignored) for unpacked official task files + your run submissions.
3. Never commit **qrels** or official narrative text if task license forbids redistribution — reference paths in local docs only.

Related: `docs/evaluation-layers-and-gates.md`, `docs/patient-evidence-labeling-guide.md`.
