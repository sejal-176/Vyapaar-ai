"""Generate synthetic growth demo dataset (growth_demo.db).
Safe to re-run: deletes and recreates growth_demo.db.
Fixed random seed (42).
60 days of history ending yesterday (IST).
"""
import os
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "growth_demo.db"

# Fixed seed for reproducibility
RANDOM_SEED = 42


def get_dates():
    # Fixed base date for consistent demonstration if needed, or today's date
    # In vyapaar-ai, system date is around 2026-10-31, so yesterday is 2026-10-30
    today = date(2026, 10, 31)
    yesterday = today - timedelta(days=1)
    start_date = yesterday - timedelta(days=59)  # 60 days total: day 0 to 59
    return start_date, yesterday


def make_growth_demo():
    random.seed(RANDOM_SEED)

    if DB_PATH.exists():
        try:
            os.remove(DB_PATH)
        except Exception as e:
            print(f"Warning: could not remove existing {DB_PATH}: {e}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Create tables per PLAN
    cur.executescript("""
    CREATE TABLE gd_customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payer_token TEXT NOT NULL UNIQUE,
        consent_status TEXT NOT NULL
    );

    CREATE TABLE gd_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        unit TEXT NOT NULL,
        price_paise INTEGER NOT NULL,
        cost_price_paise INTEGER,
        stock_on_hand INTEGER NOT NULL,
        stock_updated_on TEXT NOT NULL
    );

    CREATE TABLE gd_invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        invoice_date TEXT NOT NULL,
        total_paise INTEGER NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES gd_customers(id)
    );

    CREATE TABLE gd_invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price_paise INTEGER NOT NULL,
        FOREIGN KEY (invoice_id) REFERENCES gd_invoices(id),
        FOREIGN KEY (product_id) REFERENCES gd_products(id)
    );

    CREATE TABLE gd_outreach (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        language TEXT NOT NULL,
        offer_type TEXT NOT NULL,
        offer_pct INTEGER NOT NULL DEFAULT 0,
        message_text TEXT NOT NULL,
        evidence_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        approved_at TEXT,
        marked_sent_at TEXT,
        FOREIGN KEY (customer_id) REFERENCES gd_customers(id)
    );

    CREATE INDEX idx_invoices_customer ON gd_invoices(customer_id);
    CREATE INDEX idx_invoices_date ON gd_invoices(invoice_date);
    CREATE INDEX idx_items_invoice ON gd_invoice_items(invoice_id);
    CREATE INDEX idx_items_product ON gd_invoice_items(product_id);
    CREATE INDEX idx_outreach_customer ON gd_outreach(customer_id);
    """)

    start_date, end_date = get_dates()
    dates_list = [start_date + timedelta(days=i) for i in range(60)]
    ref_date_str = end_date.isoformat()

    # 1. Insert Products
    # Products (rupees): Tea 10, Coffee 15, Biscuit 10, Samosa 15, Bun maska 25
    # Costs: Tea 4, Coffee 7, Biscuit 7, Samosa 8, Bun maska NULL
    # Initial stock placeholders; Biscuit and Samosa stock tuned after generation
    products = [
        {"name": "Tea", "unit": "cup", "price": 1000, "cost": 400, "stock": 150},
        {"name": "Coffee", "unit": "cup", "price": 1500, "cost": 700, "stock": 80},
        {"name": "Biscuit", "unit": "pack", "price": 1000, "cost": 700, "stock": 25},  # ~2 days left
        {"name": "Samosa", "unit": "piece", "price": 1500, "cost": 800, "stock": 90},
        {"name": "Bun maska", "unit": "plate", "price": 2500, "cost": None, "stock": 40},
    ]

    for p in products:
        cur.execute(
            """INSERT INTO gd_products (name, unit, price_paise, cost_price_paise, stock_on_hand, stock_updated_on)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (p["name"], p["unit"], p["price"], p["cost"], p["stock"], ref_date_str),
        )
    conn.commit()

    # 2. Customers setup
    # 30 customers:
    # 8 daily regulars: C-0001 .. C-0008
    # 8 weekly: C-0009 .. C-0016
    # 5 occasional: C-0017 .. C-0021
    # 4 drifting: C-0022 .. C-0025 (at least 3 OPTED_IN)
    # 3 shrinking basket: C-0026 .. C-0028
    # 2 new: C-0029 .. C-0030
    archetypes = {}
    consent_map = {}

    # Define archetypes
    for i in range(1, 9):
        archetypes[f"C-{i:04d}"] = "daily_regular"
    for i in range(9, 17):
        archetypes[f"C-{i:04d}"] = "weekly"
    for i in range(17, 22):
        archetypes[f"C-{i:04d}"] = "occasional"
    for i in range(22, 26):
        archetypes[f"C-{i:04d}"] = "drifting"
    for i in range(26, 29):
        archetypes[f"C-{i:04d}"] = "shrinking_basket"
    for i in range(29, 31):
        archetypes[f"C-{i:04d}"] = "new"

    # Consents: about 60% OPTED_IN (18 opted-in, 12 none)
    # Ensure C-0022, C-0023, C-0024 (drifting) are OPTED_IN
    opted_in_tokens = {
        "C-0001", "C-0002", "C-0003", "C-0004", "C-0006",
        "C-0009", "C-0010", "C-0011", "C-0013", "C-0015",
        "C-0017", "C-0018", "C-0020",
        "C-0022", "C-0023", "C-0024",  # 3 opted-in drifting (lapsing)
        "C-0026", "C-0027"             # shrinking basket
    }

    customer_db_ids = {}
    for i in range(1, 31):
        token = f"C-{i:04d}"
        consent = "OPTED_IN" if token in opted_in_tokens else "NONE"
        consent_map[token] = consent
        cur.execute(
            "INSERT INTO gd_customers (payer_token, consent_status) VALUES (?, ?)",
            (token, consent),
        )
        customer_db_ids[token] = cur.lastrowid
    conn.commit()

    # 3. Generate Invoices & Items across 60 days
    # Days 0..45 = earlier period; Days 46..59 = last 14 days
    # Samosa requirement: slow mover (units in last 14 days fall >= 35% vs previous 14 days)
    # Biscuit requirement: stock has ~2 days left at usual velocity
    # Invariant: every invoice total equals sum(quantity * unit_price_paise)

    product_map = {
        "Tea": 1,
        "Coffee": 2,
        "Biscuit": 3,
        "Samosa": 4,
        "Bun maska": 5,
    }
    price_map = {
        1: 1000,
        2: 1500,
        3: 1000,
        4: 1500,
        5: 2500,
    }

    biscuit_units_last28 = []

    for day_idx, current_date in enumerate(dates_list):
        date_str = current_date.isoformat()
        is_last14 = (day_idx >= 46)
        is_prev14 = (32 <= day_idx < 46)

        # Decide which customers visit today
        visiting_customers = []
        for token, arch in archetypes.items():
            cid = customer_db_ids[token]
            if arch == "daily_regular":
                if random.random() < 0.85:
                    visiting_customers.append((cid, arch, token))
            elif arch == "weekly":
                if random.random() < 0.25:
                    visiting_customers.append((cid, arch, token))
            elif arch == "occasional":
                if random.random() < 0.09:
                    visiting_customers.append((cid, arch, token))
            elif arch == "drifting":
                # Drifting visits regularly until day 49 (last 10 days no visits)
                if day_idx < 50:
                    if random.random() < 0.65:
                        visiting_customers.append((cid, arch, token))
            elif arch == "shrinking_basket":
                # Still visits in last 14 days
                if random.random() < 0.60:
                    visiting_customers.append((cid, arch, token))
            elif arch == "new":
                # Only visits in last 10 days
                if day_idx >= 50:
                    if random.random() < 0.50:
                        visiting_customers.append((cid, arch, token))

        # Add walk-ins (about 30% of total invoices)
        # If we have N customer visits, we add roughly N * 0.43 walk-ins so walk-ins / total ~ 30%
        num_walkins = int(len(visiting_customers) * 0.43) + random.randint(1, 3)
        all_visits = [(cid, arch, token) for cid, arch, token in visiting_customers]
        for _ in range(num_walkins):
            all_visits.append((None, "walk_in", "WALK_IN"))

        daily_biscuit_count = 0

        for cid, arch, token in all_visits:
            # Basket selection
            items = []
            if arch == "shrinking_basket" and is_last14:
                # Basket shrinks by ~60% (e.g. 1 tea instead of 3 teas and bun maska)
                items.append((product_map["Tea"], 1, price_map[product_map["Tea"]]))
            elif arch == "shrinking_basket" and not is_last14:
                items.append((product_map["Tea"], 3, price_map[product_map["Tea"]]))
                if random.random() < 0.5:
                    items.append((product_map["Biscuit"], 1, price_map[product_map["Biscuit"]]))
                else:
                    items.append((product_map["Bun maska"], 1, price_map[product_map["Bun maska"]]))
            else:
                # Standard baskets
                # Tea is most common
                tea_qty = random.choices([1, 2, 3], weights=[0.4, 0.4, 0.2])[0]
                items.append((product_map["Tea"], tea_qty, price_map[product_map["Tea"]]))

                # Samosa: frequent in earlier & prev14, rare in last14 to ensure slow mover drop
                if is_last14:
                    if random.random() < 0.08:
                        items.append((product_map["Samosa"], 1, price_map[product_map["Samosa"]]))
                elif is_prev14:
                    if random.random() < 0.45:
                        items.append((product_map["Samosa"], random.choice([1, 2]), price_map[product_map["Samosa"]]))
                else:
                    if random.random() < 0.35:
                        items.append((product_map["Samosa"], random.choice([1, 2]), price_map[product_map["Samosa"]]))

                # Biscuit: steady sales across all days
                if random.random() < 0.35:
                    b_qty = random.choice([1, 2])
                    items.append((product_map["Biscuit"], b_qty, price_map[product_map["Biscuit"]]))

                # Coffee & Bun maska
                if random.random() < 0.20:
                    items.append((product_map["Coffee"], 1, price_map[product_map["Coffee"]]))
                if random.random() < 0.15:
                    items.append((product_map["Bun maska"], 1, price_map[product_map["Bun maska"]]))

            # Invariant: total = sum(qty * price)
            total_paise = sum(qty * price for pid, qty, price in items)
            cur.execute(
                "INSERT INTO gd_invoices (customer_id, invoice_date, total_paise) VALUES (?, ?, ?)",
                (cid, date_str, total_paise),
            )
            inv_id = cur.lastrowid

            for pid, qty, price in items:
                cur.execute(
                    "INSERT INTO gd_invoice_items (invoice_id, product_id, quantity, unit_price_paise) VALUES (?, ?, ?, ?)",
                    (inv_id, pid, qty, price),
                )
                if pid == product_map["Biscuit"]:
                    daily_biscuit_count += qty

        if day_idx >= (60 - 28):
            if daily_biscuit_count > 0:
                biscuit_units_last28.append(daily_biscuit_count)

    conn.commit()

    # 4. Tune Biscuit stock for "about 2 days left at usual pace"
    # Velocity = median units per selling day over last 28 days
    if biscuit_units_last28:
        sorted_b = sorted(biscuit_units_last28)
        mid = len(sorted_b) // 2
        median_b = sorted_b[mid] if len(sorted_b) % 2 == 1 else (sorted_b[mid - 1] + sorted_b[mid]) / 2.0
    else:
        median_b = 8.0

    # 2 days left means stock = round(median_b * 2) - 1 or 2 so days_left < 3 (DAYS_LEFT_WARN)
    biscuit_stock = max(1, int(median_b * 2.0))
    cur.execute(
        "UPDATE gd_products SET stock_on_hand = ? WHERE name = 'Biscuit'",
        (biscuit_stock,),
    )
    conn.commit()

    # 5. Print Summary Counts
    cur.execute("SELECT COUNT(*) FROM gd_customers")
    total_cust = cur.fetchone()[0]
    cur.execute("SELECT consent_status, COUNT(*) FROM gd_customers GROUP BY consent_status")
    consent_counts = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM gd_invoices")
    total_inv = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM gd_invoices WHERE customer_id IS NULL")
    walkin_inv = cur.fetchone()[0]

    # Archetype breakdown
    arch_counts = {}
    for arch in archetypes.values():
        arch_counts[arch] = arch_counts.get(arch, 0) + 1

    print("==================================================")
    print("Growth Demo Database Created (growth_demo.db)")
    print("==================================================")
    print(f"Total customers: {total_cust}")
    print(f"Consent counts: {consent_counts}")
    print(f"Customer archetypes: {arch_counts}")
    print(f"Total invoices: {total_inv}")
    print(f"Walk-in invoices: {walkin_inv} ({walkin_inv * 100 // total_inv}%)")
    print(f"Biscuit median velocity: {median_b:.1f} units/day, stock set to: {biscuit_stock}")
    print("==================================================")

    conn.close()


if __name__ == "__main__":
    make_growth_demo()

