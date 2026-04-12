"""Database operations for hotboat_appointments"""
import logging, json, random, string
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from app.db.connection import get_connection

CHILE_TZ = ZoneInfo("America/Santiago")
logger = logging.getLogger(__name__)
PRICES = {2: 69990, 3: 54990, 4: 44990, 5: 38990, 6: 32990, 7: 29990}


def load_prices_from_db() -> None:
    """Load prices per person from hotboat_settings into the live PRICES dict."""
    import json as _json
    try:
        from app.booking.operator_settings import get_setting
        raw = get_setting("prices_per_person", "")
        if raw:
            stored = _json.loads(raw)
            PRICES.update({int(k): int(v) for k, v in stored.items()})
    except Exception as e:
        logger.warning(f"load_prices_from_db: {e}")


def generate_booking_ref() -> str:
    year = datetime.now(CHILE_TZ).year
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"HB-{year}-{suffix}"


def create_booking(data: dict) -> dict:
    ref = generate_booking_ref()
    with get_connection() as conn:
        with conn.cursor() as cur:
            sql = (
                "INSERT INTO hotboat_appointments"
                " (booking_ref,customer_name,customer_phone,customer_email,customer_birthday,"
                "  booking_date,booking_time,num_people,"
                "  price_per_person,subtotal,extras_total,flex_amount,total_price,"
                "  extras,has_flex,status,source,notes,customer_language)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending_payment',%s,%s,%s)"
                " RETURNING id,booking_ref,status"
            )
            bday_raw = data.get("customer_birthday") or None
            bday = None
            if bday_raw:
                try:
                    from datetime import date as _date
                    bday = _date.fromisoformat(str(bday_raw))
                except ValueError:
                    pass
            lang = str(data.get("customer_language") or "es").strip().lower()[:5]
            if lang not in ("es", "en", "pt"):
                lang = "es"
            cur.execute(sql, (
                ref,
                data["customer_name"], data["customer_phone"],
                data.get("customer_email"), bday,
                data["booking_date"], data["booking_time"], data["num_people"],
                data["price_per_person"], data["subtotal"],
                data.get("extras_total", 0), data.get("flex_amount", 0), data["total_price"],
                json.dumps(data.get("extras", [])), data.get("has_flex", False),
                data.get("source", "web"), data.get("notes"), lang
            ))
            row = cur.fetchone()
            conn.commit()
            return {"id": row[0], "booking_ref": row[1], "status": row[2]}


def update_booking_payment(booking_ref: str, payment_id: str, payment_order_id: str, payment_status: str) -> bool:
    new_status = "confirmed" if payment_status == "approved" else "pending_payment"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hotboat_appointments"
                " SET payment_id=%s, payment_order_id=%s, payment_status=%s, status=%s,"
                "     paid_at=CASE WHEN %s='approved' THEN NOW() ELSE paid_at END"
                " WHERE booking_ref=%s",
                (payment_id, payment_order_id, payment_status, new_status, payment_status, booking_ref)
            )
            conn.commit()
            return cur.rowcount > 0


def get_booking_by_ref(booking_ref: str) -> Optional[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,booking_ref,customer_name,customer_phone,customer_email,"
                "       booking_date,booking_time,num_people,price_per_person,"
                "       subtotal,extras_total,flex_amount,total_price,"
                "       extras,has_flex,status,payment_id,payment_status,"
                "       paid_at,source,notes,created_at,confirmation_email_sent_at,"
                "       COALESCE(customer_language,'es')"
                " FROM hotboat_appointments WHERE booking_ref=%s",
                (booking_ref,)
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = ["id","booking_ref","customer_name","customer_phone","customer_email",
                    "booking_date","booking_time","num_people","price_per_person",
                    "subtotal","extras_total","flex_amount","total_price",
                    "extras","has_flex","status","payment_id","payment_status",
                    "paid_at","source","notes","created_at","confirmation_email_sent_at",
                    "customer_language"]
            result = dict(zip(cols, row))
            for k in ("booking_date","booking_time","paid_at","created_at", "confirmation_email_sent_at"):
                if result.get(k):
                    result[k] = str(result[k])
            return result


def get_bookings_pending_payment_email(delay_minutes: int = 5) -> list:
    """Return bookings that are still pending payment after delay_minutes
    and haven't had the booking_created reminder email sent yet.
    Ensures the column exists defensively.
    """
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=delay_minutes)
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Defensive: add column if missing (covers old deployments)
            cur.execute("""
                ALTER TABLE hotboat_appointments
                    ADD COLUMN IF NOT EXISTS pending_email_sent_at TIMESTAMPTZ
            """)
            conn.commit()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, booking_ref, customer_name, customer_phone, customer_email, "
                "       booking_date, booking_time, num_people, subtotal, extras_total, "
                "       total_price "
                "FROM hotboat_appointments "
                "WHERE status = 'pending_payment' "
                "  AND customer_email IS NOT NULL AND customer_email <> '' "
                "  AND pending_email_sent_at IS NULL "
                "  AND created_at <= %s",
                (cutoff,),
            )
            cols = ["id", "booking_ref", "customer_name", "customer_phone", "customer_email",
                    "booking_date", "booking_time", "num_people", "subtotal", "extras_total",
                    "total_price"]
            rows = []
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                for k in ("booking_date", "booking_time"):
                    if d.get(k):
                        d[k] = str(d[k])
                rows.append(d)
            return rows


