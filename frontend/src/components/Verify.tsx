import React, { useState, useRef, useEffect } from "react";
import type { VerificationResult, Merchant } from "../api/types";
import { verifyScreenshot, createCase } from "../api/client";
import { formatINR } from "../lib/format";

interface VerifyProps {
  merchantId: number;
  merchants: Merchant[];
  onNavigateToCases?: () => void;
}

export const Verify: React.FC<VerifyProps> = ({ merchantId, merchants, onNavigateToCases }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [showRawOcr, setShowRawOcr] = useState<boolean>(false);
  const [isCreatingCase, setIsCreatingCase] = useState<boolean>(false);
  const [createdCaseId, setCreatedCaseId] = useState<number | null>(null);
  const [caseError, setCaseError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentMerchant = merchants.find((m) => m.id === merchantId);

  // Reset when merchant changes
  useEffect(() => {
    setSelectedFile(null);
    setPreviewUrl(null);
    setResult(null);
    setErrorMsg(null);
    setCreatedCaseId(null);
    setCaseError(null);
  }, [merchantId]);

  const handleFileSelect = (file: File) => {
    setErrorMsg(null);
    setResult(null);
    setCreatedCaseId(null);
    setCaseError(null);

    // Client-side extension validation
    const validExtensions = ["image/png", "image/jpeg", "image/jpg"];
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!validExtensions.includes(file.type) && !["png", "jpg", "jpeg"].includes(ext || "")) {
      setErrorMsg("Invalid file format. Please upload a PNG, JPG, or JPEG image.");
      return;
    }

    // Client-side size validation (5 MB limit)
    const MAX_SIZE = 5 * 1024 * 1024;
    if (file.size > MAX_SIZE) {
      setErrorMsg(`File size (${(file.size / (1024 * 1024)).toFixed(2)} MB) exceeds the 5 MB maximum limit.`);
      return;
    }

    setSelectedFile(file);
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleVerify = async () => {
    if (!selectedFile) return;

    setIsLoading(true);
    setErrorMsg(null);

    try {
      const res = await verifyScreenshot(merchantId, selectedFile);
      setResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to process screenshot.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateCase = async () => {
    if (!result || isCreatingCase) return;

    setIsCreatingCase(true);
    setCaseError(null);

    const utrRef = result.extracted.utr || result.ledger_record?.reference || null;
    const extractedAmt = result.extracted.amount_paise !== null ? formatINR(result.extracted.amount_paise) : "N/A";
    const ledgerAmt = result.ledger_record ? formatINR(result.ledger_record.amount_paise) : "N/A";

    try {
      const created = await createCase(merchantId, {
        case_type: "MISMATCH",
        description: `Verification discrepancy: ${result.reason}`,
        status: "OPEN",
        related_reference: utrRef,
        note: `Screenshot amount: ${extractedAmt}, Ledger amount: ${ledgerAmt}`,
      });
      setCreatedCaseId(created.id);
    } catch (err: any) {
      setCaseError(err.message || "Failed to create case.");
    } finally {
      setIsCreatingCase(false);
    }
  };

  const resetUpload = () => {
    setSelectedFile(null);
    setPreviewUrl(null);
    setResult(null);
    setErrorMsg(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div>
      <div className="view-header">
        <div>
          <h1 className="view-title">Verify Payment Screenshot</h1>
          <p className="view-subtitle">
            Deterministic verification against your transaction records ({currentMerchant?.name || "Merchant"})
          </p>
        </div>
      </div>

      {/* Mandatory Rule 8 statement */}
      <div className="rule8-notice">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <span>
          <strong>Important:</strong> A screenshot alone cannot prove payment. Verification is against the transaction record.
        </span>
      </div>

      {/* Upload Zone */}
      <div className="verify-card">
        <div
          className="upload-dropzone"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleInputChange}
            accept=".png,.jpg,.jpeg,image/png,image/jpeg"
            style={{ display: "none" }}
          />

          {previewUrl ? (
            <div className="preview-container" onClick={(e) => e.stopPropagation()}>
              <img src={previewUrl} alt="Screenshot preview" className="screenshot-preview" />
              <div className="preview-meta">
                <span>{selectedFile?.name}</span> ({(Number(selectedFile?.size || 0) / 1024).toFixed(1)} KB)
                <button
                  type="button"
                  className="btn-change-file"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Change file
                </button>
              </div>
            </div>
          ) : (
            <div className="dropzone-prompt">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="var(--color-navy)" strokeWidth="1.75">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <p className="dropzone-text">
                <strong>Click to upload</strong> or drag and drop customer payment screenshot
              </p>
              <p className="dropzone-hint">PNG, JPG, or JPEG up to 5 MB</p>
            </div>
          )}
        </div>

        {selectedFile && !result && (
          <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={resetUpload}
              disabled={isLoading}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleVerify}
              disabled={isLoading}
            >
              {isLoading ? "Verifying against ledger..." : "Verify Payment"}
            </button>
          </div>
        )}

        {/* Error message */}
        {errorMsg && (
          <div className="verify-error-box">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{errorMsg}</span>
          </div>
        )}
      </div>

      {/* Verification Result Section */}
      {result && (
        <div className="verification-results">
          {/* Duplicate Warning */}
          {result.duplicate_flag && (
            <div className="duplicate-alert">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <div>
                <strong>Duplicate Screenshot Notice:</strong> This image has already been submitted previously.
              </div>
            </div>
          )}

          {/* Outcome Banner */}
          <div className={`outcome-banner ${result.outcome.toLowerCase()}`}>
            <div className="outcome-header">
              <div className="outcome-icon-tag">
                {result.outcome === "VERIFIED" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                )}
                {result.outcome === "UNVERIFIED" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                )}
                {result.outcome === "MISMATCH" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2" />
                    <line x1="15" y1="9" x2="9" y2="15" />
                    <line x1="9" y1="9" x2="15" y2="15" />
                  </svg>
                )}
                <span className="outcome-title">{result.outcome}</span>
              </div>
              <span className="outcome-reason">{result.reason}</span>
            </div>

            <div className="outcome-next-step">
              <strong>Next Step:</strong> {result.next_step}
            </div>

            {result.outcome === "MISMATCH" && (
              <div className="case-action-row">
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
                    >
                      {isCreatingCase ? "Creating case..." : "Create case"}
                    </button>
                    {caseError && <span className="case-error-hint">{caseError}</span>}
                  </>
                )}
              </div>
            )}
          </div>

          {/* Comparison Table */}
          <div className="verify-card">
            <h3 className="section-title">Record Comparison</h3>
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>From Screenshot</th>
                  <th>In Our Records</th>
                </tr>
              </thead>
              <tbody>
                {/* UTR */}
                <tr className={result.conflicting_fields.includes("utr") ? "conflict" : result.matched_fields.includes("utr") ? "match" : ""}>
                  <td><strong>Reference (UTR)</strong></td>
                  <td style={{ fontFamily: "monospace" }}>
                    {result.extracted.utr || <span className="text-muted">Not found in image</span>}
                  </td>
                  <td style={{ fontFamily: "monospace" }}>
                    {result.ledger_record?.reference || <span className="text-muted">Not found</span>}
                  </td>
                </tr>

                {/* Amount */}
                <tr className={result.conflicting_fields.includes("amount") ? "conflict" : result.matched_fields.includes("amount") ? "match" : ""}>
                  <td><strong>Amount</strong></td>
                  <td>
                    {result.extracted.amount_paise !== null
                      ? formatINR(result.extracted.amount_paise)
                      : <span className="text-muted">Not found in image</span>}
                  </td>
                  <td>
                    {result.ledger_record
                      ? formatINR(result.ledger_record.amount_paise)
                      : <span className="text-muted">—</span>}
                  </td>
                </tr>

                {/* Status */}
                <tr className={result.conflicting_fields.includes("status") ? "conflict" : ""}>
                  <td><strong>Status</strong></td>
                  <td>
                    {result.extracted.status_text || <span className="text-muted">Not found in image</span>}
                  </td>
                  <td>
                    {result.ledger_record?.status || <span className="text-muted">—</span>}
                  </td>
                </tr>

                {/* Recipient */}
                <tr className={result.conflicting_fields.includes("recipient") ? "conflict" : ""}>
                  <td><strong>Recipient</strong></td>
                  <td>
                    {result.extracted.recipient || <span className="text-muted">Not found in image</span>}
                  </td>
                  <td>
                    {currentMerchant?.name || <span className="text-muted">—</span>}
                  </td>
                </tr>

                {/* Date / Time */}
                <tr>
                  <td><strong>Timestamp</strong></td>
                  <td>
                    {result.extracted.timestamp || <span className="text-muted">Not found in image</span>}
                  </td>
                  <td>
                    {result.ledger_record?.created_at_ist || <span className="text-muted">—</span>}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Evidence List */}
          <div className="verify-card">
            <h3 className="section-title">Decision Evidence</h3>
            <ul className="evidence-list">
              {result.evidence.map((ev, i) => (
                <li key={i}>{ev}</li>
              ))}
            </ul>
          </div>

          {/* Collapsible Raw OCR Text (strictly plain text, never HTML per Rule 7) */}
          <div className="verify-card">
            <button
              type="button"
              className="btn-toggle-ocr"
              onClick={() => setShowRawOcr(!showRawOcr)}
            >
              {showRawOcr ? "Hide Raw OCR Text" : "View Raw OCR Text"}
            </button>
            {showRawOcr && (
              <pre className="raw-ocr-display">
                {result.raw_text || "(No raw OCR text available)"}
              </pre>
            )}
          </div>

          <div style={{ textAlign: "center", marginTop: "1.5rem" }}>
            <button type="button" className="btn-secondary" onClick={resetUpload}>
              Verify Another Screenshot
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

