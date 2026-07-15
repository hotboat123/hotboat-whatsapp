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


# Arbitrary constant used as the advisory-lock key below. Any unique int64
# works; this one has no special meaning.
_SCHEDULER_LOCK_KEY = 918273645

# Held open for the process lifetime once acquired — advisory locks are
# session-scoped, so releasing/reusing this connection would drop the lock.
_scheduler_lock_conn = None


def try_acquire_scheduler_lock() -> bool:
    """
    Claim the single "runs the background schedulers" slot via a Postgres
    advisory lock. When the app runs with multiple uvicorn workers, each
    worker is a separate process that would otherwise start its own copy of
    the auto-sync/email/notification schedulers, sending every automated
    email and WhatsApp message once per worker. Only the worker that wins
    this lock should start them; the rest just serve requests.
    """
    global _scheduler_lock_conn
    conn = psycopg.connect(settings.database_url, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (_SCHEDULER_LOCK_KEY,))
        acquired = cur.fetchone()[0]
    if acquired:
        _scheduler_lock_conn = conn
        return True
    conn.close()
    return False








