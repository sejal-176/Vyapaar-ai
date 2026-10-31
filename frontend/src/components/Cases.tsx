import React, { useState, useEffect, useCallback } from "react";
import type { CaseItem, CaseStatus, Merchant } from "../api/types";
import { fetchCases, updateCase } from "../api/client";

interface CasesProps {
  merchantId: number;
  merchants: Merchant[];
}

export const Cases: React.FC<CasesProps> = ({ merchantId, merchants }) => {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notesState, setNotesState] = useState<Record<number, string>>({});

  const currentMerchant = merchants.find((m) => m.id === merchantId);

  const loadCases = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setActionError(null);
    try {
      const data = await fetchCases(merchantId);
      setCases(data);
      // Initialize note inputs from fetched data
      const initialNotes: Record<number, string> = {};
      data.forEach((c) => {
        initialNotes[c.id] = c.note || "";
      });
      setNotesState(initialNotes);
    } catch (err: any) {
      setError(err.message || "Failed to load cases.");
    } finally {
      setIsLoading(false);
    }
  }, [merchantId]);

  useEffect(() => {
    loadCases();
  }, [loadCases]);

  const handleStatusChange = async (caseId: number, newStatus: CaseStatus) => {
    setActionError(null);
    const prevCase = cases.find((c) => c.id === caseId);
    if (!prevCase || prevCase.status === newStatus) return;

    const prevStatus = prevCase.status;

    // Optimistic update
    setCases((prev) =>
      prev.map((c) => (c.id === caseId ? { ...c, status: newStatus } : c))
    );

    try {
      await updateCase(merchantId, caseId, { status: newStatus });
    } catch (err: any) {
      // Rollback on failure
      setCases((prev) =>
        prev.map((c) => (c.id === caseId ? { ...c, status: prevStatus } : c))
      );
      setActionError(`Failed to update status for Case #${caseId}: ${err.message || "Unknown error"}`);
    }
  };

  const handleNoteBlur = async (caseId: number) => {
    setActionError(null);
    const existingCase = cases.find((c) => c.id === caseId);
    if (!existingCase) return;

    const currentNoteVal = notesState[caseId] !== undefined ? notesState[caseId] : (existingCase.note || "");
    const originalNote = existingCase.note || "";

    // If note hasn't changed, do nothing
    if (currentNoteVal.trim() === originalNote.trim()) return;

    try {
      const updated = await updateCase(merchantId, caseId, { note: currentNoteVal });
      setCases((prev) =>
        prev.map((c) => (c.id === caseId ? { ...c, note: updated.note } : c))
      );
    } catch (err: any) {
      // Rollback note
      setNotesState((prev) => ({ ...prev, [caseId]: originalNote }));
      setActionError(`Failed to save note for Case #${caseId}: ${err.message || "Unknown error"}`);
    }
  };

  const handleNoteChange = (caseId: number, value: string) => {
    setNotesState((prev) => ({
      ...prev,
      [caseId]: value,
    }));
  };

  return (
    <div className="cases-container">
      {/* Header */}
      <div className="view-header">
        <div>
          <h1 className="view-title">Dispute & Follow-up Cases</h1>
          <p className="view-subtitle">
            Manage payment discrepancies and screenshot verification follow-ups for {currentMerchant?.name}
          </p>
        </div>
      </div>

      {/* Mandatory Demo Disclaimer Label */}
      <div className="demo-disclaimer-banner">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <span>Internal demo cases. Not submitted to Paytm or any bank.</span>
      </div>

      {/* Action error banner if status/note update fails */}
      {actionError && (
        <div className="cases-action-error">
          <span>{actionError}</span>
          <button type="button" onClick={() => setActionError(null)} className="btn-dismiss">
            ✕
          </button>
        </div>
      )}

      {/* Main Content */}
      {isLoading ? (
        <div className="state-container">
          <div className="state-title">Loading cases...</div>
          <div className="state-text">Fetching recorded dispute cases for this merchant.</div>
        </div>
      ) : error ? (
        <div className="state-container">
          <div className="state-title" style={{ color: "var(--color-danger)" }}>
            Unable to load cases
          </div>
          <div className="state-text">{error}</div>
          <button type="button" className="btn-retry" onClick={loadCases}>
            Retry
          </button>
        </div>
      ) : cases.length === 0 ? (
        <div className="state-container">
          <div className="state-title">No cases found</div>
          <div className="state-text">
            There are no internal cases recorded for this merchant. When a payment mismatch is flagged in the Verify tab, you can create a case to track it here.
          </div>
        </div>
      ) : (
        <div className="table-card">
          <table className="data-table cases-table">
            <thead>
              <tr>
                <th style={{ width: "70px" }}>ID</th>
                <th style={{ width: "120px" }}>Type</th>
                <th>Description</th>
                <th style={{ width: "150px" }}>Related Ref</th>
                <th style={{ width: "160px" }}>Status</th>
                <th>Internal Note</th>
                <th style={{ width: "160px" }}>Created (IST)</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id}>
                  <td className="case-id">#{c.id}</td>
                  <td>
                    <span className="case-type-badge">{c.case_type}</span>
                  </td>
                  <td className="case-description">{c.description}</td>
                  <td className="case-reference">
                    {c.related_reference ? (
                      <code>{c.related_reference}</code>
                    ) : (
                      <span className="muted-text">—</span>
                    )}
                  </td>
                  <td>
                    <select
                      className={`status-select status-${c.status.toLowerCase()}`}
                      value={c.status}
                      onChange={(e) => handleStatusChange(c.id, e.target.value as CaseStatus)}
                      aria-label={`Status for case ${c.id}`}
                    >
                      <option value="OPEN">OPEN</option>
                      <option value="UNDER_REVIEW">UNDER REVIEW</option>
                      <option value="RESOLVED">RESOLVED</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="text"
                      className="case-note-input"
                      placeholder="Add merchant note..."
                      value={notesState[c.id] !== undefined ? notesState[c.id] : (c.note || "")}
                      onChange={(e) => handleNoteChange(c.id, e.target.value)}
                      onBlur={() => handleNoteBlur(c.id)}
                      aria-label={`Internal note for case ${c.id}`}
                    />
                  </td>
                  <td className="case-created-at">
                    {c.created_at_ist || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