def mark_pending_email_sent(booking_ref: str) -> bool:
    """Mark the pending-payment reminder email as sent (idempotent)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hotboat_appointments SET pending_email_sent_at=NOW(), updated_at=NOW() "
                "WHERE booking_ref=%s AND pending_email_sent_at IS NULL",
                (booking_ref,),
            )
            conn.commit()
            return cur.rowcount > 0


def mark_confirmation_email_sent(booking_ref: str) -> bool:
    """Set confirmation_email_sent_at once (returns True if row updated)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hotboat_appointments SET confirmation_email_sent_at=NOW(), updated_at=NOW() "
                "WHERE booking_ref=%s AND confirmation_email_sent_at IS NULL",
                (booking_ref,),
            )
            conn.commit()
            return cur.rowcount > 0


def get_bookings_for_followup(days_after: int) -> list:
    """Return confirmed bookings whose booking_date = today - days_after
    that have a customer email and haven't received the followup email yet.
    Includes both hotboat_appointments (public) and all_appointments (manual).
    Manual rows use synthetic booking_ref = 'MANUAL-<id>'.
    """
    from datetime import date, timedelta
    target_date = date.today() - timedelta(days=days_after)

    # Ensure all_appointments has the followup column (safe guard for old DBs)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS followup_email_sent_at TIMESTAMPTZ
            """)
            conn.commit()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, booking_ref, customer_name, customer_phone, customer_email,
                       booking_date, booking_time, num_people, subtotal, extras_total,
                       total_price, has_flex, flex_amount, extras, notes,
                       COALESCE(customer_language, 'es') AS customer_language
                FROM hotboat_appointments
                WHERE booking_date = %s
                  AND status = 'confirmed'
                  AND customer_email IS NOT NULL AND customer_email <> ''
                  AND followup_email_sent_at IS NULL

                UNION ALL

                SELECT id,
                       'MANUAL-' || id::text          AS booking_ref,
                       nombre_cliente                  AS customer_name,
                       telefono                        AS customer_phone,
                       email                           AS customer_email,
                       fecha                           AS booking_date,
                       hora                            AS booking_time,
                       num_personas                    AS num_people,
                       ingreso_total                   AS subtotal,
                       COALESCE(ingreso_extras, 0)     AS extras_total,
                       ingreso_total                   AS total_price,
                       FALSE                           AS has_flex,
                       0                               AS flex_amount,
                       NULL                            AS extras,
                       observaciones                   AS notes,
                       'es'                            AS customer_language
                FROM all_appointments
                WHERE fecha = %s
                  AND status = 'confirmed'
                  AND email IS NOT NULL AND email <> ''
                  AND followup_email_sent_at IS NULL
            """, (target_date, target_date))
            cols = [
                "id", "booking_ref", "customer_name", "customer_phone", "customer_email",
                "booking_date", "booking_time", "num_people", "subtotal", "extras_total",
                "total_price", "has_flex", "flex_amount", "extras", "notes", "customer_language",
            ]
            rows = []
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                for k in ("booking_date", "booking_time"):
                    if d.get(k):
                        d[k] = str(d[k])
                rows.append(d)
            return rows


