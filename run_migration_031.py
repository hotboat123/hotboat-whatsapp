"""Run migration 031: coupon_extra_benefit on all_appointments."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.connection import get_connection


def run_migration():
    migration_file = Path(__file__).parent / "migrations" / "031_coupon_extra_benefit.sql"
    if not migration_file.exists():
        print(f"Migration file not found: {migration_file}")
        sys.exit(1)

    with open(migration_file, "r", encoding="utf-8") as f:
        migration_sql = f.read()

    print("Running migration 031: coupon_extra_benefit...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(migration_sql)
                conn.commit()
        print("Migration 031 completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
