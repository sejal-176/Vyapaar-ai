import { useState, useEffect } from "react";
import {
  getLapsingCustomers,
  getCustomerChange,
  getInventoryInsights,
  previewTemplate,
  checkGuardrail,
  createDraft,
  listOutreach,
  updateOutreach,
} from "../api/client";
import type {
  LapsingResponse,
  LapsingCustomer,
  CustomerChangeResponse,
  InventoryResponse,
  OutreachItem,
  GuardrailResult,
} from "../api/types";

export function GrowthInsights() {
  const [activeSubTab, setActiveSubTab] = useState<"customers" | "inventory">("customers");

  // Customers data
  const [lapsingData, setLapsingData] = useState<LapsingResponse | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);
  const [customerDetail, setCustomerDetail] = useState<CustomerChangeResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Inventory data
  const [inventoryData, setInventoryData] = useState<InventoryResponse | null>(null);

  // Outreach drafts
  const [outreachList, setOutreachList] = useState<OutreachItem[]>([]);
  const [showDraftModal, setShowDraftModal] = useState(false);
  const [draftCustomerId, setDraftCustomerId] = useState<number | null>(null);
  const [draftCustomerToken, setDraftCustomerToken] = useState<string>("");
  const [draftLanguage, setDraftLanguage] = useState<string>("en");
  const [draftOfferType, setDraftOfferType] = useState<string>("NONE");
  const [draftOfferPct, setDraftOfferPct] = useState<string>("");
  const [draftMessageText, setDraftMessageText] = useState<string>("");
  const [guardrailResult, setGuardrailResult] = useState<GuardrailResult | null>(null);
  const [draftSubmitting, setDraftSubmitting] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);

  // Loading & error states
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [custRes, invRes, outRes] = await Promise.all([
        getLapsingCustomers(),
        getInventoryInsights(),
        listOutreach(),
      ]);
      setLapsingData(custRes);
      setInventoryData(invRes);
      setOutreachList(outRes);

      // Auto-select first named lapsing customer if available
      if (custRes.named.length > 0 && !selectedCustomerId) {
        setSelectedCustomerId(custRes.named[0].id);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load growth preview data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // When selectedCustomerId changes, fetch detail
  useEffect(() => {
    if (!selectedCustomerId) {
      setCustomerDetail(null);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    getCustomerChange(selectedCustomerId)
      .then((data) => {
        if (!cancelled) setCustomerDetail(data);
      })
      .catch((err) => {
        if (!cancelled) console.error("Error loading customer detail:", err);
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCustomerId]);

  // Handle draft modal open
  const openDraftModal = (cust: LapsingCustomer) => {
    setDraftCustomerId(cust.id);
    setDraftCustomerToken(cust.payer_token);
    setDraftLanguage("en");
    setDraftOfferType("NONE");
    setDraftOfferPct("");
    setDraftError(null);
    setGuardrailResult(null);

    // Initial template preview
    previewTemplate("NONE", "en", 0)
      .then((res) => setDraftMessageText(res.message_text))
      .catch(() => {});

    setShowDraftModal(true);
  };

  // Re-fetch template preview when language or offer changes
  const handleOfferChange = async (newType: string, newLang: string, pctStr: string) => {
    setDraftOfferType(newType);
    setDraftLanguage(newLang);
    setDraftOfferPct(pctStr);
    setDraftError(null);

    const pctNum = parseInt(pctStr, 10) || 0;

    if (newType === "PERCENT" && draftCustomerId && pctStr !== "") {
      try {
        const gr = await checkGuardrail(draftCustomerId, pctNum);
        setGuardrailResult(gr);
      } catch (err: any) {
        setGuardrailResult(null);
      }
    } else {
      setGuardrailResult(null);
    }

    try {
      const res = await previewTemplate(newType, newLang, pctNum);
      setDraftMessageText(res.message_text);
    } catch {
      // keep current text
    }
  };

  const handleSaveDraft = async () => {
    if (!draftCustomerId) return;
    setDraftSubmitting(true);
    setDraftError(null);
    try {
      const pctNum = parseInt(draftOfferPct, 10) || 0;
      await createDraft({
        customer_id: draftCustomerId,
        language: draftLanguage,
        offer_type: draftOfferType,
        offer_pct: pctNum,
        custom_text: draftMessageText,
      });
      setShowDraftModal(false);
      // Refresh outreach list
      const updated = await listOutreach();
      setOutreachList(updated);
    } catch (err: any) {
      setDraftError(err?.message || "Failed to create draft.");
    } finally {
      setDraftSubmitting(false);
    }
  };

  const handleOutreachAction = async (outreachId: number, action: string) => {
    try {
      await updateOutreach(outreachId, action);
      const updated = await listOutreach();
      setOutreachList(updated);
    } catch (err: any) {
      alert(`Action failed: ${err?.message || "Unknown error"}`);
    }
  };

  const handleCopyText = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopyFeedback(true);
    setTimeout(() => setCopyFeedback(false), 2000);
  };

  if (loading) {
    return (
      <div className="growth-screen">
        <div className="growth-card growth-loading">
          <div className="loading-spinner" />
          <p>Loading Growth Insights preview...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="growth-screen">
        <div className="growth-card growth-error">
          <p className="error-title">Unable to load Growth Insights</p>
          <p className="error-desc">{error}</p>
          <button className="btn btn-secondary" onClick={loadData}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  const namedCount = lapsingData?.named.length || 0;
  const notNamedCount = lapsingData?.not_named_count || 0;

  return (
    <div className="growth-screen">
      {/* Top Disclaimer Banner */}
      <div className="growth-top-banner">
        <span className="banner-badge">Preview</span>
        <span className="banner-text">
          Preview on a separate synthetic dataset. Not connected to the payment ledger.
          Shows what insights customer and billing data could enable.
        </span>
      </div>

      {/* Sub Tab Navigation */}
      <div className="growth-subnav">
        <button
          className={`growth-tab-btn ${activeSubTab === "customers" ? "active" : ""}`}
          onClick={() => setActiveSubTab("customers")}
        >
          <span className="tab-icon">👥</span>
          Customers Visiting Less
          {namedCount > 0 && <span className="tab-pill">{namedCount}</span>}
        </button>
        <button
          className={`growth-tab-btn ${activeSubTab === "inventory" ? "active" : ""}`}
          onClick={() => setActiveSubTab("inventory")}
        >
          <span className="tab-icon">📦</span>
          Inventory & Pace
          {inventoryData?.slow_movers && inventoryData.slow_movers.length > 0 && (
            <span className="tab-pill alert">{inventoryData.slow_movers.length}</span>
          )}
        </button>
      </div>

      {/* ==================================================================== */}
      {/* Customers Sub-Tab */}
      {/* ==================================================================== */}
      {activeSubTab === "customers" && (
        <div className="growth-tab-content">
          {/* Header Summary */}
          <div className="growth-header-card">
            <div className="growth-header-stats">
              <div className="header-stat-main">
                <span className="stat-number">{namedCount}</span>
                <span className="stat-label">opted-in customers are visiting less</span>
              </div>
              {notNamedCount > 0 && (
                <div className="header-stat-secondary">
                  <span className="stat-bullet">ℹ️</span>
                  <span>
                    <strong>{notNamedCount}</strong> more are lapsing but have not opted in to messages
                  </span>
                </div>
              )}
            </div>
            <p className="growth-how-text">{lapsingData?.how_we_measure}</p>
          </div>

          <div className="growth-two-col">
            {/* Lapsing Table */}
            <div className="growth-card col-table">
              <h3 className="section-title">Lapsing Customers (Opted-in)</h3>
              {namedCount === 0 ? (
                <div className="empty-state-card">
                  <p>No opted-in customers are currently visiting less.</p>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="growth-table">
                    <thead>
                      <tr>
                        <th>Customer</th>
                        <th>Usual Gap</th>
                        <th>Last Visit</th>
                        <th>Spend / Visit</th>
                        <th>Main Driver</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lapsingData?.named.map((c) => {
                        const isSelected = selectedCustomerId === c.id;
                        return (
                          <tr
                            key={c.id}
                            className={`clickable-row ${isSelected ? "selected" : ""}`}
                            onClick={() => setSelectedCustomerId(c.id)}
                          >
                            <td>
                              <span className="token-badge">{c.payer_token}</span>
                            </td>
                            <td>{c.usual_gap_days} days</td>
                            <td>
                              <span className="days-lapse-pill">
                                {c.days_since_last_visit} days ago
                              </span>
                            </td>
                            <td>
                              <div className="spend-cell">
                                <span className="old-val">{c.spend_per_visit_before_inr}</span>
                                <span className="arrow">→</span>
                                <span className="new-val">{c.spend_per_visit_now_inr}</span>
                              </div>
                            </td>
                            <td>
                              <span className={`driver-pill ${c.main_driver}`}>
                                {c.main_driver === "fewer_visits" && "📉 Fewer visits"}
                                {c.main_driver === "smaller_basket" && "🛒 Smaller basket"}
                                {c.main_driver === "mixed" && "⚖️ Mixed"}
                              </span>
                            </td>
                            <td>
                              <button
                                className="btn-table-action"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openDraftModal(c);
                                }}
                              >
                                Draft message
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Customer Detail Panel */}
            <div className="growth-card col-detail">
              <h3 className="section-title">Customer Inspection</h3>
              {loadingDetail ? (
                <div className="detail-loading">
                  <div className="loading-spinner" />
                  <p>Analyzing customer breakdown...</p>
                </div>
              ) : !customerDetail ? (
                <div className="empty-state-card">
                  <p>Select a customer from the table to view their breakdown.</p>
                </div>
              ) : (
                <div className="detail-body">
                  <div className="detail-header-row">
                    <span className="token-large">{customerDetail.payer_token}</span>
                    <span className="consent-pill">{customerDetail.consent_status}</span>
                  </div>

                  {/* Decomposition Box */}
                  <div className="detail-box decomposition">
                    <h4 className="box-title">Spend Change Breakdown</h4>
                    <p className="summary-sentence">{customerDetail.driver_summary}</p>
                    <div className="split-pills-row">
                      <div className="split-pill">
                        <span className="split-label">Visits effect:</span>
                        <span className="split-val">{customerDetail.visits_effect_inr}</span>
                      </div>
                      <div className="split-pill">
                        <span className="split-label">Basket effect:</span>
                        <span className="split-val">{customerDetail.basket_effect_inr}</span>
                      </div>
                      <div className="split-pill total">
                        <span className="split-label">Total change:</span>
                        <span className="split-val">{customerDetail.spend_change_inr}</span>
                      </div>
                    </div>
                  </div>

                  {/* Billed Items Changed */}
                  <div className="detail-box">
                    <h4 className="box-title">Billed Items Changed per Visit</h4>
                    {customerDetail.products_changed.length === 0 ? (
                      <p className="muted-text">No significant item quantity changes.</p>
                    ) : (
                      <ul className="products-changed-list">
                        {customerDetail.products_changed.map((p, idx) => (
                          <li key={idx} className="product-change-item">
                            <span className="p-name">{p.product_name}:</span>
                            <span className="p-values">
                              {p.before_avg} before, {p.now_avg} now
                            </span>
                            <span className={`p-diff ${p.change < 0 ? "neg" : "pos"}`}>
                              ({p.change > 0 ? `+${p.change}` : p.change} / visit)
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* Worth Checking Fixed Questions */}
                  <div className="detail-box worth-checking-box">
                    <h4 className="box-title">Worth checking</h4>
                    <ul className="worth-checking-list">
                      {customerDetail.worth_checking.map((q, idx) => (
                        <li key={idx} className="worth-checking-item">
                          {q}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <button
                    className="btn btn-primary btn-block"
                    onClick={() => {
                      const matched = lapsingData?.named.find(
                        (n) => n.id === customerDetail.customer_id
                      );
                      if (matched) openDraftModal(matched);
                    }}
                  >
                    Draft message for {customerDetail.payer_token}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Outreach Activity Feed */}
          {outreachList.length > 0 && (
            <div className="growth-card outreach-feed-card">
              <h3 className="section-title">Message Drafts & History</h3>
              <div className="outreach-grid">
                {outreachList.map((item) => (
                  <div key={item.id} className={`outreach-card status-${item.status.toLowerCase()}`}>
                    <div className="outreach-header">
                      <span className="token-badge">{item.payer_token}</span>
                      <span className={`status-badge ${item.status.toLowerCase()}`}>
                        {item.status === "DRAFT" && "📝 Draft"}
                        {item.status === "APPROVED" && "✅ Approved"}
                        {item.status === "MARKED_SENT" && "📤 Marked sent"}
                        {item.status === "DISMISSED" && "✖ Dismissed"}
                      </span>
                    </div>

                    <p className="outreach-text">{item.message_text}</p>

                    <div className="outreach-meta">
                      <span>Language: {item.language.toUpperCase()}</span>
                      <span>Offer: {item.offer_type}</span>
                      {item.offer_pct > 0 && <span>({item.offer_pct}%)</span>}
                    </div>

                    <div className="outreach-actions">
                      <button
                        className="btn-tiny"
                        onClick={() => handleCopyText(item.message_text)}
                      >
                        {copyFeedback ? "Copied!" : "Copy message"}
                      </button>

                      {item.status === "DRAFT" && (
                        <>
                          <button
                            className="btn-tiny btn-action"
                            onClick={() => handleOutreachAction(item.id, "approve")}
                          >
                            Approve
                          </button>
                          <button
                            className="btn-tiny btn-dismiss"
                            onClick={() => handleOutreachAction(item.id, "dismiss")}
                          >
                            Dismiss
                          </button>
                        </>
                      )}

                      {item.status === "APPROVED" && (
                        <button
                          className="btn-tiny btn-action"
                          onClick={() => handleOutreachAction(item.id, "mark_sent")}
                        >
                          Mark as sent
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ==================================================================== */}
      {/* Inventory Sub-Tab */}
      {/* ==================================================================== */}
      {activeSubTab === "inventory" && (
        <div className="growth-tab-content">
          {/* Inventory Disclaimer Note */}
          <div className="growth-notice-card">
            <span>ℹ️</span>
            <span>{inventoryData?.note}</span>
          </div>

          {/* Slow Movers Section */}
          {inventoryData?.slow_movers && inventoryData.slow_movers.length > 0 && (
            <div className="growth-card slow-movers-card">
              <h3 className="section-title alert-title">
                <span>⚠️</span> Slow Movers Flagged
              </h3>
              <div className="slow-movers-list">
                {inventoryData.slow_movers.map((sm) => (
                  <div key={sm.product_id} className="slow-mover-banner">
                    <span className="sm-name">{sm.product_name}</span>
                    <span className="sm-drop">Units dropped {sm.drop_pct}%</span>
                    <span className="sm-detail">
                      ({sm.units_prev14} {sm.unit}s previously → {sm.units_last14} {sm.unit}s in last 14 days)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Product Table */}
          <div className="growth-card">
            <h3 className="section-title">Product Stock & Pace</h3>
            <div className="table-responsive">
              <table className="growth-table">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Price</th>
                    <th>Cost Price</th>
                    <th>Stock you entered</th>
                    <th>Usual Pace</th>
                    <th>Days Left</th>
                    <th>Status</th>
                    <th>14-Day Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {inventoryData?.products.map((p) => {
                    return (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.name}</strong>
                          <span className="unit-sub"> per {p.unit}</span>
                        </td>
                        <td>{p.price_inr}</td>
                        <td>
                          {p.cost_price_inr ? (
                            <span>{p.cost_price_inr}</span>
                          ) : (
                            <span className="muted-text">Not entered</span>
                          )}
                        </td>
                        <td>
                          <span className="stock-val">{p.stock_on_hand}</span> {p.unit}s
                        </td>
                        <td>
                          {p.velocity > 0 ? (
                            <span>{p.velocity} {p.unit}s / day</span>
                          ) : (
                            <span className="muted-text">—</span>
                          )}
                        </td>
                        <td>
                          {p.days_left !== null ? (
                            <span className={`days-left-val ${p.days_left < 3 ? "urgent" : ""}`}>
                              {p.days_left} days
                            </span>
                          ) : (
                            <span className="muted-text">—</span>
                          )}
                        </td>
                        <td>
                          <span
                            className={`stock-status-pill ${
                              p.status === "Low stock"
                                ? "low"
                                : p.status === "OK"
                                ? "ok"
                                : "none"
                            }`}
                          >
                            {p.status === "Low stock" && "⚠️ Low stock"}
                            {p.status === "OK" && "✅ OK"}
                            {p.status === "No recent units" && "⏸ No recent units"}
                          </span>
                        </td>
                        <td>
                          {p.trend_pct !== null ? (
                            <span className={`trend-val ${p.trend_pct < 0 ? "neg" : "pos"}`}>
                              {p.trend_pct > 0 ? `+${p.trend_pct}%` : `${p.trend_pct}%`}
                            </span>
                          ) : (
                            <span className="muted-text">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="table-footnote">
              * Usual pace is based on median units billed per active day over the last 28 days.
            </p>
          </div>
        </div>
      )}

      {/* Draft Message Modal Dialog */}
      {showDraftModal && (
        <div className="modal-overlay" onClick={() => setShowDraftModal(false)}>
          <div className="modal-content draft-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Draft Message for {draftCustomerToken}</h3>
              <button className="btn-close" onClick={() => setShowDraftModal(false)}>
                ✕
              </button>
            </div>

            {/* Mandatory Safety Notice */}
            <div className="modal-safety-banner">
              <span>🛡️</span>
              <span>VyapaarAI never sends messages. You send it yourself.</span>
            </div>

            {draftError && <div className="modal-error-box">{draftError}</div>}

            <div className="modal-form">
              {/* Language Selector */}
              <div className="form-group">
                <label>Language</label>
                <select
                  value={draftLanguage}
                  onChange={(e) =>
                    handleOfferChange(draftOfferType, e.target.value, draftOfferPct)
                  }
                >
                  <option value="en">English</option>
                  <option value="hi">Hindi (हिंदी)</option>
                  <option value="mr">Marathi (मराठी)</option>
                </select>
              </div>

              {/* Offer Type */}
              <div className="form-group">
                <label>Offer Type</label>
                <select
                  value={draftOfferType}
                  onChange={(e) =>
                    handleOfferChange(e.target.value, draftLanguage, draftOfferPct)
                  }
                >
                  <option value="NONE">No discount (Friendly hello)</option>
                  <option value="LOYALTY_STAMP">Loyalty stamp</option>
                  <option value="PERCENT">Percentage concession</option>
                </select>
              </div>

              {/* Percent Offer Input (no default!) */}
              {draftOfferType === "PERCENT" && (
                <div className="form-group">
                  <label>Concession percentage (max 10%)</label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    placeholder="Enter percentage (e.g. 5)"
                    value={draftOfferPct}
                    onChange={(e) =>
                      handleOfferChange(draftOfferType, draftLanguage, e.target.value)
                    }
                  />

                  {/* Live Guardrail Result */}
                  {guardrailResult && (
                    <div
                      className={`guardrail-banner ${
                        guardrailResult.allowed ? "allowed" : "refused"
                      }`}
                    >
                      <span className="gr-icon">{guardrailResult.allowed ? "✅" : "⚠️"}</span>
                      <span className="gr-reason">{guardrailResult.reason}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Editable Message Box */}
              <div className="form-group">
                <label>Message Text</label>
                <textarea
                  rows={4}
                  value={draftMessageText}
                  onChange={(e) => setDraftMessageText(e.target.value)}
                />
              </div>

              <div className="modal-actions-row">
                <button
                  className="btn btn-secondary"
                  onClick={() => handleCopyText(draftMessageText)}
                >
                  {copyFeedback ? "Copied!" : "Copy message"}
                </button>
                <div className="right-actions">
                  <button
                    className="btn btn-outline"
                    onClick={() => setShowDraftModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={
                      draftSubmitting ||
                      (draftOfferType === "PERCENT" &&
                        (!guardrailResult || !guardrailResult.allowed))
                    }
                    onClick={handleSaveDraft}
                  >
                    {draftSubmitting ? "Saving..." : "Save Draft"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="growth-footer">
        <p>Pseudonymous customers. Synthetic demo data.</p>
      </footer>
    </div>
  );
}
