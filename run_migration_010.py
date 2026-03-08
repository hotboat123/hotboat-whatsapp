import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.connection import get_connection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run the push_tokens table migration"""
    try:
        migration_file = Path(__file__).parent / "migrations" / "010_add_push_tokens.sql"
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                logger.info("Running migration 010_add_push_tokens.sql...")
                cur.execute(migration_sql)
                conn.commit()
                logger.info("✅ Migration completed successfully!")
                
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
