"""Run migration 011: Add pg_trgm indexes for message search (ILIKE)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.connection import get_connection


def run_migration():
    migration_file = Path(__file__).parent / "migrations" / "011_add_message_search_index.sql"
    if not migration_file.exists():
        print(f"Migration file not found: {migration_file}")
        sys.exit(1)

    with open(migration_file, "r", encoding="utf-8") as f:
        migration_sql = f.read()

    print("Running migration 011: Add message search indexes (pg_trgm)...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(migration_sql)
                conn.commit()
        print("Migration 011 completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")
        print("   If pg_trgm is not available, search will still work but may be slower.")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
