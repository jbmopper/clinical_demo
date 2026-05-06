// Tiny typed client over the local FastAPI. Hand-typed against
// the response shapes in src/clinical_demo/api/app.py — when this
// UI moves into the juliusm.com repo we'll either pin a generated
// client or (more likely) regenerate these by hand because the
// surface is small.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

export type Eligibility = 'pass' | 'fail' | 'indeterminate';
export type Verdict = 'pass' | 'fail' | 'indeterminate';
export type JudgeLabel = 'correct' | 'incorrect' | 'unjudgeable';
export type PatientEvidenceLabel =
	| 'supports_present'
	| 'supports_absent'
	| 'supports_measurement_comparison'
	| 'insufficient_evidence';
export type MatcherAssumptionMode = 'open_world' | 'closed_world_eval' | 'closed_world_demo';
export type LLMUseLevel = 'none' | 'retrieval_only' | 'bounded_adjudication' | 'critic';

export interface PatientRow {
	patient_id: string;
	score: number | null;
	slice: string | null;
}

export interface TrialRow {
	nct_id: string;
	title: string;
}

export type VerdictReason =
	| 'ok'
	| 'no_data'
	| 'stale_data'
	| 'unit_mismatch'
	| 'unmapped_concept'
	| 'unsupported_kind'
	| 'unsupported_mood'
	| 'human_review_required'
	| 'ambiguous_criterion'
	| 'extractor_invariant_violation';

export interface EvidenceBase {
	kind: string;
	note: string;
}
export interface LabEvidence extends EvidenceBase {
	kind: 'lab';
	concept: { system: string; code: string; display: string };
	value: number;
	unit: string;
	effective_date: string;
}
export interface ConditionEvidence extends EvidenceBase {
	kind: 'condition';
	concept: { system: string; code: string; display: string };
	onset_date: string | null;
	abatement_date: string | null;
}
export interface MedicationEvidence extends EvidenceBase {
	kind: 'medication';
	concept: { system: string; code: string; display: string };
	start_date: string;
	end_date: string | null;
}
export interface DemographicsEvidence extends EvidenceBase {
	kind: 'demographics';
	field: 'age_years' | 'sex';
	value: string;
}
export interface TrialFieldEvidence extends EvidenceBase {
	kind: 'trial_field';
	field: string;
	value: string;
}
export interface MissingEvidence extends EvidenceBase {
	kind: 'missing';
	looked_for: string;
}
export interface RetrievedPatientRowEvidence extends EvidenceBase {
	kind: 'retrieved_patient_row';
	row_id: string;
	row_kind: string;
	label: string;
	value: string;
	date: string | null;
	code: string | null;
	system: string | null;
	status: string | null;
	score: number;
	reasons: string[];
}
export type Evidence =
	| LabEvidence
	| ConditionEvidence
	| MedicationEvidence
	| DemographicsEvidence
	| TrialFieldEvidence
	| MissingEvidence
	| RetrievedPatientRowEvidence;

export interface MatchVerdict {
	criterion: ExtractedCriterion;
	verdict: Verdict;
	reason: VerdictReason;
	rationale: string;
	evidence: Evidence[];
	matcher_version: string;
}

export interface ExtractedCriterion {
	kind: string;
	polarity: 'inclusion' | 'exclusion';
	source_text: string;
	negated: boolean;
	mood: 'actual' | 'hypothetical' | 'historical';
	age?: { minimum_years: number | null; maximum_years: number | null } | null;
	sex?: { sex: 'MALE' | 'FEMALE' | 'ALL' } | null;
	condition?: { condition_text: string } | null;
	medication?: { medication_text: string } | null;
	measurement?: Record<string, unknown> | null;
	temporal_window?: Record<string, unknown> | null;
	free_text?: { description: string } | null;
	mentions: unknown[];
}

export interface ScoringSummary {
	total_criteria: number;
	by_verdict: Record<string, number>;
	by_reason: Record<string, number>;
	by_polarity: Record<string, number>;
	adjudicator_calls: number;
	adjudicator_input_tokens: number | null;
	adjudicator_output_tokens: number | null;
	adjudicator_cost_usd: number | null;
}

