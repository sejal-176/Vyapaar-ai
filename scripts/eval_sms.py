"""Evaluation script for SMS scam checker against testdata/sms/samples.json.
Loads samples, runs each message through the detection pipeline for Merchant 1,
compares outcome and signals against expectations, and outputs a formatted table.
"""
import json
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db import SessionLocal
from backend.api.scam import check_sms_message, ScamCheckRequest


def main():
    samples_file = Path(__file__).resolve().parent.parent / "testdata" / "sms" / "samples.json"
    if not samples_file.exists():
        print(f"Error: {samples_file} not found. Run make_sms_samples.py first.")
        sys.exit(1)

    with open(samples_file, "r", encoding="utf-8") as f:
        samples = json.load(f)

    db = SessionLocal()
    merchant_id = 1

    header = f"{'ID':<25} | {'EXP OUTCOME':<13} | {'GOT OUTCOME':<13} | {'EXP SIGNALS':<25} | {'GOT SIGNALS':<25} | {'STATUS':<6}"
    divider = "-" * len(header)
    print("\nVyapaarAI SMS Scam Detection Evaluation")
    print(divider)
    print(header)
    print(divider)

    passed_count = 0
    total_count = len(samples)

    try:
        for item in samples:
            sample_id = item["id"]
            text = item["text"]
            exp_outcome = item["expected_outcome"]
            exp_signals = sorted(list(set(item.get("expected_signal_categories", []))))

            # Run detection via check_sms_message
            req = ScamCheckRequest(text=text)
            resp = check_sms_message(payload=req, merchant_id=merchant_id, db=db)

            got_outcome = resp["ledger_check"]["outcome"]
            got_signals = sorted(list(set(s["category"] for s in resp["signals"])))

            outcome_ok = (got_outcome == exp_outcome)
            # Check if expected signals match or are subset if more general
            signals_ok = (got_signals == exp_signals)

            is_pass = outcome_ok and signals_ok
            if is_pass:
                passed_count += 1
                status_str = "PASS"
            else:
                status_str = "FAIL"

            exp_sig_str = ",".join(exp_signals) if exp_signals else "-"
            got_sig_str = ",".join(got_signals) if got_signals else "-"

            print(
                f"{sample_id:<25} | {exp_outcome:<13} | {got_outcome:<13} | {exp_sig_str:<25} | {got_sig_str:<25} | {status_str:<6}"
            )

    finally:
        db.close()

    print(divider)
    print(f"\nResult: {passed_count} / {total_count} passed\n")

    if passed_count == total_count:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
