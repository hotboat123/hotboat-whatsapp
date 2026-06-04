"""Run migration 030: urgency_days composite key (per-product temporada alta)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.connection import get_connection


def run_migration():
    migration_file = Path(__file__).parent / "migrations" / "030_urgency_days_scope.sql"
    if not migration_file.exists():
        print(f"Migration file not found: {migration_file}")
        sys.exit(1)

    with open(migration_file, "r", encoding="utf-8") as f:
        migration_sql = f.read()

    print("Running migration 030: urgency_days entity scope...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(migration_sql)
                conn.commit()
        print("Migration 030 completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
