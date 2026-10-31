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
