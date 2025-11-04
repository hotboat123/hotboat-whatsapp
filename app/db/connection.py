"""
Database connection management
"""
import psycopg
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Connection pool
_pool: ConnectionPool = None


def get_pool() -> ConnectionPool:
    """Get or create connection pool"""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=2,
            max_size=10,
            timeout=30
        )
        logger.info("✅ Database connection pool created")
    return _pool


@contextmanager
def get_connection():
    """Get database connection from pool"""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn




