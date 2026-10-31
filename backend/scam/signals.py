"""Rule-based warning signal detection for SMS messages in English and Hinglish.
No AI or LLM is involved.
No risk scores or percentages.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlparse

OFFICIAL_DOMAINS = {
    "paytm.com",
    "paytm.in",
    "sbi.co.in",
    "hdfcbank.com",
    "icicibank.com",
    "axisbank.com",
}

SHORTENER_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "cutt.ly",
    "rb.gy",
    "is.gd",
    "ow.ly",
    "shorturl.at",
}

ODD_TLDS = {".xyz", ".top", ".click", ".buzz", ".icu"}

BRAND_SUSPECT_WORDS = ["paytm", "bank", "kyc", "refund", "reward"]

# Phrase-level patterns for English and Hinglish
PATTERNS = {
    "secrets": [
        (r"(?i)\b(?:share|send|tell|give)\s+(?:your\s+)?otp\b", "Requests sharing an OTP"),
        (r"(?i)\botp\s+(?:batao|bhejo|share\s+karo)\b", "Requests sharing an OTP (Hinglish)"),
        (r"(?i)\benter\s+(?:your\s+)?(?:upi\s+)?pin\b", "Requests entering a UPI PIN"),
        (r"(?i)\bpin\s+bhejo\b", "Requests sending a PIN"),
        (r"(?i)\b(?:enter|share|send)\s+cvv\b", "Requests CVV information"),
        (r"(?i)\b(?:enter|share|send)\s+password\b", "Requests password"),
    ],
    "pin_trick": [
        (r"(?i)\benter\s+(?:your\s+)?(?:upi\s+)?pin\s+(?:to\s+receive|to\s+get|for\s+credit)\b", "PIN is never needed to receive money"),
        (r"(?i)\baccept\s+collect\s+request\s+to\s+get\s+money\b", "Collect requests deduct money from your account"),
        (r"(?i)\bapprove\s+to\s+receive\s+refund\b", "Approving a request pays money out, never receives it"),
        (r"(?i)\bpin\s+daal(?:o|e)?\s+paise\s+l(?:ene|o)\b", "PIN is only used to send money, never to receive (Hinglish)"),
    ],
    "remote_access": [
        (r"(?i)\banydesk\b", "Requests installing AnyDesk remote desktop software"),
        (r"(?i)\bteamviewer\b", "Requests installing TeamViewer remote screen control"),
        (r"(?i)\bquicksupport\b", "Requests installing QuickSupport remote tool"),
        (r"(?i)\bscreen\s+share\b", "Requests screen sharing which exposes sensitive screens"),
    ],
    "urgency": [
        (r"(?i)\baccount\s+will\s+be\s+blocked\b", "Creates panic by threatening account blocking"),
        (r"(?i)\baccount\s+blocked\b", "Claims account is blocked to induce rushed action"),
        (r"(?i)\bwithin\s+24\s+hours\b", "Artificial urgency time limit"),
        (r"(?i)\bimmediately\b", "Demands immediate action"),
        (r"(?i)\bturant\b", "Urgent action demand (Hinglish)"),
        (r"(?i)\bblock\s+ho\s+jayega\b", "Threatens account suspension (Hinglish)"),
    ],
    "kyc_scare": [
        (r"(?i)\bkyc\s+expired\b", "False claim that KYC has expired"),
        (r"(?i)\bupdate\s+kyc\b", "Unsolicited prompt to update KYC"),
        (r"(?i)\baccount\s+suspended\b", "Claims account suspension"),
        (r"(?i)\bverify\s+your\s+account\b", "Unsolicited request to verify account"),
    ],
    "prize": [
        (r"(?i)\byou\s+have\s+won\b", "Prize or sweepstakes lure"),
        (r"(?i)\blottery\b", "Lottery claim"),
        (r"(?i)\bclaim\s+cashback\b", "Unsolicited cashback claim"),
        (r"(?i)\binaam\b", "Prize claim (Hinglish)"),
    ],
    "refund_trick": [
        (r"(?i)\bsent\s+by\s+mistake\b", "Social engineering claim of mistaken payment"),
        (r"(?i)\bwrongly\s+credited\b", "Claims payment was sent by mistake"),
        (r"(?i)\bplease\s+return\s+the\s+money\b", "Requests immediate refund of unverified payment"),
        (r"(?i)\bgalti\s+se\b", "Claims money sent by mistake (Hinglish)"),
    ],
}

# Regex to find links (http, https, www, bare domain with path or tld)
RE_URL = re.compile(
    r"(?i)\b((?:https?://|www\.)[^\s/$.?#].[^\s]*|[a-zA-Z0-9-]+\.(?:com|in|co\.in|org|net|xyz|top|click|buzz|icu|io|cc|me)(?:/[^\s]*)?)",
    re.IGNORECASE,
)
RE_IP = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _is_official_domain(host: str) -> bool:
    """Check if host is an exact match or subdomain of an official domain."""
    clean_host = host.lower()
    for official in OFFICIAL_DOMAINS:
        if clean_host == official or clean_host.endswith("." + official):
            return True
    return False


def _check_url_for_bad_link(url_str: str) -> list[dict]:
    """Inspect a URL against bad link rules."""
    signals = []
    normalized = url_str.strip().rstrip(".,;:)")
    if not normalized.startswith("http://") and not normalized.startswith("https://"):
        url_to_parse = "http://" + normalized
    else:
        url_to_parse = normalized

    try:
        parsed = urlparse(url_to_parse)
        host = (parsed.hostname or "").lower()
        if not host:
            return signals

        # 1. Plain HTTP instead of HTTPS (if original explicitly specified http://)
        if url_str.lower().startswith("http://"):
            signals.append({
                "category": "bad_link",
                "matched_text": url_str,
                "explanation": "Unencrypted HTTP link instead of secure HTTPS.",
            })

        # 2. Raw IP address host
        if RE_IP.match(host):
            signals.append({
                "category": "bad_link",
                "matched_text": url_str,
                "explanation": f"Link points to a raw IP address ({host}) rather than a trusted domain.",
            })
            return signals

        # 3. Known link shorteners
        if host in SHORTENER_DOMAINS or any(host.endswith("." + s) for s in SHORTENER_DOMAINS):
            signals.append({
                "category": "bad_link",
                "matched_text": url_str,
                "explanation": f"Shortened link ({host}) masks the true destination website.",
            })
            return signals

        # If it's an official domain, do not flag further domain checks
        if _is_official_domain(host):
            return signals

        # 4. Odd TLDs
        if any(host.endswith(tld) for tld in ODD_TLDS):
            signals.append({
                "category": "bad_link",
                "matched_text": url_str,
                "explanation": f"Domain uses a high-risk suspicious top-level domain ({host}).",
            })

        # 5. 3+ hyphens in host
        if host.count("-") >= 3:
            signals.append({
                "category": "bad_link",
                "matched_text": url_str,
                "explanation": f"Domain contains multiple hyphens ({host}), typical of spoofed lookalikes.",
            })

        # 6. Very long host (over 40 characters)
        if len(host) > 40:
            signals.append({
                "category": "bad_link",
                "matched_text": url_str,
                "explanation": f"Suspiciously long domain name ({len(host)} characters).",
            })

        # 7. Brand / KYC / refund keywords in an unofficial domain
        if any(b in host for b in BRAND_SUSPECT_WORDS):
            signals.append({
                "category": "bad_link",
                "matched_text": url_str,
                "explanation": f"Domain ({host}) includes bank/brand keywords but is not on the official allowlist.",
            })

    except Exception:
        pass

    return signals


def detect_signals(text: str) -> list[dict]:
    """Detect warning signals in message text using deterministic phrase matching.
    Returns: list of {category, matched_text, explanation}
    """
    if not text:
        return []

    signals: list[dict] = []
    seen_categories_and_text: set[tuple[str, str]] = set()

    def _add_signal(cat: str, matched: str, exp: str):
        key = (cat, matched.lower())
        if key not in seen_categories_and_text:
            seen_categories_and_text.add(key)
            signals.append({
                "category": cat,
                "matched_text": matched,
                "explanation": exp,
            })

    # 1. Phrase-based categories
    for cat, rules in PATTERNS.items():
        for pat, exp in rules:
            for m in re.finditer(pat, text):
                _add_signal(cat, m.group(0), exp)

    # 2. Bad link detection
    for m in RE_URL.finditer(text):
        url_found = m.group(0)
        link_signals = _check_url_for_bad_link(url_found)
        for s in link_signals:
            _add_signal(s["category"], s["matched_text"], s["explanation"])

    return signals
