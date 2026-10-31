import { useEffect, useState } from "react";
import type { Merchant, DashboardResponse } from "./api/types";
import { fetchMerchants, fetchDashboard } from "./api/client";
import { Dashboard } from "./components/Dashboard";
import { Verify } from "./components/Verify";
import { Assistant } from "./components/Assistant";
import { Cases } from "./components/Cases";
import { Report } from "./components/Report";

type TabKey = "dashboard" | "assistant" | "verify" | "cases" | "report";

export default function App() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [selectedMerchantId, setSelectedMerchantId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("dashboard");

  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Load merchants on initial mount
  useEffect(() => {
    let isMounted = true;
    fetchMerchants()
      .then((data) => {
        if (!isMounted) return;
        setMerchants(data);
        if (data.length > 0) {
          setSelectedMerchantId(data[0].id);
        }
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err.message || "Could not connect to backend server.");
        setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Fetch dashboard data whenever selectedMerchantId changes
  const loadDashboard = (merchantId: number) => {
    setIsLoading(true);
    setError(null);
    fetchDashboard(merchantId)
      .then((res) => {
        setDashboardData(res);
        setIsLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load dashboard data.");
        setIsLoading(false);
      });
  };

  useEffect(() => {
    if (selectedMerchantId !== null) {
      loadDashboard(selectedMerchantId);
    }
  }, [selectedMerchantId]);

  const handleMerchantChange = (newId: number) => {
    setSelectedMerchantId(newId);
  };

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="app-header">
        <div className="brand">
          <div className="brand-icon">V</div>
          <div className="brand-name">
            Vyapaar<span>AI</span>
          </div>
        </div>

        <div className="header-right">
          <div className="merchant-select-wrapper">
            <span className="merchant-select-label">Merchant:</span>
            <select
              className="merchant-select"
              value={selectedMerchantId ?? ""}
              onChange={(e) => handleMerchantChange(Number(e.target.value))}
              disabled={merchants.length === 0}
            >
              {merchants.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.business_type})
                </option>
              ))}
            </select>
          </div>
          <span className="demo-badge">Demo data (synthetic)</span>
        </div>
      </header>

      {/* Main Body with Sidebar + View */}
      <div className="app-body">
        {/* Desktop Sidebar */}
        <aside className="sidebar">
          <button
            className={`nav-item ${activeTab === "dashboard" ? "active" : ""}`}
            onClick={() => setActiveTab("dashboard")}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="9" rx="1" />
              <rect x="14" y="3" width="7" height="5" rx="1" />
              <rect x="14" y="12" width="7" height="9" rx="1" />
              <rect x="3" y="16" width="7" height="5" rx="1" />
            </svg>
            Dashboard
          </button>

          <button
            className={`nav-item ${activeTab === "assistant" ? "active" : ""}`}
            onClick={() => setActiveTab("assistant")}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            Assistant
          </button>

          <button
            className={`nav-item ${activeTab === "verify" ? "active" : ""}`}
            onClick={() => setActiveTab("verify")}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
            Verify
          </button>

          <button
            className={`nav-item ${activeTab === "cases" ? "active" : ""}`}
            onClick={() => setActiveTab("cases")}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            Cases
          </button>

          <button
            className={`nav-item ${activeTab === "report" ? "active" : ""}`}
            onClick={() => setActiveTab("report")}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
              <path d="M22 12A10 10 0 0 0 12 2v10z" />
            </svg>
            Report
          </button>
        </aside>

        {/* Content View */}
        <main className="main-content">
          {activeTab === "dashboard" ? (
            isLoading ? (
              <div className="state-container">
                <div className="state-title">Loading digital collections...</div>
                <div className="state-text">Fetching transaction ledger data for this merchant.</div>
              </div>
            ) : error ? (
              <div className="state-container">
                <div className="state-title" style={{ color: "var(--color-danger)" }}>
                  Unable to load data
                </div>
                <div className="state-text">{error}</div>
                {selectedMerchantId !== null && (
                  <button
                    className="btn-retry"
                    onClick={() => loadDashboard(selectedMerchantId)}
                  >
                    Retry
                  </button>
                )}
              </div>
            ) : dashboardData ? (
              <Dashboard data={dashboardData} />
            ) : (
              <div className="state-container">
                <div className="state-title">No data available</div>
                <div className="state-text">There are no records for this merchant.</div>
              </div>
            )
          ) : activeTab === "assistant" ? (
            selectedMerchantId !== null ? (
              <Assistant merchantId={selectedMerchantId} merchants={merchants} />
            ) : (
              <div className="state-container">
                <div className="state-title">Please select a merchant</div>
              </div>
            )
          ) : activeTab === "verify" ? (
            selectedMerchantId !== null ? (
              <Verify
                merchantId={selectedMerchantId}
                merchants={merchants}
                onNavigateToCases={() => setActiveTab("cases")}
              />
            ) : (
              <div className="state-container">
                <div className="state-title">Please select a merchant</div>
              </div>
            )
          ) : activeTab === "cases" ? (
            selectedMerchantId !== null ? (
              <Cases merchantId={selectedMerchantId} merchants={merchants} />
            ) : (
              <div className="state-container">
                <div className="state-title">Please select a merchant</div>
              </div>
            )
          ) : activeTab === "report" ? (
            selectedMerchantId !== null ? (
              <Report merchantId={selectedMerchantId} merchants={merchants} />
            ) : (
              <div className="state-container">
                <div className="state-title">Please select a merchant</div>
              </div>
            )
          ) : null}
        </main>
      </div>

      {/* Mobile Bottom Navigation */}
      <nav className="bottom-nav">
        <button
          className={`bottom-nav-item ${activeTab === "dashboard" ? "active" : ""}`}
          onClick={() => setActiveTab("dashboard")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="9" rx="1" />
            <rect x="14" y="3" width="7" height="5" rx="1" />
            <rect x="14" y="12" width="7" height="9" rx="1" />
            <rect x="3" y="16" width="7" height="5" rx="1" />
          </svg>
          Dashboard
        </button>

        <button
          className={`bottom-nav-item ${activeTab === "assistant" ? "active" : ""}`}
          onClick={() => setActiveTab("assistant")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          Assistant
        </button>

        <button
          className={`bottom-nav-item ${activeTab === "verify" ? "active" : ""}`}
          onClick={() => setActiveTab("verify")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
          Verify
        </button>

        <button
          className={`bottom-nav-item ${activeTab === "cases" ? "active" : ""}`}
          onClick={() => setActiveTab("cases")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          Cases
        </button>

        <button
          className={`bottom-nav-item ${activeTab === "report" ? "active" : ""}`}
          onClick={() => setActiveTab("report")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
            <path d="M22 12A10 10 0 0 0 12 2v10z" />
          </svg>
          Report
        </button>
      </nav>
    </div>
  );
}
