"""Synthetic data generator for VyapaarAI merchants.
Generates realistic 30-day transaction history with peak hours,
weekend effects, status distributions, and deliberate dirty rows.
"""
from datetime import date, datetime, time, timedelta
import random
from pathlib import Path
from backend.core.timeutil import IST


def generate_merchant_csv(
    merchant_id: int,
    output_path: str | Path,
    end_date: date | None = None,
    seed: int = 42,
) -> str:
    """Generate 30 full days of synthetic transactions ending yesterday.
    Columns: reference,amount,status,timestamp

    Merchant 1 (tea stall):
    - peaks at 8-10 and 17-20 IST, busier on weekends
    - amounts from {10, 20, 40, 60, 120} with small variation
    Merchant 2 (kirana):
    - steadier, peaks at 11-13 and 18-21 IST
    - amounts from 50 to 800

    Demo scenario:
    - Most recent day (yesterday) is clearly lower than the day before,
      primarily through fewer transactions (not smaller tickets).

    Injects ~10 dirty rows (duplicates, negative amount, missing timestamp,
    blank reference, unknown status, messy status text, formatted currency amount).
    """
    rng = random.Random(seed + merchant_id * 1000)

    if end_date is None:
        today_ist = datetime.now(IST).date()
        end_date = today_ist - timedelta(days=1)

    start_date = end_date - timedelta(days=29)

    rows = []
    # Track used references to ensure clean rows are unique 12-digit numbers
    # We will use 400000000000 + merchant_id * 100000000 + counter
    seq = 1

    current_day = start_date
    day_index = 0
    while current_day <= end_date:
        is_weekend = current_day.weekday() in (5, 6)
        is_yesterday = current_day == end_date
        is_day_before_yesterday = current_day == (end_date - timedelta(days=1))

        if merchant_id == 1:
            # Tea stall
            if is_yesterday:
                # Demo scenario: significantly fewer transactions
                tx_count = rng.randint(15, 20)
            elif is_day_before_yesterday:
                tx_count = rng.randint(55, 65)
            else:
                base_count = 50 if is_weekend else 38
                tx_count = rng.randint(base_count - 5, base_count + 8)

            # Hour distributions
            peak_morning = [8, 9, 10]
            peak_evening = [17, 18, 19, 20]
            other_hours = [6, 7, 11, 12, 13, 14, 15, 16, 21, 22]
            hour_pool = (peak_morning * 4) + (peak_evening * 5) + other_hours

            amounts_choices = [10, 20, 20, 40, 40, 60, 120]

        else:
            # Kirana store
            if is_yesterday:
                # Demo scenario: drop in transaction volume
                tx_count = rng.randint(12, 18)
            elif is_day_before_yesterday:
                tx_count = rng.randint(45, 55)
            else:
                base_count = 42 if is_weekend else 34
                tx_count = rng.randint(base_count - 4, base_count + 6)

            peak_midday = [11, 12, 13]
            peak_evening = [18, 19, 20, 21]
            other_hours = [7, 8, 9, 10, 14, 15, 16, 17, 22]
            hour_pool = (peak_midday * 4) + (peak_evening * 5) + other_hours

            amounts_choices = None  # Random between 50 and 800

        for _ in range(tx_count):
            h = rng.choice(hour_pool)
            m = rng.randint(0, 59)
            s = rng.randint(0, 59)
            tx_dt = datetime.combine(current_day, time(h, m, s))

            # Status weights: 90% SUCCESS, 5% PENDING, 3% FAILED, 2% REFUNDED
            roll = rng.random()
            if roll < 0.90:
                status = "SUCCESS"
            elif roll < 0.95:
                status = "PENDING"
            elif roll < 0.98:
                status = "FAILED"
            else:
                status = "REFUNDED"

            if merchant_id == 1:
                amt = rng.choice(amounts_choices)
            else:
                amt = rng.randint(50, 800)

            ref = f"{merchant_id}{seq:011d}"
            seq += 1

            rows.append({
                "reference": ref,
                "amount": str(amt),
                "status": status,
                "timestamp": tx_dt.strftime("%Y-%m-%d %H:%M:%S"),
            })

        current_day += timedelta(days=1)
        day_index += 1

    # Inject ~10 dirty rows (some rejected, some messy but valid)
    # Pick a reference from existing rows for duplicate testing
    sample_ref = rows[10]["reference"]
    sample_ref2 = rows[25]["reference"]

    dirty_rows = [
        # 1. Duplicate reference (reject -> duplicate)
        {
            "reference": sample_ref,
            "amount": "50",
            "status": "SUCCESS",
            "timestamp": f"{end_date} 10:15:00",
        },
        # 2. Duplicate reference 2 (reject -> duplicate)
        {
            "reference": sample_ref2,
            "amount": "100",
            "status": "SUCCESS",
            "timestamp": f"{end_date} 11:20:00",
        },
        # 3. Negative amount (reject -> invalid_amount)
        {
            "reference": f"{merchant_id}99999000001",
            "amount": "-50",
            "status": "SUCCESS",
            "timestamp": f"{end_date} 12:00:00",
        },
        # 4. Zero/non-numeric amount (reject -> invalid_amount)
        {
            "reference": f"{merchant_id}99999000002",
            "amount": "INVALID_AMT",
            "status": "SUCCESS",
            "timestamp": f"{end_date} 12:05:00",
        },
        # 5. Missing timestamp (reject -> missing_time)
        {
            "reference": f"{merchant_id}99999000003",
            "amount": "40",
            "status": "SUCCESS",
            "timestamp": "",
        },
        # 6. Unparseable timestamp (reject -> missing_time)
        {
            "reference": f"{merchant_id}99999000004",
            "amount": "40",
            "status": "SUCCESS",
            "timestamp": "invalid-timestamp",
        },
        # 7. Blank reference (reject -> blank_reference)
        {
            "reference": "   ",
            "amount": "60",
            "status": "SUCCESS",
            "timestamp": f"{end_date} 14:00:00",
        },
        # 8. Unknown status (reject -> unknown_status)
        {
            "reference": f"{merchant_id}99999000005",
            "amount": "80",
            "status": "CHARGEBACK",
            "timestamp": f"{end_date} 15:00:00",
        },
        # 9. Messy status text (VALID -> normalized to SUCCESS)
        {
            "reference": f"{merchant_id}99999000006",
            "amount": "20",
            "status": "Completed",
            "timestamp": f"{end_date} 16:00:00",
        },
        # 10. Messy status with trailing spaces (VALID -> normalized to SUCCESS)
        {
            "reference": f"{merchant_id}99999000007",
            "amount": "30",
            "status": "success ",
            "timestamp": f"{end_date} 16:30:00",
        },
        # 11. Formatted currency amount (VALID -> parsed to 125050 paise)
        {
            "reference": f"{merchant_id}99999000008",
            "amount": "₹1,250.50",
            "status": "SUCCESS",
            "timestamp": f"{end_date} 17:00:00",
        },
    ]

    # Insert dirty rows scattered near the end
    rows.extend(dirty_rows)

    # Sort rows by timestamp where possible, keeping blank timestamps near the end
    def sort_key(r):
        return r["timestamp"] if r["timestamp"] else "9999"

    rows.sort(key=sort_key)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write("reference,amount,status,timestamp\n")
        for r in rows:
            # Quote amount if it contains comma
            amt_str = f'"{r["amount"]}"' if ',' in r["amount"] else r["amount"]
            f.write(f'{r["reference"]},{amt_str},{r["status"]},{r["timestamp"]}\n')

    return str(output_path)

