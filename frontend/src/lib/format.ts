/**
 * Formatting utilities for Indian Rupee currency and IST timestamps.
 * Rule 1: Money is stored as integer paise.
 * Rule 2: Display in IST.
 */

const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatINR(paise: number | null | undefined): string {
  if (paise === null || paise === undefined || isNaN(paise)) {
    return "";
  }
  const rupees = paise / 100;
  return inrFormatter.format(rupees);
}

export function formatDateIST(dateStr: string): string {
  if (!dateStr) return "";
  try {
    const [year, month, day] = dateStr.split("-").map(Number);
    if (!year || !month || !day) return dateStr;
    const d = new Date(year, month - 1, day);
    return d.toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export function formatDateTimeIST(dateTimeStr: string): string {
  if (!dateTimeStr) return "";
  // If in YYYY-MM-DD HH:MM:SS format
  return dateTimeStr;
}