def mark_followup_email_sent(booking_ref: str) -> bool:
    """Set followup_email_sent_at once (idempotent).
    Handles both hotboat_appointments (real ref) and all_appointments (MANUAL-<id>).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            if booking_ref.startswith("MANUAL-"):
                row_id = int(booking_ref.split("-", 1)[1])
                cur.execute(
                    "UPDATE all_appointments SET followup_email_sent_at=NOW(), updated_at=NOW() "
                    "WHERE id=%s AND followup_email_sent_at IS NULL",
                    (row_id,),
                )
            else:
                cur.execute(
                    "UPDATE hotboat_appointments SET followup_email_sent_at=NOW(), updated_at=NOW() "
                    "WHERE booking_ref=%s AND followup_email_sent_at IS NULL",
                    (booking_ref,),
                )
            conn.commit()
            return cur.rowcount > 0


# ── Pre-booking 1-hour notification ──────────────────────────────────────────

def get_bookings_starting_soon(window_minutes: int = 20, target_minutes_ahead: int = 60) -> list:
    """
    Return bookings whose start time is between
    (now + target_minutes_ahead - window_minutes/2) and
    (now + target_minutes_ahead + window_minutes/2)
    that haven't had a pre-booking notification sent yet.
    Checks both hotboat_appointments and all_appointments.
    window_minutes=20 with a 10-min scheduler gives safe overlap without duplicates.
    """
    from datetime import timezone
    # Ensure the column exists on all_appointments too (safe guard)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS pre_booking_notif_sent_at TIMESTAMPTZ
            """)
            conn.commit()

    half = window_minutes // 2
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, booking_ref, customer_name, customer_phone, customer_email,
                       booking_date, booking_time, num_people, total_price, status,
                       'hotboat_web' AS source, COALESCE(customer_language,'es') AS customer_language,
                       COALESCE(extras::text, '[]') AS extras,
                       COALESCE(extras_total, 0) AS extras_total,
                       notes
                FROM hotboat_appointments
                WHERE (booking_date + booking_time) AT TIME ZONE 'America/Santiago'
                      BETWEEN (NOW() AT TIME ZONE 'America/Santiago' + INTERVAL '{target_minutes_ahead - half} minutes')
                          AND (NOW() AT TIME ZONE 'America/Santiago' + INTERVAL '{target_minutes_ahead + half} minutes')
                  AND status IN ('confirmed','pending_payment')
                  AND pre_booking_notif_sent_at IS NULL

                UNION ALL

                SELECT id,
                       'MANUAL-' || id::text          AS booking_ref,
                       nombre_cliente                  AS customer_name,
                       telefono                        AS customer_phone,
                       email                           AS customer_email,
                       fecha                           AS booking_date,
                       hora                            AS booking_time,
                       num_personas                    AS num_people,
                       ingreso_total                   AS total_price,
                       status,
                       fuente                          AS source,
                       'es'                            AS customer_language,
                       '[]'                            AS extras,
                       COALESCE(ingreso_extras, 0)     AS extras_total,
                       observaciones                   AS notes
                FROM all_appointments
                WHERE (fecha + hora) AT TIME ZONE 'America/Santiago'
                      BETWEEN (NOW() AT TIME ZONE 'America/Santiago' + INTERVAL '{target_minutes_ahead - half} minutes')
                          AND (NOW() AT TIME ZONE 'America/Santiago' + INTERVAL '{target_minutes_ahead + half} minutes')
                  AND status IN ('confirmed','pending_payment')
                  AND pre_booking_notif_sent_at IS NULL
            """)
            cols = ["id", "booking_ref", "customer_name", "customer_phone", "customer_email",
                    "booking_date", "booking_time", "num_people", "total_price", "status",
                    "source", "customer_language", "extras", "extras_total", "notes"]
            rows = []
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                for k in ("booking_date", "booking_time"):
                    if d.get(k):
                        d[k] = str(d[k])
                rows.append(d)
            return rows


def mark_pre_booking_notif_sent(booking_ref: str) -> bool:
    """Set pre_booking_notif_sent_at once (idempotent)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            if booking_ref.startswith("MANUAL-"):
                row_id = int(booking_ref.split("-", 1)[1])
                cur.execute(
                    "UPDATE all_appointments SET pre_booking_notif_sent_at=NOW() "
                    "WHERE id=%s AND pre_booking_notif_sent_at IS NULL",
                    (row_id,),
                )
            else:
                cur.execute(
                    "UPDATE hotboat_appointments SET pre_booking_notif_sent_at=NOW() "
                    "WHERE booking_ref=%s AND pre_booking_notif_sent_at IS NULL",
                    (booking_ref,),
                )
            conn.commit()
            return cur.rowcount > 0


