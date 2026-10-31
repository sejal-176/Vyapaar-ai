"""Evaluation script for the OCR & verification pipeline.
Runs all screenshots in testdata/screenshots/ through preprocess -> extract -> verify
against the seeded vyapaar.db and evaluates outcomes against expected.json.
Never hardcodes results.
"""
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
from backend.db import SessionLocal
from backend.verification import preprocess, extract_fields, verify


def eval_ocr():
    screenshots_dir = PROJECT_ROOT / "testdata" / "screenshots"
    expected_path = screenshots_dir / "expected.json"

    if not expected_path.exists():
        print(f"Error: {expected_path} not found. Run scripts/make_test_images.py first.")
        sys.exit(1)

    with open(expected_path, "r", encoding="utf-8") as f:
        expected_data = json.load(f)

    db = SessionLocal()
    merchant_id = 1  # Testing against Sharma Tea Stall

    results = []
    failed_details = []

    print("=" * 80)
    print(f"{'FILE':<22} | {'EXPECTED':<12} | {'GOT':<12} | {'RESULT':<8} | NOTES")
    print("=" * 80)

    try:
        # Sort files so 01_match to 06_injection run in order
        image_files = sorted([p for p in screenshots_dir.glob("*.png")])

        pass_count = 0
        total_count = len(image_files)

        for img_path in image_files:
            filename = img_path.name
            expected_meta = expected_data.get(filename, {})
            expected_outcome = expected_meta.get("expected_outcome", "UNKNOWN")
            acceptable_outcomes = expected_meta.get("acceptable_outcomes", [expected_outcome])

            with open(img_path, "rb") as f:
                image_bytes = f.read()

            try:
                # 1. Preprocess
                prep_result = preprocess(image_bytes, filename)
                # 2. Extract
                fields = extract_fields(prep_result["variants"])
                # 3. Verify
                res = verify(
                    db=db,
                    merchant_id=merchant_id,
                    fields=fields,
                    image_hash=prep_result["image_hash"],
                    raw_text=fields.raw_text,
                )
                got_outcome = res["outcome"]

            except Exception as e:
                got_outcome = f"ERROR: {e}"
                fields = None

            is_pass = got_outcome in acceptable_outcomes
            if is_pass:
                pass_count += 1
                status_str = "PASS"
            else:
                status_str = "FAIL"
                failed_details.append({
                    "file": filename,
                    "expected": expected_outcome,
                    "got": got_outcome,
                    "raw_text": fields.raw_text if fields else "N/A",
                    "extracted": fields.__dict__ if fields else {},
                })

            desc = expected_meta.get("description", "")
            print(f"{filename:<22} | {expected_outcome:<12} | {got_outcome:<12} | {status_str:<8} | {desc}")

        print("=" * 80)
        print(f"Summary: {pass_count}/{total_count} images passed expected outcome.")
        print("=" * 80)

        if failed_details:
            print("\nDetailed Diagnostic for Failed Images:")
            for item in failed_details:
                print(f"\n--- {item['file']} ---")
                print(f"Expected: {item['expected']}")
                print(f"Got: {item['got']}")
                print(f"Extracted fields: {item['extracted']}")
                print(f"Raw OCR Text:\n{item['raw_text']}")

    finally:
        db.close()


if __name__ == "__main__":
    eval_ocr()

