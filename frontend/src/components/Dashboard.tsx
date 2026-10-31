import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { DashboardResponse } from "../api/types";
import { formatINR, formatDateIST } from "../lib/format";

interface DashboardProps {
  data: DashboardResponse;
}

export const Dashboard: React.FC<DashboardProps> = ({ data }) => {
  const { summary, previous_summary, reference_date, trend, recent_transactions, ingestion_report } = data;

  const chartData = trend.map((item) => {
    const parts = item.date.split("-");
    const label = parts.length === 3 ? `${parts[2]}/${parts[1]}` : item.date;
    return {
      date: item.date,
      displayDate: label,
      collections_paise: item.collections_paise,
      rupees: item.collections_paise / 100,
    };
  });

  const getStatusBadge = (status: string) => {
    const s = status.toUpperCase();
    if (s === "SUCCESS") {
      return (
        <span className="status-chip success">
          <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
            <path d="M13.485 1.929a1 1 0 0 1 .15 1.407L6.636 12.33a1 1 0 0 1-1.46.064L1.364 8.582a1 1 0 0 1 1.414-1.414l3.1 3.1 6.2-7.989a1 1 0 0 1 1.407-.15z" />
          </svg>
          Success
        </span>
      );
    }
    if (s === "PENDING") {
      return (
        <span className="status-chip pending">
          <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
            <path d="M8 3.5a.5.5 0 0 0-1 0V9a.5.5 0 0 0 .252.434l3.5 2a.5.5 0 0 0 .496-.868L8 8.71V3.5z" />
            <path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm7-8A7 7 0 1 1 1 8a7 7 0 0 1 14 0z" />
          </svg>
          Pending
        </span>
      );
    }
    if (s === "FAILED") {
      return (
        <span className="status-chip failed">
          <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
            <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z" />
          </svg>
          Failed
        </span>
      );
    }
    return (
      <span className="status-chip refunded">
        <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
          <path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2v1z" />
          <path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466z" />
        </svg>
        Refunded
      </span>
    );
  };

  return (
    <div>
      <div className="view-header">
        <div>
          <h1 className="view-title">Collections Overview</h1>
          <p className="view-subtitle">
            Showing performance for {formatDateIST(reference_date)} ({data.merchant.name})
          </p>
        </div>
      </div>

      {/* 4 Summary Cards */}
      <div className="cards-grid">
        <div className="summary-card">
          <div className="card-label">Digital Collections</div>
          <div className="card-value">{formatINR(summary.collections_paise)}</div>
          <div className="card-meta">
            Prev: {formatINR(previous_summary.collections_paise)}
          </div>
        </div>

        <div className="summary-card">
          <div className="card-label">Successful Payments</div>
          <div className="card-value">{summary.success_count}</div>
          <div className="card-meta">
            Prev: {previous_summary.success_count} payments
          </div>
        </div>

        <div className="summary-card">
          <div className="card-label">Pending / Failed</div>
          <div className="card-value">
            {summary.pending_count} / {summary.failed_count}
          </div>
          <div className="card-meta">
            {summary.pending_count} pending, {summary.failed_count} failed
          </div>
        </div>

        <div className="summary-card">
          <div className="card-label">Average Ticket</div>
          <div className="card-value">{formatINR(summary.avg_ticket_paise)}</div>
          <div className="card-meta">
            Prev: {formatINR(previous_summary.avg_ticket_paise)}
          </div>
        </div>
      </div>

      {/* 14-day Trend Chart */}
      <div className="chart-card">
        <div className="chart-header">
          <div>
            <h2 className="chart-title">14-Day Digital Collections Trend</h2>
            <p className="chart-subtitle">Daily aggregate of successful payments</p>
          </div>
        </div>
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
              <XAxis dataKey="displayDate" stroke="#64748B" fontSize={12} tickLine={false} />
              <YAxis
                stroke="#64748B"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `₹${v >= 1000 ? (v / 1000).toFixed(0) + "k" : v}`}
              />
              <Tooltip
                formatter={(value: any) => [formatINR(Number(value) * 100), "Collections"]}
                labelFormatter={(label, payload) => {
                  if (payload && payload.length > 0 && payload[0].payload) {
                    return formatDateIST(payload[0].payload.date);
                  }
                  return label;
                }}
                contentStyle={{
                  backgroundColor: "#FFFFFF",
                  border: "1px solid #E2E8F0",
                  borderRadius: "8px",
                  boxShadow: "0 4px 6px -1px rgba(0,0,0,0.1)",
                }}
              />
              <Line
                type="monotone"
                dataKey="rupees"
                stroke="#002970"
                strokeWidth={2.5}
                dot={{ fill: "#00B9F1", strokeWidth: 2, r: 3.5 }}
                activeDot={{ r: 6, fill: "#002970" }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Validation Report Panel */}
      <div className="validation-card">
        <div className="validation-header">
          <div className="validation-title">Data Ingestion Report</div>
          <span className="demo-badge" style={{ backgroundColor: "#00B9F1", color: "#002970", borderColor: "#00B9F1" }}>
            Quarantine Active
          </span>
        </div>
        <p className="validation-notice">
          Rejected rows are kept in quarantine with a reason.
        </p>
        <div className="validation-stats">
          <div className="validation-stat-item">
            <span className="validation-stat-num" style={{ color: "var(--color-success)" }}>
              {ingestion_report.accepted}
            </span>
            <span className="validation-stat-label">Accepted Rows</span>
          </div>
          <div className="validation-stat-item">
            <span className="validation-stat-num" style={{ color: "var(--color-danger)" }}>
              {ingestion_report.rejected}
            </span>
            <span className="validation-stat-label">Quarantined Rows</span>
          </div>
        </div>
        {ingestion_report.rejected > 0 && (
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "0.35rem", fontWeight: 600 }}>
              REJECTION REASONS BREAKDOWN:
            </div>
            <div className="reasons-chips">
              {Object.entries(ingestion_report.reasons).map(([reason, count]) => (
                <span key={reason} className="reason-chip">
                  <strong>{reason}:</strong> {count}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Recent Transactions Table */}
      <div className="table-card">
        <h2 className="table-title">Recent Transactions</h2>
        {recent_transactions.length === 0 ? (
          <p style={{ color: "var(--color-muted)", fontSize: "0.85rem", padding: "1rem 0" }}>
            No recent transactions found.
          </p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Time (IST)</th>
                <th>Reference (UTR)</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody>
              {recent_transactions.map((tx) => (
                <tr key={tx.reference}>
                  <td>{tx.created_at_ist}</td>
                  <td style={{ fontFamily: "monospace", fontWeight: 600 }}>{tx.reference}</td>
                  <td style={{ fontWeight: 600 }}>{formatINR(tx.amount_paise)}</td>
                  <td>{getStatusBadge(tx.status)}</td>
                  <td style={{ fontSize: "0.75rem", color: "var(--color-muted)", fontWeight: 600 }}>
                    {tx.txn_type}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

