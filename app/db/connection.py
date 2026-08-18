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


# Namespace for the per-phone advisory lock below — deliberately a different
# value/call-signature (two int32 keys instead of one bigint) from
# _SCHEDULER_LOCK_KEY above, so the two lock families can never collide.
_PHONE_LOCK_NAMESPACE = 725019283


def acquire_phone_advisory_lock(phone_number: str, timeout_seconds: int = 10):
    """Cross-replica mutual exclusion for processing one phone number's
    WhatsApp message. app/bot/conversation.py's per-phone asyncio.Lock only
    protects concurrency *within one replica's process memory* — with
    railway.toml's numReplicas=4, two near-simultaneous messages from the
    same customer can land on two different replicas, each with its own
    empty in-memory conversation cache. Both then read the shared
    bot_conversation_state row before either has written its own update, so
    both see empty history and both send the "first message" welcome menu
    instead of only one of them progressing the conversation (confirmed via
    a real conversation on 2026-08-18: 5 messages in 14s all got the
    identical first-message reply).

    BLOCKS (bounded by timeout_seconds via lock_timeout) until any other
    replica currently holding this phone's lock releases it, so the second
    replica genuinely waits and then re-reads the now-current state instead
    of racing it. Uses a dedicated, non-pooled connection — advisory locks
    are session-scoped, so returning this connection to the shared pool
    afterward would leak the lock onto whoever borrows it next. Returns the
    connection to pass to release_phone_advisory_lock, or None if the lock
    could not be acquired within the timeout (caller should proceed anyway
    rather than block the message indefinitely — this is a best-effort
    safety net, not a hard requirement for correctness).
    """
    conn = psycopg.connect(settings.database_url, autocommit=True)
    try:
        with conn.cursor() as cur:
            # SET does not accept a bind parameter for the value — timeout_seconds
            # is always an int from our own call sites (never user input), so
            # inlining it here is safe.
            cur.execute(f"SET lock_timeout = '{int(timeout_seconds)}s'")
            cur.execute(
                "SELECT pg_advisory_lock(%s, hashtext(%s))",
                (_PHONE_LOCK_NAMESPACE, phone_number),
            )
        return conn
    except Exception as e:
        logger.warning(f"Could not acquire phone advisory lock for {phone_number}: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def release_phone_advisory_lock(conn, phone_number: str) -> None:
    """Release a lock acquired by acquire_phone_advisory_lock and close its
    dedicated connection. Safe to call with conn=None (lock was never
    acquired)."""
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_unlock(%s, hashtext(%s))",
                (_PHONE_LOCK_NAMESPACE, phone_number),
            )
    except Exception as e:
        logger.warning(f"Error releasing phone advisory lock for {phone_number}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass








