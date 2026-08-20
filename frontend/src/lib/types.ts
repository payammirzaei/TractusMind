export type UserRole = "user" | "operator" | "admin";

export interface Identity {
  user_id: string;
  display_name: string;
  role: UserRole;
  auth_type: string;
}

export interface ConversationSummary {
  conversation_id: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationHistory {
  conversation_id: string;
  turns: Array<{ question: string; answer: string }>;
}

export interface QueryRoute {
  intent: string;
  source_ids: string[];
  version?: string | null;
  ref?: string | null;
  commit_sha?: string | null;
  reasons: string[];
}

export interface AnswerCitation {
  citation_id: string;
  chunk_id: string;
  source_id: string;
  repository: string;
  component: string;
  version_ref?: string | null;
  snapshot_commit_sha?: string | null;
  commit_sha: string;
  path: string;
  start_line: number;
  end_line: number;
  source_url: string;
  retrieval_score?: number | null;
  rerank_score?: number | null;
  debug_score?: number | null;
  retrieval_methods: string[];
}

export interface VerificationReport {
  passed: boolean;
  claims: Array<{
    claim: string;
    citation_ids: string[];
    supported: boolean;
    reason?: string | null;
  }>;
  unsupported_claim_count: number;
  failure_reason?: string | null;
}

export interface GroundedAnswer {
  interaction_id?: string | null;
  conversation_id?: string | null;
  question: string;
  answer: string;
  grounded: boolean;
  abstained: boolean;
  evidence_count: number;
  citations: AnswerCitation[];
  verification?: VerificationReport | null;
  route?: QueryRoute | null;
  model?: string | null;
}

export interface SourceStatus {
  source_id: string;
  repository: string;
  component: string;
  priority: string;
  enabled: boolean;
  configured_ref: string;
  version_ref?: string | null;
  snapshot_commit_sha?: string | null;
  file_count: number;
  updated_at?: string | null;
  latest_run_status?: string | null;
  latest_run_error?: string | null;
  locked: boolean;
}

export interface OpsSummary {
  configured_sources: number;
  enabled_sources: number;
  indexed_sources: number;
  locked_sources: number;
  running_sources: number;
  failed_sources: number;
  scheduler_interval_seconds: number;
  redis_ok: boolean;
  run_status_counts: Record<string, number>;
}

export interface RunStatus {
  run_id: string;
  source_id: string;
  repository: string;
  status: string;
  discovered_count: number;
  added_count: number;
  modified_count: number;
  deleted_count: number;
  unchanged_count: number;
  fetched_count: number;
  chunk_count: number;
  indexed_count: number;
  error_message?: string | null;
  started_at: string;
  finished_at?: string | null;
}

export interface QualityReview {
  review_id: string;
  interaction_id: string;
  trigger: string;
  status: string;
  root_cause?: string | null;
  reviewer_note?: string | null;
  question: string;
  answer?: string | null;
  interaction_status: string;
  intent?: string | null;
  error_type?: string | null;
  feedback_rating?: string | null;
  feedback_reason?: string | null;
  feedback_comment?: string | null;
  created_at: string;
  reviewed_at?: string | null;
}

export interface RegressionCase {
  case_id: string;
  review_id: string;
  interaction_id: string;
  benchmark_kind: "retrieval" | "debug" | "answer";
  question: string;
  expected_source_ids: string[];
  expected_terms: string[];
  expected_abstain: boolean;
  route_snapshot?: Record<string, unknown> | null;
  root_cause: string;
  reviewer_note?: string | null;
  created_at: string;
}

export interface ManagedUser {
  user_id: string;
  display_name: string;
  api_key_prefix?: string | null;
  enabled: boolean;
  role: UserRole;
  auth_type: string;
}