def count_previous_bookings(customer_email: str = "", customer_phone: str = "",
                             exclude_ref: str = "") -> int:
    """
    Return the number of *previous confirmed* bookings for this customer
    (matched by email OR phone, excluding the current booking_ref).
    Checks both hotboat_appointments and all_appointments.
    """
    if not customer_email and not customer_phone:
        return 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            parts, params = [], []
            if customer_email:
                parts.append("customer_email = %s")
                params.append(customer_email.strip().lower())
            if customer_phone:
                parts.append("customer_phone = %s")
                params.append(customer_phone.strip())
            match_clause = " OR ".join(parts)
            excl_ha = f"AND booking_ref != %s" if exclude_ref else ""
            excl_aa = f"AND 'MANUAL-' || id::text != %s" if exclude_ref else ""
            p_ha = params + ([exclude_ref] if exclude_ref else [])
            p_aa = params + ([exclude_ref] if exclude_ref else [])

            cur.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT id FROM hotboat_appointments
                    WHERE ({match_clause}) AND status = 'confirmed' {excl_ha}
                    UNION ALL
                    SELECT id FROM all_appointments
                    WHERE (
                        ({' OR '.join(
                            ['email = %s'] * (1 if customer_email else 0) +
                            ['telefono = %s'] * (1 if customer_phone else 0)
                        )})
                    ) AND status = 'confirmed' {excl_aa}
                ) t
            """, p_ha + p_aa)
            row = cur.fetchone()
            return int(row[0]) if row else 0


# ── Birthday sweep ────────────────────────────────────────────────────────────

def get_customers_for_birthday_email() -> list:
    """
    Return one record per customer whose birthday is today and who hasn't
    received a birthday email this calendar year yet.
    Uses DISTINCT ON (customer_email) to avoid duplicate sends for multi-booking customers.
    """
    from datetime import date
    today = date.today()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (ha.customer_email)
                       ha.customer_email, ha.customer_name, ha.customer_phone,
                       ha.booking_ref, ha.booking_date, ha.booking_time,
                       ha.num_people, ha.total_price, ha.subtotal, ha.extras_total,
                       COALESCE(ha.customer_language, 'es') AS customer_language
                FROM hotboat_appointments ha
                WHERE ha.customer_birthday IS NOT NULL
                  AND ha.customer_email IS NOT NULL
                  AND ha.customer_email <> ''
                  AND EXTRACT(MONTH FROM ha.customer_birthday) = %s
                  AND EXTRACT(DAY   FROM ha.customer_birthday) = %s
                  AND ha.customer_email NOT IN (
                      SELECT customer_email FROM birthday_emails_sent
                      WHERE sent_year = %s
                  )
                ORDER BY ha.customer_email, ha.created_at DESC
                """,
                (today.month, today.day, today.year),
            )
            cols = ["customer_email", "customer_name", "customer_phone",
                    "booking_ref", "booking_date", "booking_time",
                    "num_people", "total_price", "subtotal", "extras_total",
                    "customer_language"]
            rows = []
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                for k in ("booking_date", "booking_time"):
                    if d.get(k):
                        d[k] = str(d[k])
                rows.append(d)
            return rows


def mark_birthday_email_sent(customer_email: str) -> bool:
    """Record that birthday email was sent this year (idempotent)."""
    from datetime import date
    year = date.today().year
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO birthday_emails_sent (customer_email, sent_year) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (customer_email, year),
            )
            conn.commit()
            return cur.rowcount > 0


def ensure_db_columns() -> None:
    """Apply any missing columns (idempotent). Run once at startup."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                -- 019: customer language on web bookings
                ALTER TABLE hotboat_appointments
                    ADD COLUMN IF NOT EXISTS customer_language VARCHAR(5) DEFAULT 'es';

                -- 020: pre-booking notification tracker (web bookings)
                ALTER TABLE hotboat_appointments
                    ADD COLUMN IF NOT EXISTS pre_booking_notif_sent_at TIMESTAMPTZ;

                -- 020b: pre-booking notification tracker (manual/all_appointments)
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS pre_booking_notif_sent_at TIMESTAMPTZ;

                -- 021: multiple images per alojamiento
                ALTER TABLE alojamientos
                    ADD COLUMN IF NOT EXISTS extra_images JSONB DEFAULT '[]';
            """)
            conn.commit()


