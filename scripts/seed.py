"""Database seed script for VyapaarAI.
Recreates all tables, inserts demo merchants, generates synthetic CSVs,
ingests transactions into the database, and prints validation reports.
"""
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles to prevent encoding crashes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db import Base, engine, SessionLocal
from backend.models import Merchant
from backend.data.generator import generate_merchant_csv
from backend.data.ingest import ingest_csv


def seed_database():
    print("Recreating database tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Insert demo merchants
        print("Inserting demo merchants...")
        m1 = Merchant(
            id=1,
            name="Sharma Tea Stall",
            business_type="tea stall",
            vpa="sharmatea@demo",
        )
        m2 = Merchant(
            id=2,
            name="Gupta Kirana Store",
            business_type="kirana",
            vpa="guptakirana@demo",
        )
        db.add(m1)
        db.add(m2)
        db.commit()

        # Data directory
        data_dir = PROJECT_ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        csv_path_m1 = data_dir / "merchant_1.csv"
        csv_path_m2 = data_dir / "merchant_2.csv"

        print("Generating synthetic 30-day CSVs...")
        generate_merchant_csv(merchant_id=1, output_path=csv_path_m1, seed=42)
        generate_merchant_csv(merchant_id=2, output_path=csv_path_m2, seed=42)

        print(f"Ingesting Merchant 1 ({m1.name})...")
        report_1 = ingest_csv(csv_path_m1, merchant_id=1, db=db)

        print(f"Ingesting Merchant 2 ({m2.name})...")
        report_2 = ingest_csv(csv_path_m2, merchant_id=2, db=db)

        print("\n" + "=" * 50)
        print("VALIDATION REPORT - SHARMA TEA STALL (Merchant 1)")
        print("=" * 50)
        print(f"Accepted: {report_1['accepted']}")
        print(f"Rejected: {report_1['rejected']}")
        print("Rejection reasons:")
        for reason, count in report_1["reasons"].items():
            print(f"  - {reason}: {count}")

        print("\n" + "=" * 50)
        print("VALIDATION REPORT - GUPTA KIRANA STORE (Merchant 2)")
        print("=" * 50)
        print(f"Accepted: {report_2['accepted']}")
        print(f"Rejected: {report_2['rejected']}")
        print("Rejection reasons:")
        for reason, count in report_2["reasons"].items():
            print(f"  - {reason}: {count}")
        print("=" * 50)
        print("Database seed complete.")

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
