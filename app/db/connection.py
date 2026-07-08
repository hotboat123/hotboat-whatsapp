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
            timeout=30,
            # Validate a connection (cheap round-trip) before handing it to
            # application code. Without this, a connection that Railway/
            # Postgres silently closed while idle (or a network blip) looks
            # fine sitting in the pool but fails the moment a real query
            # runs on it — surfacing as "SSL SYSCALL error: EOF detected"
            # in whatever request happened to get it. check_connection
            # transparently reconnects instead of handing out a dead one.
            check=ConnectionPool.check_connection,
            # Proactively recycle connections that have been idle too long,
            # instead of waiting for them to go stale and fail.
            max_idle=300,
        )
        logger.info("✅ Database connection pool created")
    return _pool


@contextmanager
def get_connection():
    """Get database connection from pool"""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn








