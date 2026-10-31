import { API_BASE_URL } from "./config";
import type {
  Merchant,
  DashboardResponse,
  VerificationResult,
  AgentResponse,
  CaseItem,
  CreateCasePayload,
  UpdateCasePayload,
  ReportResponse,
  ScamCheckResponse,
  LapsingResponse,
  CustomerChangeResponse,
  InventoryResponse,
  GuardrailResult,
  OutreachItem,
} from "./types";

export async function fetchMerchants(): Promise<Merchant[]> {
  const res = await fetch(`${API_BASE_URL}/api/merchants`);
  if (!res.ok) {
    throw new Error(`Failed to load merchants: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchDashboard(merchantId: number): Promise<DashboardResponse> {
  const res = await fetch(`${API_BASE_URL}/api/dashboard?merchant_id=${merchantId}`);
  if (!res.ok) {
    throw new Error(`Failed to load dashboard: ${res.statusText}`);
  }
  return res.json();
}

export async function verifyScreenshot(
  merchantId: number,
  file: File
): Promise<VerificationResult> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/verify?merchant_id=${merchantId}`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback to statusText
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export async function sendAgentMessage(
  merchantId: number,
  message: string
): Promise<AgentResponse> {
  const res = await fetch(`${API_BASE_URL}/api/agent?merchant_id=${merchantId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export async function fetchCases(merchantId: number): Promise<CaseItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/cases?merchant_id=${merchantId}`);
  if (!res.ok) {
    throw new Error(`Failed to load cases: ${res.statusText}`);
  }
  return res.json();
}

export async function createCase(
  merchantId: number,
  payload: CreateCasePayload
): Promise<CaseItem> {
  const res = await fetch(`${API_BASE_URL}/api/cases?merchant_id=${merchantId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export async function updateCase(
  merchantId: number,
  caseId: number,
  payload: UpdateCasePayload
): Promise<CaseItem> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}?merchant_id=${merchantId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export async function fetchReport(
  merchantId: number,
  date?: string
): Promise<ReportResponse> {
  const url = date
    ? `${API_BASE_URL}/api/report?merchant_id=${merchantId}&date=${encodeURIComponent(date)}`
    : `${API_BASE_URL}/api/report?merchant_id=${merchantId}`;

  const res = await fetch(url);
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export async function checkSmsMessage(
  merchantId: number,
  text: string
): Promise<ScamCheckResponse> {
  const res = await fetch(`${API_BASE_URL}/api/scam-check?merchant_id=${merchantId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),
  });

  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

// ============================================================================
// Growth Insights API Calls
// ============================================================================

export async function getLapsingCustomers(): Promise<LapsingResponse> {
  const res = await fetch(`${API_BASE_URL}/api/growth/customers/lapsing`);
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function getCustomerChange(customerId: number): Promise<CustomerChangeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/growth/customers/${customerId}/change`);
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function getInventoryInsights(): Promise<InventoryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/growth/inventory`);
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function previewTemplate(
  offerType: string,
  language: string,
  offerPct: number = 0
): Promise<{ message_text: string }> {
  const res = await fetch(`${API_BASE_URL}/api/growth/outreach/template-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ offer_type: offerType, language, offer_pct: offerPct }),
  });
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function checkGuardrail(customerId: number, offerPct: number): Promise<GuardrailResult> {
  const res = await fetch(`${API_BASE_URL}/api/growth/outreach/guardrail-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_id: customerId, offer_pct: offerPct }),
  });
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function createDraft(payload: {
  customer_id: number;
  language: string;
  offer_type: string;
  offer_pct: number;
  custom_text?: string;
}): Promise<OutreachItem> {
  const res = await fetch(`${API_BASE_URL}/api/growth/outreach/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function listOutreach(): Promise<OutreachItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/growth/outreach`);
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function updateOutreach(
  outreachId: number,
  action: string,
  messageText?: string
): Promise<OutreachItem> {
  const res = await fetch(`${API_BASE_URL}/api/growth/outreach/${outreachId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, message_text: messageText }),
  });
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}
