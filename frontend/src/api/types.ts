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

// ============================================================================
// Growth Insights Preview Types
// ============================================================================

export interface LapsingCustomer {
  id: number;
  payer_token: string;
  consent_status: "NONE" | "OPTED_IN" | string;
  usual_gap_days: number;
  days_since_last_visit: number;
  last_visit_date: string;
  visits_before: number;
  visits_now: number;
  spend_before_inr: string;
  spend_now_inr: string;
  spend_per_visit_before_inr: string;
  spend_per_visit_now_inr: string;
  main_driver: "fewer_visits" | "smaller_basket" | "mixed" | string;
  driver_summary: string;
}

export interface ShrinkingCustomer {
  customer_id: number;
  payer_token: string;
  consent_status: string;
  visits_now: number;
  spend_per_visit_before_inr: string;
  spend_per_visit_now_inr: string;
  drop_pct: number;
  driver_summary: string;
}

export interface LapsingResponse {
  named: LapsingCustomer[];
  not_named_count: number;
  reference_date: string | null;
  how_we_measure: string;
  shrinking: ShrinkingCustomer[];
}

export interface ProductChanged {
  product_name: string;
  before_avg: number;
  now_avg: number;
  change: number;
}

export interface CustomerChangeResponse {
  customer_id: number;
  payer_token: string;
  consent_status: string;
  reference_date: string;
  visits_old: number;
  visits_new: number;
  spend_old_inr: string;
  spend_new_inr: string;
  spend_change_inr: string;
  spend_per_visit_old_inr: string;
  spend_per_visit_new_inr: string;
  visits_effect_inr: string;
  basket_effect_inr: string;
  main_driver: string;
  driver_summary: string;
  products_changed: ProductChanged[];
  worth_checking: string[];
}

export interface ProductInsight {
  id: number;
  name: string;
  unit: string;
  price_paise: number;
  price_inr: string;
  cost_price_paise: number | null;
  cost_price_inr: string | null;
  margin_per_unit_inr: string | null;
  margin_pct: number | null;
  stock_on_hand: number;
  stock_updated_on: string;
  velocity: number;
  days_left: number | null;
  status: "Low stock" | "OK" | "No recent units" | string;
  units_last14: number;
  units_prev14: number;
  trend_pct: number | null;
  explanation: string;
}

export interface SlowMover {
  product_id: number;
  product_name: string;
  unit: string;
  units_prev14: number;
  units_last14: number;
  drop_pct: number;
  note: string;
}

export interface InventoryResponse {
  products: ProductInsight[];
  slow_movers: SlowMover[];
  reference_date: string | null;
  how_we_measure: string;
  note: string;
}

export interface OutreachItem {
  id: number;
  customer_id: number;
  payer_token: string;
  status: "DRAFT" | "APPROVED" | "MARKED_SENT" | "DISMISSED" | string;
  language: "en" | "hi" | "mr" | string;
  offer_type: "NONE" | "LOYALTY_STAMP" | "PERCENT" | string;
  offer_pct: number;
  message_text: string;
  evidence: Record<string, any>;
  created_at: string;
  approved_at: string | null;
  marked_sent_at: string | null;
}

export interface GuardrailResult {
  allowed: boolean;
  reason: string;
  margin_used: number;
  margin_left: number;
}



