import React, { useState, useEffect, useCallback } from "react";
import type { Merchant, ReportResponse } from "../api/types";
import { fetchReport } from "../api/client";
import { formatINR } from "../lib/format";

interface ReportProps {
  merchantId: number;
  merchants: Merchant[];
}

export const Report: React.FC<ReportProps> = ({ merchantId, merchants }) => {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const currentMerchant = merchants.find((m) => m.id === merchantId);

  const loadReport = useCallback(async (dateToFetch?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchReport(merchantId, dateToFetch);
      setReport(data);
      if (!selectedDate || !dateToFetch) {
        setSelectedDate(data.date);
      }
    } catch (err: any) {
      setError(err.message || "Failed to generate daily report.");
    } finally {
      setIsLoading(false);
    }
  }, [merchantId, selectedDate]);

  // Load initial report defaulting to latest data day when merchantId changes
  useEffect(() => {
    setSelectedDate("");
    loadReport();
  }, [merchantId]);

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedDate) {
      loadReport(selectedDate);
    }
  };

  const handleDownload = () => {
    if (!report) return;
    const blob = new Blob([report.text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const merchantSlug = currentMerchant?.name.toLowerCase().replace(/[^a-z0-9]+/g, "_") || "merchant";
    a.download = `daily_report_${merchantSlug}_${report.date}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="report-container">
      {/* Header */}
      <div className="view-header">
        <div>
          <h1 className="view-title">Daily Business Report</h1>
          <p className="view-subtitle">
            Auditable digital payment summary, comparison effects, and peak hours for {currentMerchant?.name}
          </p>
        </div>
      </div>

      {/* Control Toolbar */}
      <div className="report-toolbar">
        <form className="report-date-form" onSubmit={handleGenerate}>
          <label htmlFor="report-date-input" className="report-date-label">
            Select Date (IST):
          </label>
          <input
            id="report-date-input"
            type="date"
            className="report-date-input"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            disabled={isLoading}
            required
          />
          <button
            type="submit"
            className="btn-generate-report"
            disabled={isLoading || !selectedDate}
          >
            {isLoading ? "Generating..." : "Generate Report"}
          </button>
        </form>

        {report && (
          <button
            type="button"
            className="btn-download-report"
            onClick={handleDownload}
            title="Download report as plain text"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>Download .txt</span>
          </button>
        )}
      </div>

      {/* Main Content Area */}
      {isLoading ? (
        <div className="state-container">
          <div className="state-title">Generating daily report...</div>
          <div className="state-text">Computing collections summary, day-over-day effects, and peak activity.</div>
        </div>
      ) : error ? (
        <div className="state-container">
          <div className="state-title" style={{ color: "var(--color-danger)" }}>
            Unable to generate report
          </div>
          <div className="state-text">{error}</div>
          <button type="button" className="btn-retry" onClick={() => loadReport(selectedDate)}>
            Retry
          </button>
        </div>
      ) : report ? (
        <div className="report-content-grid">
          {/* Section 1: Rendered Cards */}
          <div className="report-sections">
            <h2 className="report-section-header">
              Report for {report.date} (IST)
            </h2>

            {/* Metrics Grid */}
            <div className="report-cards-grid">
              {/* Card 1: Summary */}
              <div className="report-card">
                <div className="report-card-title">Digital Collections Summary</div>
                <div className="report-card-main-stat">
                  {formatINR(report.sections.summary.collections_paise)}
                </div>
                <div className="report-card-substats">
                  <div>
                    <span>Successful:</span>
                    <strong>{report.sections.summary.success_count}</strong>
                  </div>
                  <div>
                    <span>Pending:</span>
                    <strong>{report.sections.summary.pending_count}</strong>
                  </div>
                  <div>
                    <span>Failed:</span>
                    <strong>{report.sections.summary.failed_count}</strong>
                  </div>
                  <div>
                    <span>Avg Ticket:</span>
                    <strong>{formatINR(report.sections.summary.avg_ticket_paise)}</strong>
                  </div>
                </div>
              </div>

              {/* Card 2: Day-over-Day Comparison */}
              <div className="report-card">
                <div className="report-card-title">Comparison with Previous Day</div>
                <div className="report-card-main-stat">
                  {report.sections.comparison.delta_collections_paise >= 0 ? "+" : ""}
                  {formatINR(report.sections.comparison.delta_collections_paise)}
                </div>
                <div className="report-card-substats">
                  <div>
                    <span>Volume Effect:</span>
                    <strong>{formatINR(report.sections.comparison.volume_effect)}</strong>
                  </div>
                  <div>
                    <span>Ticket Effect:</span>
                    <strong>{formatINR(report.sections.comparison.ticket_effect)}</strong>
                  </div>
                  <div>
                    <span>Primary Driver:</span>
                    <strong className="driver-tag">
                      {report.sections.comparison.main_driver === "volume"
                        ? "Volume change"
                        : report.sections.comparison.main_driver === "ticket_size"
                        ? "Ticket size change"
                        : "Mixed factors"}
                    </strong>
                  </div>
                </div>
              </div>

              {/* Card 3: Peak Hour Activity */}
              <div className="report-card">
                <div className="report-card-title">Peak Hourly Activity</div>
                <div className="report-card-main-stat" style={{ fontSize: "1.3rem" }}>
                  {report.sections.peak_hour.peak_hour_display}
                </div>
                <div className="report-card-substats">
                  <div>
                    <span>Peak Collections:</span>
                    <strong>{formatINR(report.sections.peak_hour.amount_paise)}</strong>
                  </div>
                  <div>
                    <span>Peak Payments:</span>
                    <strong>{report.sections.peak_hour.count} txns</strong>
                  </div>
                </div>
              </div>

              {/* Card 4: Open Cases */}
              <div className="report-card">
                <div className="report-card-title">Internal Follow-up Cases</div>
                <div className="report-card-main-stat">
                  {report.sections.open_cases}
                </div>
                <div className="report-card-substats">
                  <div>
                    <span>Active Cases:</span>
                    <strong>{report.sections.open_cases} require review</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Monospace Text Preview */}
          <div className="report-preview-section">
            <div className="report-preview-header">
              <span className="report-preview-title">Plain Text Monospace Preview</span>
              <span className="report-preview-badge">Ready for export / print</span>
            </div>
            <pre className="report-text-pre">{report.text}</pre>
          </div>
        </div>
      ) : null}
    </div>
  );
};

