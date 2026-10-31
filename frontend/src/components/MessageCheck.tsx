import React, { useState, useEffect } from "react";
import type { Merchant, ScamCheckResponse } from "../api/types";
import { checkSmsMessage, createCase } from "../api/client";

interface MessageCheckProps {
  merchantId: number;
  merchants: Merchant[];
  onNavigateToCases?: () => void;
}

const MAX_CHARS = 2000;
const PLACEHOLDER_TEXT =
  "e.g. Rs 500.00 credited to your account via UPI. UTR 400000000001 on 30-10-2026 18:30:00. Check balance at https://paytm.com";

export const MessageCheck: React.FC<MessageCheckProps> = ({
  merchantId,
  merchants,
  onNavigateToCases,
}) => {
  const [inputText, setInputText] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [result, setResult] = useState<ScamCheckResponse | null>(null);

  const [isCreatingCase, setIsCreatingCase] = useState<boolean>(false);
  const [createdCaseId, setCreatedCaseId] = useState<number | null>(null);
  const [caseError, setCaseError] = useState<string | null>(null);

  const currentMerchant = merchants.find((m) => m.id === merchantId);

  // Clear state when merchant changes
  useEffect(() => {
    setInputText("");
    setResult(null);
    setErrorMsg(null);
    setCreatedCaseId(null);
    setCaseError(null);
  }, [merchantId]);

  const handleCheck = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputText.trim();
    if (!trimmed || isLoading) return;

    setIsLoading(true);
    setErrorMsg(null);
    setCreatedCaseId(null);
    setCaseError(null);

    try {
      const res = await checkSmsMessage(merchantId, trimmed);
      setResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to inspect message.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleClear = () => {
    setInputText("");
    setResult(null);
    setErrorMsg(null);
    setCreatedCaseId(null);
    setCaseError(null);
  };

  const handleCreateCase = async () => {
    if (!result || isCreatingCase) return;

    setIsCreatingCase(true);
    setCaseError(null);

    const ref = result.claim.utr || (result.ledger_check.possible_match ? result.ledger_check.possible_match.reference : null);
    const desc = `SMS Check discrepancy (${result.ledger_check.outcome}): ${result.ledger_check.reason}`;
    const note = `Claimed: ${result.claim.amount_inr || "No amount"}, Direction: ${result.claim.direction}. Signals: ${
      result.signals.map((s) => s.category).join(", ") || "None"
    }`;

    try {
      const created = await createCase(merchantId, {
        case_type: "SMS_CLAIM",
        description: desc,
        status: "OPEN",
        related_reference: ref,
        note: note,
      });
      setCreatedCaseId(created.id);
    } catch (err: any) {
      setCaseError(err.message || "Failed to create dispute case.");
    } finally {
      setIsCreatingCase(false);
    }
  };

  const lc = result?.ledger_check;
  const isMatch = (field: string) => lc?.matched_fields.includes(field);
  const isConflict = (field: string) => lc?.conflicting_fields.includes(field);

  const getFieldClass = (field: string, hasClaimValue: boolean) => {
    if (isConflict(field)) return "cell-conflict";
    if (isMatch(field)) return "cell-match";
    if (!hasClaimValue) return "cell-muted";
    return "";
  };

  return (
    <div className="scam-container">
      {/* Header */}
      <div className="view-header">
        <div>
          <h1 className="view-title">Payment Message & SMS Checker</h1>
          <p className="view-subtitle">
            Verify payment claims against ledger records and detect fraud signals for {currentMerchant?.name}
          </p>
        </div>
      </div>

      {/* Input Form Card */}
      <div className="verify-card">
        <form onSubmit={handleCheck}>
          <div className="scam-input-header">
            <label htmlFor="sms-text-input" className="section-title">
              Paste SMS or Notification Message
            </label>
            <span
              className={`char-counter ${inputText.length > MAX_CHARS ? "over-limit" : ""}`}
            >
              {inputText.length} / {MAX_CHARS}
            </span>
          </div>

          <textarea
            id="sms-text-input"
            className="scam-textarea"
            rows={5}
            maxLength={MAX_CHARS}
            placeholder={PLACEHOLDER_TEXT}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={isLoading}
            aria-label="SMS message content to verify"
          />

          {errorMsg && (
            <div className="error-banner" style={{ marginTop: "0.75rem" }}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>{errorMsg}</span>
            </div>
          )}

          <div className="scam-button-row">
            <button
              type="submit"
              className="btn-primary"
              disabled={isLoading || !inputText.trim()}
              style={{ minHeight: "44px", minWidth: "140px" }}
            >
              {isLoading ? "Checking Message..." : "Check Message"}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={handleClear}
              disabled={isLoading || (!inputText && !result)}
              style={{ minHeight: "44px" }}
            >
              Clear
            </button>
          </div>
        </form>
      </div>

      {/* Result Section */}
      {result && lc && (
        <div className="verification-results">
          {/* Outcome Banner */}
          <div className={`outcome-banner ${lc.outcome.toLowerCase().replace(/_/g, "-")}`}>
            <div className="outcome-header">
              <div className="outcome-icon-tag">
                {lc.outcome === "VERIFIED" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                )}
                {lc.outcome === "UNVERIFIED" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                )}
                {lc.outcome === "MISMATCH" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2" />
                    <line x1="15" y1="9" x2="9" y2="15" />
                    <line x1="9" y1="9" x2="15" y2="15" />
                  </svg>
                )}
                {lc.outcome === "NOT_CHECKABLE" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                  </svg>
                )}
                <span className="outcome-title">{lc.outcome}</span>
              </div>
              <span className="outcome-reason">{lc.reason}</span>
            </div>

            <div className="outcome-next-step">
              <strong>Next Step:</strong> {result.next_step}
            </div>

            {/* Create Case Button for MISMATCH and UNVERIFIED */}
            {(lc.outcome === "MISMATCH" || lc.outcome === "UNVERIFIED") && (
              <div className="case-action-row" style={{ marginTop: "1rem" }}>
                {createdCaseId ? (
                  <div className="case-created-banner">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                      <polyline points="22 4 12 14.01 9 11.01" />
                    </svg>
                    <span>
                      Dispute Case <strong>#{createdCaseId}</strong> created successfully.{" "}
                      {onNavigateToCases && (
                        <button
                          type="button"
                          className="btn-case-link"
                          onClick={onNavigateToCases}
                        >
                          View in Cases tab &rarr;
                        </button>
                      )}
                    </span>
                  </div>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn-create-case active"
                      onClick={handleCreateCase}
                      disabled={isCreatingCase}
                      style={{ minHeight: "44px" }}
                    >
                      {isCreatingCase ? "Creating Case..." : "Create Case from Discrepancy"}
                    </button>
                    {caseError && <span className="case-error-hint">{caseError}</span>}
                  </>
                )}
              </div>
            )}
          </div>

          {/* Comparison Table: What the message claims vs In our records */}
          <div className="verify-card">
            <h3 className="section-title">Record Comparison</h3>
            <table className="comparison-table">
              <thead>
                <tr>
                  <th style={{ width: "25%" }}>Field</th>
                  <th style={{ width: "37.5%" }}>What the Message Claims</th>
                  <th style={{ width: "37.5%" }}>In Our Records</th>
                </tr>
              </thead>
              <tbody>
                {/* Amount */}
                <tr className={getFieldClass("amount", result.claim.amount_inr !== null)}>
                  <td className="field-label">Amount</td>
                  <td>
                    {result.claim.amount_inr || (
                      <span className="muted-text">Not found in message</span>
                    )}
                  </td>
                  <td>
                    {lc.ledger_record ? (
                      lc.ledger_record.amount_inr
                    ) : lc.possible_match ? (
                      lc.possible_match.amount_inr
                    ) : (
                      <span className="muted-text">—</span>
                    )}
                  </td>
                </tr>

                {/* Reference */}
                <tr className={getFieldClass("reference", result.claim.utr !== null)}>
                  <td className="field-label">Reference (UTR)</td>
                  <td>
                    {result.claim.utr ? (
                      <code>{result.claim.utr}</code>
                    ) : (
                      <span className="muted-text">Not found in message</span>
                    )}
                  </td>
                  <td>
                    {lc.ledger_record ? (
                      <code>{lc.ledger_record.reference}</code>
                    ) : lc.possible_match ? (
                      <code>{lc.possible_match.reference}</code>
                    ) : (
                      <span className="muted-text">—</span>
                    )}
                  </td>
                </tr>

                {/* Direction */}
                <tr className={getFieldClass("direction", result.claim.direction !== "unknown")}>
                  <td className="field-label">Direction</td>
                  <td>
                    {result.claim.direction !== "unknown" ? (
                      <span className="text-tag">{result.claim.direction.toUpperCase()}</span>
                    ) : (
                      <span className="muted-text">Not specified</span>
                    )}
                  </td>
                  <td>
                    {lc.ledger_record ? (
                      <span className="text-tag">{lc.ledger_record.txn_type}</span>
                    ) : (
                      <span className="muted-text">—</span>
                    )}
                  </td>
                </tr>

                {/* Time */}
                <tr>
                  <td className="field-label">Time</td>
                  <td>
                    {result.claim.timestamp || (
                      <span className="muted-text">Not specified</span>
                    )}
                  </td>
                  <td>
                    {lc.ledger_record ? (
                      lc.ledger_record.created_at_ist
                    ) : lc.possible_match ? (
                      lc.possible_match.time_ist
                    ) : (
                      <span className="muted-text">—</span>
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Candidate Matches if multiple or single without UTR */}
          {lc.candidates && lc.candidates.length > 0 && (
            <div className="verify-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <h3 className="section-title">Potential Matching Transactions</h3>
                <span className="muted-notice">Amount alone is not proof.</span>
              </div>
              <p style={{ fontSize: "0.85rem", color: "var(--color-muted)", marginBottom: "0.75rem" }}>
                The following transactions match the claimed amount in our records. Without a matching reference number, the specific transaction cannot be proved.
              </p>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Time (IST)</th>
                  </tr>
                </thead>
                <tbody>
                  {lc.candidates.map((cand, idx) => (
                    <tr key={idx}>
                      <td><code>{cand.reference}</code></td>
                      <td style={{ fontWeight: 600 }}>{cand.amount_inr}</td>
                      <td><span className="status-chip success">{cand.status}</span></td>
                      <td>{cand.time_ist}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Evidence List */}
          {lc.evidence && lc.evidence.length > 0 && (
            <div className="verify-card">
              <h3 className="section-title">Verification Evidence</h3>
              <ul className="evidence-list">
                {lc.evidence.map((item, index) => (
                  <li key={index} className="evidence-item">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Warning Signals Section */}
          <div className="verify-card">
            <div className="signals-header">
              <h3 className="section-title">Warning Signals</h3>
              <span className={`signals-badge ${result.signals.length > 0 ? "warning" : "clean"}`}>
                {result.warning_level}
              </span>
            </div>

            {result.signals.length === 0 ? (
              <p style={{ fontSize: "0.85rem", color: "var(--color-success)", margin: "0.5rem 0" }}>
                No suspicious phrases, link manipulation, or secret requests were detected in this message.
              </p>
            ) : (
              <div className="signals-list">
                {result.signals.map((sig, sIdx) => (
                  <div key={sIdx} className="signal-item">
                    <div className="signal-cat-badge">{sig.category.toUpperCase().replace(/_/g, " ")}</div>
                    <div className="signal-details">
                      <div className="signal-match-phrase">
                        Matched text: <mark className="signal-mark">{sig.matched_text}</mark>
                      </div>
                      <div className="signal-explanation">{sig.explanation}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Mandatory Advice & Disclaimer */}
          <div className="advice-disclaimer-card">
            <div className="advice-line">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <strong>Security Advice:</strong> {result.advice}
            </div>
            <div className="disclaimer-line">
              <strong>Notice:</strong> {result.disclaimer}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