export interface ExtractorRunMeta {
	model: string;
	prompt_version: string;
	input_tokens: number | null;
	output_tokens: number | null;
	cached_input_tokens: number | null;
	cost_usd: number | null;
	latency_ms: number | null;
}

export type LLMCallStage =
	| 'extractor'
	| 'llm_match'
	| 'patient_evidence_adjudicator'
	| 'critic';

export interface LLMCallCost {
	stage: LLMCallStage;
	criterion_index: number | null;
	model: string;
	prompt_version: string;
	input_tokens: number | null;
	output_tokens: number | null;
	cached_input_tokens: number | null;
	cost_usd: number | null;
	latency_ms: number | null;
}

export interface ScorePairResult {
	patient_id: string;
	nct_id: string;
	as_of: string;
	matcher_assumption_mode: MatcherAssumptionMode;
	llm_use_level: LLMUseLevel;
	extraction: { criteria: ExtractedCriterion[]; metadata: { notes: string } };
	extraction_meta: ExtractorRunMeta;
	verdicts: MatchVerdict[];
	summary: ScoringSummary;
	eligibility: Eligibility;
	llm_calls: LLMCallCost[];
}

export interface ScoreRequest {
	patient_id: string;
	nct_id: string;
	as_of?: string | null;
	orchestrator?: 'imperative' | 'graph';
	critic_enabled?: boolean;
	use_cached_extraction?: boolean;
	matcher_assumption_mode?: MatcherAssumptionMode;
	llm_use_level?: LLMUseLevel;
}

export interface EvalRunRow {
	run_id: string;
	started_at: string;
	finished_at: string;
	notes: string;
	n_cases: number;
	n_errors: number;
}

export interface LayerThreeHumanLabel {
	pair_id: string;
	criterion_index: number;
	label: JudgeLabel | null;
	reviewer?: string | null;
	rationale: string;
	expected_matcher_verdict?: Verdict | null;
	correct_answer: string;
}

export interface LayerThreeSourceRecord {
	source: 'patient' | 'trial';
	kind: string;
	label: string;
	value: string;
	date?: string | null;
	code?: string | null;
	system?: string | null;
	status?: string | null;
}

export interface PatientEvidenceSourceRow extends LayerThreeSourceRecord {
	row_id: string;
}

export interface LayerThreeSourceContext {
	patient: LayerThreeSourceRecord[];
	trial: LayerThreeSourceRecord[];
}

export interface LayerThreeCalibrationRow {
	pair_id: string;
	patient_id: string;
	nct_id: string;
	criterion_index: number;
	bucket: string;
	criterion_kind: string;
	criterion_source_text: string;
	polarity: string;
	negated: boolean;
	mood: string;
	matcher_verdict: Verdict;
	matcher_reason: VerdictReason;
	matcher_rationale: string;
	evidence: Evidence[];
	source_context?: LayerThreeSourceContext | null;
	existing_label: LayerThreeHumanLabel | null;
}

export interface LayerThreeCalibrationResponse {
	run_id: string;
	label_path: string;
	rows: LayerThreeCalibrationRow[];
}

export interface PatientEvidenceHumanLabel {
	pair_id: string;
	criterion_index: number;
	label: PatientEvidenceLabel | null;
	cited_source_row_ids: string[];
	expected_matcher_verdict: Verdict | null;
	matcher_assumption_mode: MatcherAssumptionMode;
	reviewer?: string | null;
	rationale: string;
}

export interface PatientEvidenceCompositeLineItem {
	item_id: string;
	operator: 'any_of' | 'all_of';
	source_text: string;
}