def ensure_signatures_table() -> None:
    """Create hotboat_signatures table if it doesn't exist yet (idempotent)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hotboat_signatures (
                    id               SERIAL PRIMARY KEY,
                    booking_ref      VARCHAR(50)  NOT NULL,
                    passenger_name   VARCHAR(255) NOT NULL,
                    passenger_email  VARCHAR(255),
                    passenger_phone  VARCHAR(50),
                    passenger_birthday DATE,
                    accepted_tc      BOOLEAN      DEFAULT TRUE,
                    ip_address       VARCHAR(50),
                    created_at       TIMESTAMPTZ  DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_signatures_booking_ref ON hotboat_signatures(booking_ref);
                CREATE INDEX IF NOT EXISTS idx_signatures_email       ON hotboat_signatures(passenger_email);
            """)
            conn.commit()


def create_signature(booking_ref: str, data: dict, ip: str = "") -> dict:
    """Save a passenger T&C signature. Returns the created row as dict."""
    from datetime import date as _date
    bday_raw = data.get("passenger_birthday") or None
    bday = None
    if bday_raw:
        try:
            bday = _date.fromisoformat(str(bday_raw))
        except Exception:
            pass
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO hotboat_signatures
                   (booking_ref, passenger_name, passenger_email, passenger_phone,
                    passenger_birthday, accepted_tc, ip_address)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, booking_ref, passenger_name, passenger_email,
                             passenger_phone, passenger_birthday, accepted_tc, created_at""",
                (
                    booking_ref,
                    (data.get("passenger_name") or "").strip(),
                    (data.get("passenger_email") or "").strip().lower() or None,
                    (data.get("passenger_phone") or "").strip() or None,
                    bday,
                    bool(data.get("accepted_tc", True)),
                    ip or None,
                ),
            )
            conn.commit()
            row = cur.fetchone()
            cols = ["id", "booking_ref", "passenger_name", "passenger_email",
                    "passenger_phone", "passenger_birthday", "accepted_tc", "created_at"]
            d = dict(zip(cols, row))
            for k in ("passenger_birthday", "created_at"):
                if d.get(k):
                    d[k] = str(d[k])
            return d


def get_signatures_by_booking_ref(booking_ref: str) -> list:
    """Return all T&C signatures for a booking, newest first."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, booking_ref, passenger_name, passenger_email,
                          passenger_phone, passenger_birthday, accepted_tc, created_at
                   FROM hotboat_signatures
                   WHERE booking_ref = %s
                   ORDER BY created_at ASC""",
                (booking_ref,),
            )
            cols = ["id", "booking_ref", "passenger_name", "passenger_email",
                    "passenger_phone", "passenger_birthday", "accepted_tc", "created_at"]
            rows = []
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                for k in ("passenger_birthday", "created_at"):
                    if d.get(k):
                        d[k] = str(d[k])
                rows.append(d)
            return rows


def get_bookings_with_signatures_for_date(target_date) -> list:
    """
    Return today's bookings that have at least one signature.
    Used for the daily summary notification.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT DISTINCT ha.booking_ref, ha.customer_name, ha.customer_email,
                          ha.customer_phone, ha.booking_date, ha.booking_time, ha.num_people
                   FROM hotboat_appointments ha
                   JOIN hotboat_signatures hs ON hs.booking_ref = ha.booking_ref
                   WHERE ha.booking_date = %s
                   ORDER BY ha.booking_time""",
                (target_date,),
            )
            cols = ["booking_ref", "customer_name", "customer_email",
                    "customer_phone", "booking_date", "booking_time", "num_people"]
            rows = []
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                for k in ("booking_date", "booking_time"):
                    if d.get(k):
                        d[k] = str(d[k])
                rows.append(d)
            return rows


def get_all_bookings(limit: int = 200) -> List[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,booking_ref,customer_name,customer_phone,"
                "       booking_date,booking_time,num_people,total_price,status,created_at"
                " FROM hotboat_appointments ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            cols = ["id","booking_ref","customer_name","customer_phone",
                    "booking_date","booking_time","num_people","total_price","status","created_at"]
            rows = cur.fetchall()
            result = []
            for r in rows:
                d = dict(zip(cols, r))
                for k in ("booking_date","booking_time","created_at"):
                    if d.get(k):
                        d[k] = str(d[k])
                result.append(d)
            return result
