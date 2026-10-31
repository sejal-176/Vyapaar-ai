/**
 * Typed models matching backend/api/dashboard.py, backend/api/verify.py,
 * and backend/api/agent.py responses exactly.
 * Rule 1: Money fields are integer paise.
 * Rule 3: Collections = digital collections.
 * Rule 6: Deterministic verification, no AI confidence scores.
 */

export interface Merchant {
  id: number;
  name: string;
  business_type: string;
  vpa: string;
}

export interface MerchantInfo {
  id: number;
  name: string;
  business_type: string;
}

export interface DaySummary {
  collections_paise: number;
  success_count: number;
  pending_count: number;
  failed_count: number;
  refunded_count: number;
  avg_ticket_paise: number;
}

export interface TrendItem {
  date: string;
  collections_paise: number;
}

export interface RecentTransaction {
  reference: string;
  amount_paise: number;
  status: "SUCCESS" | "PENDING" | "FAILED" | "REFUNDED" | string;
  txn_type: "PAYMENT" | "REFUND" | string;
  created_at_ist: string;
}

export interface IngestionReport {
  accepted: number;
  rejected: number;
  reasons: Record<string, number>;
}

export interface DashboardResponse {
  merchant: MerchantInfo;
  reference_date: string;
  summary: DaySummary;
  previous_summary: DaySummary;
  trend: TrendItem[];
  recent_transactions: RecentTransaction[];
  ingestion_report: IngestionReport;
}

export interface ExtractedDetails {
  amount_paise: number | null;
  utr: string | null;
  timestamp: string | null;
  status_text: string | null;
  recipient: string | null;
}

export interface LedgerRecord {
  reference: string;
  amount_paise: number;
  amount_inr?: string;
  status: string;
  txn_type?: string;
  created_at_ist: string;
}

export interface VerificationResult {
  outcome: "VERIFIED" | "UNVERIFIED" | "MISMATCH";
  reason: string;
  matched_fields: string[];
  conflicting_fields: string[];
  evidence: string[];
  next_step: string;
  duplicate_flag: boolean;
  extracted: ExtractedDetails;
  ledger_record: LedgerRecord | null;
  raw_text: string;
}

export interface AgentToolCall {
  name: string;
  args: Record<string, any>;
}

export interface AgentResponse {
  answer: string;
  tools_used: AgentToolCall[];
  mode: "llm" | "rule-based" | string;
}

export type CaseStatus = "OPEN" | "UNDER_REVIEW" | "RESOLVED";

export interface CaseItem {
  id: number;
  merchant_id: number;
  case_type: string;
  description: string;
  status: CaseStatus;
  related_reference: string | null;
  note: string | null;
  created_at_ist: string | null;
  updated_at_ist: string | null;
}

export interface CreateCasePayload {
  case_type?: string;
  description: string;
  status?: CaseStatus;
  related_reference?: string | null;
  note?: string | null;
}

export interface UpdateCasePayload {
  status?: CaseStatus;
  note?: string | null;
}

export interface ComparisonData {
  day_a: DaySummary;
  day_b: DaySummary;
  delta_collections_paise: number;
  delta_success_count: number;
  delta_avg_ticket_paise: number;
  volume_effect: number;
  ticket_effect: number;
  main_driver: "volume" | "ticket_size" | "mixed" | string;
  note: string | null;
}

export interface PeakHourData {
  hour_ist: number;
  peak_hour_display: string;
  amount_paise: number;
  count: number;
}

export interface ReportSections {
  summary: DaySummary;
  comparison: ComparisonData;
  peak_hour: PeakHourData;
  open_cases: number;
}

export interface ReportResponse {
  date: string;
  sections: ReportSections;
  text: string;
}

export interface ExtractedClaim {
  direction: "credit" | "debit" | "refund" | "unknown" | string;
  amount_paise: number | null;
  amount_inr: string | null;
  utr: string | null;
  timestamp: string | null;
  counterparty: string | null;
  raw_amounts_found: string[];
}

export interface CandidateTransaction {
  reference: string;
  amount_inr: string;
  status: string;
  time_ist: string;
}

export interface LedgerCheckResult {
  outcome: "VERIFIED" | "UNVERIFIED" | "MISMATCH" | "NOT_CHECKABLE";
  reason: string;
  matched_fields: string[];
  conflicting_fields: string[];
  evidence: string[];
  ledger_record: LedgerRecord | null;
  candidates: CandidateTransaction[];
  possible_match: CandidateTransaction | null;
}

export interface WarningSignal {
  category: string;
  matched_text: string;
  explanation: string;
}

export interface ScamCheckResponse {
  claim: ExtractedClaim;
  ledger_check: LedgerCheckResult;
  signals: WarningSignal[];
  warning_level: string;
  next_step: string;
  advice: string;
  disclaimer: string;
}