export interface PatientEvidenceCalibrationRow {
	pair_id: string;
	patient_id: string;
	nct_id: string;
	eval_slice: string;
	criterion_index: number;
	candidate_bucket: string;
	criterion_kind: string;
	criterion_source_text: string;
	polarity: string;
	negated: boolean;
	mood: string;
	matcher_verdict: Verdict;
	matcher_reason: VerdictReason;
	matcher_rationale: string;
	matcher_assumption_mode: MatcherAssumptionMode;
	matcher_evidence: Evidence[];
	judge_label?: JudgeLabel | null;
	judge_error_categories: string[];
	judge_rationale?: string | null;
	source_rows: PatientEvidenceSourceRow[];
	source_row_counts: Record<string, number>;
	retrieved_source_row_ids: string[];
	retrieved_source_row_counts: Record<string, number>;
	retrieved_structured_source_row_ids: string[];
	retrieved_note_source_row_ids: string[];
	retrieval_reasons: Record<string, string[]>;
	concept_mappings: unknown[];
	composite_line_items: PatientEvidenceCompositeLineItem[];
	mapping_state: string;
	unmapped_surfaces: string[];
	evidence_retrieval_state: string;
	free_text_review_hint: string;
	open_world_label_guidance: string;
	closed_world_label_guidance: string;
	existing_label: PatientEvidenceHumanLabel | null;
}

export interface PatientEvidenceCalibrationResponse {
	candidate_path: string;
	label_path: string;
	rows: PatientEvidenceCalibrationRow[];
}

export interface ResearchSource {
	title: string;
	url: string;
	snippet: string;
}

export interface CriterionResearchBlurb {
	query: string;
	provider: string;
	model: string;
	gemini_prompt: string;
	blurb: string;
	sources: ResearchSource[];
	gemini_error: string | null;
	suggested_label: JudgeLabel | null;
	suggested_expected_matcher_verdict: Verdict | null;
	suggested_correct_answer: string;
}

export interface CriterionResearchRequest {
	criterion_text: string;
	criterion_kind?: string;
	matcher_verdict?: Verdict;
	matcher_reason?: VerdictReason;
	matcher_rationale?: string;
	matcher_evidence?: Evidence[];
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
	if (!res.ok) {
		let detail: unknown;
		try {
			detail = await res.json();
		} catch {
			detail = await res.text();
		}
		const msg =
			typeof detail === 'object' && detail !== null && 'detail' in detail
				? (detail as { detail: unknown }).detail
				: detail;
		throw new Error(`${res.status} ${res.statusText}: ${String(msg)}`);
	}
	return (await res.json()) as T;
}

export async function getHealth(): Promise<{ status: string }> {
	return jsonOrThrow(await fetch(`${API_BASE}/health`));
}

export async function listPatients(): Promise<PatientRow[]> {
	return jsonOrThrow(await fetch(`${API_BASE}/patients`));
}

export async function listTrials(): Promise<TrialRow[]> {
	return jsonOrThrow(await fetch(`${API_BASE}/trials`));
}

export async function score(req: ScoreRequest): Promise<ScorePairResult> {
	return jsonOrThrow(
		await fetch(`${API_BASE}/score`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(req)
		})
	);
}

export async function listEvalRuns(): Promise<EvalRunRow[]> {
	return jsonOrThrow(await fetch(`${API_BASE}/eval/runs`));
}

export async function getLayerThreeCalibration(
	runId: string,
	limit: number
): Promise<LayerThreeCalibrationResponse> {
	const params = new URLSearchParams({ run_id: runId, limit: String(limit) });
	return jsonOrThrow(await fetch(`${API_BASE}/layer3/calibration?${params}`));
}

export async function saveLayerThreeCalibration(
	labels: LayerThreeHumanLabel[],
	labelPath?: string
): Promise<{ label_path: string; saved: number }> {
	return jsonOrThrow(
		await fetch(`${API_BASE}/layer3/calibration`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ labels, label_path: labelPath })
		})
	);
}

export async function getPatientEvidenceCalibration(): Promise<PatientEvidenceCalibrationResponse> {
	return jsonOrThrow(await fetch(`${API_BASE}/patient-evidence/calibration`));
}

export async function savePatientEvidenceCalibration(
	labels: PatientEvidenceHumanLabel[],
	labelPath?: string
): Promise<{ label_path: string; saved: number }> {
	return jsonOrThrow(
		await fetch(`${API_BASE}/patient-evidence/calibration`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ labels, label_path: labelPath })
		})
	);
}

export async function fetchCriterionResearch(
	request: CriterionResearchRequest
): Promise<CriterionResearchBlurb> {
	return jsonOrThrow(
		await fetch(`${API_BASE}/research/criterion`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(request)
		})
	);
}
