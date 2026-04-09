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
                "  extras,has_flex,status,source,notes)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending_payment',%s,%s)"
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
            cur.execute(sql, (
                ref,
                data["customer_name"], data["customer_phone"],
                data.get("customer_email"), bday,
                data["booking_date"], data["booking_time"], data["num_people"],
                data["price_per_person"], data["subtotal"],
                data.get("extras_total", 0), data.get("flex_amount", 0), data["total_price"],
                json.dumps(data.get("extras", [])), data.get("has_flex", False),
                data.get("source", "web"), data.get("notes")
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
                "       paid_at,source,notes,created_at,confirmation_email_sent_at"
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
                    "paid_at","source","notes","created_at","confirmation_email_sent_at"]
            result = dict(zip(cols, row))
            for k in ("booking_date","booking_time","paid_at","created_at", "confirmation_email_sent_at"):
                if result.get(k):
                    result[k] = str(result[k])
            return result


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
    that have a customer email and haven't received the followup email yet."""
    from datetime import date, timedelta
    target_date = date.today() - timedelta(days=days_after)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, booking_ref, customer_name, customer_phone, customer_email, "
                "       booking_date, booking_time, num_people, subtotal, extras_total, "
                "       total_price, has_flex, flex_amount, extras, notes "
                "FROM hotboat_appointments "
                "WHERE booking_date = %s "
                "  AND status = 'confirmed' "
                "  AND customer_email IS NOT NULL "
                "  AND customer_email <> '' "
                "  AND followup_email_sent_at IS NULL",
                (target_date,),
            )
            cols = [
                "id", "booking_ref", "customer_name", "customer_phone", "customer_email",
                "booking_date", "booking_time", "num_people", "subtotal", "extras_total",
                "total_price", "has_flex", "flex_amount", "extras", "notes",
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
    """Set followup_email_sent_at once (idempotent)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hotboat_appointments SET followup_email_sent_at=NOW(), updated_at=NOW() "
                "WHERE booking_ref=%s AND followup_email_sent_at IS NULL",
                (booking_ref,),
            )
            conn.commit()
            return cur.rowcount > 0


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
                       ha.num_people, ha.total_price, ha.subtotal, ha.extras_total
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
                    "num_people", "total_price", "subtotal", "extras_total"]
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
