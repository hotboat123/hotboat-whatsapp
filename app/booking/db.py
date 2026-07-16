"""Database operations for bookings.

Single source of truth is ``all_appointments`` (source ``hotboat_web`` +
``source_id`` = HB ref). The legacy ``hotboat_appointments`` table has been
dropped.
"""
import logging, json, random, string
from datetime import datetime, date as date_type, time as time_type
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from app.db.connection import get_connection

CHILE_TZ = ZoneInfo("America/Santiago")
logger = logging.getLogger(__name__)
PRICES = {2: 76990, 3: 59990, 4: 48990, 5: 42990, 6: 36990, 7: 33990}

def _parse_booking_date(val: Any) -> date_type:
    if isinstance(val, date_type):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        return date_type.fromisoformat(val[:10])
    raise ValueError("invalid booking_date")


def _parse_booking_time(val: Any) -> time_type:
    if isinstance(val, time_type):
        return val
    if isinstance(val, str) and len(val) >= 4:
        parts = val.replace(".", ":").split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return time_type(h, min(m, 59), 0)
    return time_type(12, 0, 0)


def _legacy_booking_from_aa(d: Dict[str, Any]) -> Dict[str, Any]:
    """Map an all_appointments row dict to the legacy hotboat-shaped API dict."""
    ref = (d.get("source_id") or "").strip() or f"AA-{d.get('id')}"
    ej = d.get("extras_json")
    if ej is None:
        ej = {}
    elif isinstance(ej, str):
        try:
            ej = json.loads(ej)
        except Exception:
            ej = {}
    if isinstance(ej, dict):
        extras_list = ej.get("extras") or []
    elif isinstance(ej, list):
        extras_list = ej  # web bookings store extras as a plain list
    else:
        extras_list = []
    if not isinstance(extras_list, list):
        extras_list = []
    price_pp = 0
    if isinstance(ej, dict) and ej.get("price_per_person"):
        try:
            price_pp = int(ej["price_per_person"])
        except (TypeError, ValueError):
            price_pp = 0
    if not price_pp and d.get("ingreso_reserva") is not None and d.get("num_personas"):
        try:
            n = int(str(d["num_personas"]).strip())
            if n > 0:
                price_pp = int(float(d["ingreso_reserva"]) / n)
        except (TypeError, ValueError):
            pass
    num_people = None
    if d.get("num_personas") not in (None, ""):
        try:
            num_people = int(str(d["num_personas"]).strip())
        except (TypeError, ValueError):
            num_people = None

    return {
        "id": d["id"],
        "booking_ref": ref,
        "customer_name": d.get("nombre_cliente"),
        "customer_phone": d.get("telefono"),
        "customer_email": d.get("email"),
        "booking_date": str(d["fecha"]) if d.get("fecha") else "",
        "booking_time": str(d["hora"])[:5] if d.get("hora") else "",
        "num_people": num_people,
        "price_per_person": price_pp,
        "subtotal": float(d.get("ingreso_reserva") or 0),
        "extras_total": float(d.get("ingreso_extras") or 0),
        "flex_amount": float(d.get("flex_amount") or 0),
        "total_price": float(d.get("ingreso_total") or 0),
        "extras": extras_list,
        "has_flex": bool(d.get("has_flex")),
        "status": d.get("status"),
        "payment_id": d.get("payment_id"),
        "payment_order_id": d.get("payment_order_id"),
        "payment_status": d.get("payment_status"),
        "paid_at": str(d["paid_at"]) if d.get("paid_at") else None,
        "source": d.get("source"),
        "notes": d.get("observaciones"),
        "created_at": str(d["created_at"]) if d.get("created_at") else None,
        "confirmation_email_sent_at": str(d["confirmation_email_sent_at"]) if d.get("confirmation_email_sent_at") else None,
        "customer_language": d.get("customer_language") or "es",
        "coupon_code": d.get("coupon_code"),
        "coupon_discount": float(d.get("coupon_discount") or 0),
        "coupon_extra_benefit": d.get("coupon_extra_benefit"),
        "customer_birthday": str(d["customer_birthday"]) if d.get("customer_birthday") else None,
        "utm_source": d.get("utm_source") or "",
        "utm_medium": d.get("utm_medium") or "",
        "utm_campaign": d.get("utm_campaign") or "",
        "utm_content": d.get("utm_content") or "",
        "parametro_url": d.get("parametro_url") or "",
    }


_OLD_PRICES = {2: 69990, 3: 54990, 4: 44990, 5: 38990, 6: 32990, 7: 29990}

def load_prices_from_db() -> None:
    """Load prices per person from hotboat_settings into the live PRICES dict.
    If the DB still holds the old pre-2026-06 prices, auto-migrate to new ones."""
    import json as _json
    try:
        from app.booking.operator_settings import get_setting, set_setting
        raw = get_setting("prices_per_person", "")
        if raw:
            stored = {int(k): int(v) for k, v in _json.loads(raw).items()}
            if stored == _OLD_PRICES:
                # Auto-migrate stale prices to current defaults
                set_setting("prices_per_person", _json.dumps({str(k): v for k, v in PRICES.items()}))
                logger.info("load_prices_from_db: migrated prices to 2026-06 schedule")
            else:
                PRICES.update(stored)
        else:
            set_setting("prices_per_person", _json.dumps({str(k): v for k, v in PRICES.items()}))
    except Exception as e:
        logger.warning(f"load_prices_from_db: {e}")


def generate_booking_ref() -> str:
    year = datetime.now(CHILE_TZ).year
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"HB-{year}-{suffix}"


def create_booking(data: dict) -> dict:
    """Insert a new web booking into ``all_appointments`` (source ``hotboat_web``)."""
    ref = generate_booking_ref()
    fecha = _parse_booking_date(data["booking_date"])
    hora = _parse_booking_time(data["booking_time"])
    bday_raw = data.get("customer_birthday") or None
    bday = None
    if bday_raw:
        try:
            bday = date_type.fromisoformat(str(bday_raw)[:10])
        except ValueError:
            pass
    lang = str(data.get("customer_language") or "es").strip().lower()[:5]
    if lang not in ("es", "en", "pt"):
        lang = "es"
    coupon_code = data.get("coupon_code") or None
    coupon_discount = float(data.get("coupon_discount") or 0)
    coupon_extra = (data.get("coupon_extra_benefit") or "").strip() or None
    if not coupon_code:
        coupon_extra = None
    extras_payload = {
        "price_per_person": int(data["price_per_person"]),
        "extras": data.get("extras") or [],
    }
    utm_source   = str(data.get("utm_source") or "")[:200]
    utm_medium   = str(data.get("utm_medium") or "")[:200]
    utm_campaign = str(data.get("utm_campaign") or "")[:500]
    utm_content  = str(data.get("utm_content") or "")[:500]
    parametro_url = str(data.get("parametro_url") or "")[:500]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO all_appointments (
                    source, source_id, appointment_id,
                    fecha, hora,
                    nombre_cliente, email, telefono,
                    servicio, num_personas,
                    ingreso_reserva, ingreso_extras, ingreso_total,
                    has_flex, flex_amount,
                    extras_json, observaciones,
                    status, customer_language,
                    coupon_code, coupon_discount, coupon_extra_benefit,
                    customer_birthday,
                    utm_source, utm_medium, utm_campaign, utm_content, parametro_url,
                    dp_multiplier, dp_factors,
                    created_at, updated_at
                )
                VALUES (
                    'hotboat_web', %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    'pending_payment', %s,
                    %s, %s, %s,
                    %s,
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    NOW(), NOW()
                )
                RETURNING id, status
                """,
                (
                    ref,
                    ref,
                    fecha,
                    hora,
                    data["customer_name"],
                    data.get("customer_email"),
                    data["customer_phone"],
                    f"HotBoat Web ({data['num_people']}p)",
                    str(data["num_people"]),
                    float(data["subtotal"]),
                    float(data.get("extras_total", 0)),
                    float(data["total_price"]),
                    bool(data.get("has_flex", False)),
                    float(data.get("flex_amount", 0)),
                    json.dumps(extras_payload),
                    data.get("notes") or "",
                    lang,
                    coupon_code,
                    coupon_discount,
                    coupon_extra,
                    bday,
                    utm_source,
                    utm_medium,
                    utm_campaign,
                    utm_content,
                    parametro_url,
                    data.get("dp_multiplier"),
                    json.dumps(data.get("dp_factors") or []),
                ),
            )
            row = cur.fetchone()
            if coupon_code:
                try:
                    cur.execute(
                        "UPDATE coupons SET uses_count=uses_count+1, updated_at=NOW()"
                        " WHERE UPPER(code)=UPPER(%s)",
                        (coupon_code,),
                    )
                except Exception:
                    pass
            conn.commit()
            return {"id": row[0], "booking_ref": ref, "status": row[1]}


def update_booking_payment(booking_ref: str, payment_id: str, payment_order_id: str, payment_status: str) -> bool:
    new_status = "confirmed" if payment_status == "approved" else "pending_payment"
    br = (booking_ref or "").strip()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE all_appointments SET
                    payment_id=%s,
                    payment_order_id=COALESCE(%s, payment_order_id),
                    payment_status=%s,
                    status=%s,
                    paid_at=CASE WHEN %s='approved' THEN NOW() ELSE paid_at END,
                    updated_at=NOW()
                WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s)
                """,
                (payment_id, payment_order_id, payment_status, new_status, payment_status, br),
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated


def get_booking_by_ref(booking_ref: str) -> Optional[dict]:
    br = (booking_ref or "").strip()
    if not br:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source_id, nombre_cliente, telefono, email,
                       fecha, hora, num_personas,
                       ingreso_reserva, ingreso_extras, ingreso_total,
                       extras_json, has_flex, flex_amount,
                       status, payment_id, payment_order_id, payment_status,
                       paid_at, observaciones, created_at, confirmation_email_sent_at,
                       COALESCE(customer_language,'es'), coupon_code, coupon_discount,
                       coupon_extra_benefit, customer_birthday, source,
                       COALESCE(utm_source,''), COALESCE(utm_medium,''),
                       COALESCE(utm_campaign,''), COALESCE(utm_content,''),
                       COALESCE(parametro_url,'')
                FROM all_appointments
                WHERE source = 'hotboat_web' AND TRIM(source_id) = TRIM(%s)
                """,
                (br,),
            )
            row = cur.fetchone()
            if row:
                cols = [
                    "id",
                    "source_id",
                    "nombre_cliente",
                    "telefono",
                    "email",
                    "fecha",
                    "hora",
                    "num_personas",
                    "ingreso_reserva",
                    "ingreso_extras",
                    "ingreso_total",
                    "extras_json",
                    "has_flex",
                    "flex_amount",
                    "status",
                    "payment_id",
                    "payment_order_id",
                    "payment_status",
                    "paid_at",
                    "observaciones",
                    "created_at",
                    "confirmation_email_sent_at",
                    "customer_language",
                    "coupon_code",
                    "coupon_discount",
                    "coupon_extra_benefit",
                    "customer_birthday",
                    "source",
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                    "utm_content",
                    "parametro_url",
                ]
                d = dict(zip(cols, row))
                out = _legacy_booking_from_aa(d)
                for k in ("booking_date", "booking_time", "paid_at", "created_at", "confirmation_email_sent_at"):
                    if out.get(k):
                        out[k] = str(out[k])
                return out

            return None


def get_bookings_pending_payment_email(delay_minutes: int = 5) -> list:
    """Return bookings that are still pending payment after delay_minutes
    and haven't had the booking_created reminder email sent yet.
    Ensures the column exists defensively.
    """
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=delay_minutes)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS pending_email_sent_at TIMESTAMPTZ
            """)
            # Separate from pending_email_sent_at (the customer reminder) —
            # if the customer send keeps failing/never completes, the query
            # below keeps returning this booking every 3-minute sweep, and
            # without its own flag the admin "pago pendiente" alert would
            # keep re-firing forever alongside it instead of only once.
            cur.execute("""
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS pending_admin_email_sent_at TIMESTAMPTZ
            """)
            conn.commit()
    out: List[dict] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, TRIM(source_id) AS booking_ref, nombre_cliente, telefono, email,
                       fecha, hora, num_personas, ingreso_reserva, ingreso_extras, ingreso_total,
                       pending_admin_email_sent_at
                FROM all_appointments
                WHERE source = 'hotboat_web'
                  AND status = 'pending_payment'
                  AND email IS NOT NULL AND TRIM(email) <> ''
                  AND (pending_email_sent_at IS NULL OR pending_admin_email_sent_at IS NULL)
                  AND created_at <= %s
                """,
                (cutoff,),
            )
            cols = [
                "id",
                "booking_ref",
                "customer_name",
                "customer_phone",
                "customer_email",
                "booking_date",
                "booking_time",
                "num_people",
                "subtotal",
                "extras_total",
                "total_price",
                "admin_pending_email_sent_at",
            ]
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                for k in ("booking_date", "booking_time"):
                    if d.get(k):
                        d[k] = str(d[k])
                try:
                    d["num_people"] = int(str(d["num_people"]).strip()) if d.get("num_people") else None
                except (TypeError, ValueError):
                    pass
                out.append(d)
            return out


def mark_pending_email_sent(booking_ref: str) -> bool:
    """Mark the pending-payment reminder email as sent (idempotent)."""
    br = (booking_ref or "").strip()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE all_appointments SET pending_email_sent_at=NOW(), updated_at=NOW() "
                "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s) AND pending_email_sent_at IS NULL",
                (br,),
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated


def mark_admin_pending_email_sent(booking_ref: str) -> bool:
    """Mark the pending-payment ADMIN alert as sent (idempotent). Separate
    from mark_pending_email_sent (the customer reminder) so a customer send
    that keeps failing doesn't keep re-triggering the admin alert too."""
    br = (booking_ref or "").strip()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE all_appointments SET pending_admin_email_sent_at=NOW(), updated_at=NOW() "
                "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s) AND pending_admin_email_sent_at IS NULL",
                (br,),
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated


def mark_confirmation_email_sent(booking_ref: str) -> bool:
    """Set confirmation_email_sent_at once (returns True if row updated)."""
    br = (booking_ref or "").strip()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE all_appointments SET confirmation_email_sent_at=NOW(), updated_at=NOW() "
                "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s) AND confirmation_email_sent_at IS NULL",
                (br,),
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated


def get_bookings_for_followup(hours_after: int) -> list:
    """Return confirmed bookings whose slot + hours_after <= now (Chile), with email,
    follow-up not yet sent. Single source: ``all_appointments`` (HB ref from ``source_id``).
    """
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
                SELECT id,
                       CASE
                         WHEN COALESCE(source, '') = 'hotboat_web'
                              AND COALESCE(TRIM(source_id), '') <> ''
                         THEN TRIM(source_id)
                         ELSE 'MANUAL-' || id::text
                       END AS booking_ref,
                       nombre_cliente AS customer_name,
                       telefono AS customer_phone,
                       email AS customer_email,
                       fecha AS booking_date,
                       hora AS booking_time,
                       NULLIF(num_personas, '')::integer AS num_people,
                       ingreso_reserva AS subtotal,
                       COALESCE(ingreso_extras, 0) AS extras_total,
                       ingreso_total AS total_price,
                       COALESCE(has_flex, FALSE) AS has_flex,
                       COALESCE(flex_amount, 0) AS flex_amount,
                       COALESCE(extras_json::text, 'null') AS extras,
                       observaciones AS notes,
                       COALESCE(customer_language, 'es') AS customer_language
                FROM all_appointments
                WHERE status = 'confirmed'
                  AND email IS NOT NULL AND TRIM(email) <> ''
                  AND followup_email_sent_at IS NULL
                  AND fecha >= CURRENT_DATE - INTERVAL '3 days'
                  AND fecha <= CURRENT_DATE
                  AND (fecha + COALESCE(hora, '12:00:00'::time))
                        AT TIME ZONE 'America/Santiago'
                        + make_interval(hours => %s)
                      <= NOW()
            """, (hours_after,))
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
    Handles both real HB refs and all_appointments (MANUAL-<id> / AA-<id>).
    """
    br = (booking_ref or "").strip()
    with get_connection() as conn:
        with conn.cursor() as cur:
            if br.startswith("MANUAL-") or br.startswith("AA-"):
                row_id = int(br.split("-", 1)[1])
                cur.execute(
                    "UPDATE all_appointments SET followup_email_sent_at=NOW(), updated_at=NOW() "
                    "WHERE id=%s AND followup_email_sent_at IS NULL",
                    (row_id,),
                )
                conn.commit()
                return cur.rowcount > 0
            else:
                cur.execute(
                    "UPDATE all_appointments SET followup_email_sent_at=NOW(), updated_at=NOW() "
                    "WHERE source = 'hotboat_web' AND TRIM(source_id) = TRIM(%s) "
                    "AND followup_email_sent_at IS NULL",
                    (br,),
                )
                updated = cur.rowcount > 0
                conn.commit()
                return updated


def mark_followup_sent_after_manual_send(rid: int) -> None:
    """After admin sends TripAdvisor/follow-up from dashboard: stamp the all_appointments row."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE all_appointments SET followup_email_sent_at=NOW(), updated_at=NOW() WHERE id=%s",
                (rid,),
            )
            conn.commit()


# ── Pre-booking 1-hour notification ──────────────────────────────────────────

def get_bookings_starting_soon(window_minutes: int = 20, target_minutes_ahead: int = 60) -> list:
    """
    Return bookings whose start time is in the notification window.
    Uses ``all_appointments`` only (includes web HB rows).

    Window bounds must use timestamptz (NOW() + interval). Do NOT use
    (NOW() AT TIME ZONE 'America/Santiago') + interval: that yields timestamp
    without time zone and, when compared to booking start as timestamptz,
    PostgreSQL coerces using the session timezone (often UTC), shifting the
    window by ~3–4h vs Chile.
    """
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
                SELECT id,
                       CASE
                         WHEN COALESCE(source, '') = 'hotboat_web'
                              AND COALESCE(TRIM(source_id), '') <> ''
                         THEN TRIM(source_id)
                         ELSE 'MANUAL-' || id::text
                       END AS booking_ref,
                       nombre_cliente AS customer_name,
                       telefono AS customer_phone,
                       email AS customer_email,
                       fecha AS booking_date,
                       hora AS booking_time,
                       NULLIF(num_personas, '')::integer AS num_people,
                       ingreso_total AS total_price,
                       status,
                       COALESCE(source, 'manual') AS source,
                       COALESCE(customer_language,'es') AS customer_language,
                       COALESCE(extras_json::text, '[]') AS extras,
                       COALESCE(ingreso_extras, 0) AS extras_total,
                       observaciones AS notes
                FROM all_appointments
                WHERE (fecha + COALESCE(hora, '12:00:00'::time)) AT TIME ZONE 'America/Santiago'
                      BETWEEN (NOW() + INTERVAL '{target_minutes_ahead - half} minutes')
                          AND (NOW() + INTERVAL '{target_minutes_ahead + half} minutes')
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
    br = (booking_ref or "").strip()
    with get_connection() as conn:
        with conn.cursor() as cur:
            if br.startswith("MANUAL-"):
                row_id = int(br.split("-", 1)[1])
                cur.execute(
                    "UPDATE all_appointments SET pre_booking_notif_sent_at=NOW() "
                    "WHERE id=%s AND pre_booking_notif_sent_at IS NULL",
                    (row_id,),
                )
                conn.commit()
                return cur.rowcount > 0
            cur.execute(
                "UPDATE all_appointments SET pre_booking_notif_sent_at=NOW() "
                "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s) "
                "AND pre_booking_notif_sent_at IS NULL",
                (br,),
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated


def count_previous_bookings(customer_email: str = "", customer_phone: str = "",
                             exclude_ref: str = "") -> int:
    """
    Return the number of *previous confirmed* bookings for this customer
    (matched by email OR phone, excluding the current booking_ref).
    """
    if not customer_email and not customer_phone:
        return 0
    em = customer_email.strip().lower() if customer_email else ""
    ph = customer_phone.strip() if customer_phone else ""
    er = (exclude_ref or "").strip()

    aa_match_parts = []
    aa_params: List[Any] = []
    if em:
        aa_match_parts.append("LOWER(TRIM(email)) = %s")
        aa_params.append(em)
    if ph:
        aa_match_parts.append("telefono = %s")
        aa_params.append(ph)
    aa_match = " OR ".join(aa_match_parts)

    aa_exclude = ""
    if er.startswith("HB-"):
        aa_exclude = " AND NOT (source = 'hotboat_web' AND TRIM(source_id) = TRIM(%s))"
        aa_params.append(er)
    elif er.startswith("MANUAL-") or er.startswith("AA-"):
        try:
            rid = int(er.split("-", 1)[1])
            aa_exclude = " AND id <> %s"
            aa_params.append(rid)
        except ValueError:
            pass

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM all_appointments
                WHERE status = 'confirmed' AND ({aa_match}) {aa_exclude}
                """,
                tuple(aa_params),
            )
            n_aa = int(cur.fetchone()[0] or 0)
            return n_aa


def get_relevant_booking_by_phone(phone: str) -> Optional[dict]:
    """Find the most relevant all_appointments booking for a WhatsApp phone
    number (digits only, e.g. '56977577307'): prefers the soonest upcoming
    reservation; falls back to the most recent past one. Used to auto-fill
    WhatsApp re-engagement/reminder templates from the chat.
    Returns {booking_ref, customer_name, booking_date, booking_time} or None.
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return None
    core = digits[-9:]  # últimos 9 dígitos: robusto a con/sin código de país

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(source_id), ''), 'AA-' || id::text) AS ref,
                       nombre_cliente, fecha, hora
                FROM all_appointments
                WHERE RIGHT(REGEXP_REPLACE(COALESCE(telefono, ''), '[^0-9]', '', 'g'), 9) = %s
                  AND status NOT IN ('cancelled', 'rejected', 'cancelada', 'solicitud')
                  AND fecha >= CURRENT_DATE
                ORDER BY fecha ASC, hora ASC NULLS LAST
                LIMIT 1
                """,
                (core,),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    SELECT COALESCE(NULLIF(TRIM(source_id), ''), 'AA-' || id::text) AS ref,
                           nombre_cliente, fecha, hora
                    FROM all_appointments
                    WHERE RIGHT(REGEXP_REPLACE(COALESCE(telefono, ''), '[^0-9]', '', 'g'), 9) = %s
                      AND status NOT IN ('cancelled', 'rejected', 'cancelada', 'solicitud')
                    ORDER BY fecha DESC, hora DESC NULLS LAST
                    LIMIT 1
                    """,
                    (core,),
                )
                row = cur.fetchone()
            if not row:
                return None
            ref, nombre, fecha, hora = row
            return {
                "booking_ref": ref,
                "customer_name": nombre or "",
                "booking_date": str(fecha) if fecha else "",
                "booking_time": str(hora)[:5] if hora else "",
            }


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
                SELECT DISTINCT ON (LOWER(TRIM(q.customer_email)))
                       q.customer_email, q.customer_name, q.customer_phone,
                       q.booking_ref, q.booking_date, q.booking_time,
                       q.num_people, q.total_price, q.subtotal, q.extras_total,
                       q.customer_language
                FROM (
                    SELECT email AS customer_email,
                           nombre_cliente AS customer_name,
                           telefono AS customer_phone,
                           CASE WHEN COALESCE(TRIM(source_id),'') <> '' AND source = 'hotboat_web'
                                THEN TRIM(source_id)
                                ELSE 'MANUAL-' || id::text END AS booking_ref,
                           fecha AS booking_date,
                           hora AS booking_time,
                           NULLIF(num_personas,'')::integer AS num_people,
                           ingreso_total AS total_price,
                           ingreso_reserva AS subtotal,
                           COALESCE(ingreso_extras, 0) AS extras_total,
                           COALESCE(customer_language, 'es') AS customer_language,
                           created_at
                    FROM all_appointments
                    WHERE customer_birthday IS NOT NULL
                      AND email IS NOT NULL AND TRIM(email) <> ''
                      AND EXTRACT(MONTH FROM customer_birthday) = %s
                      AND EXTRACT(DAY FROM customer_birthday) = %s
                      AND LOWER(TRIM(email)) NOT IN (
                          SELECT LOWER(TRIM(customer_email)) FROM birthday_emails_sent
                          WHERE sent_year = %s
                      )
                ) q
                ORDER BY LOWER(TRIM(q.customer_email)), q.created_at DESC
                """,
                (
                    today.month,
                    today.day,
                    today.year,
                ),
            )
            cols = [
                "customer_email",
                "customer_name",
                "customer_phone",
                "booking_ref",
                "booking_date",
                "booking_time",
                "num_people",
                "total_price",
                "subtotal",
                "extras_total",
                "customer_language",
            ]
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
                -- 020b: pre-booking notification tracker (manual/all_appointments)
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS pre_booking_notif_sent_at TIMESTAMPTZ;

                -- 034: web booking parity on all_appointments (single source of truth)
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS payment_order_id TEXT;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS pending_email_sent_at TIMESTAMPTZ;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS confirmation_email_sent_at TIMESTAMPTZ;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS customer_birthday DATE;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS coupon_code TEXT;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS coupon_discount NUMERIC DEFAULT 0;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS coupon_extra_benefit TEXT;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS customer_language VARCHAR(5) DEFAULT 'es';

                -- 021: multiple images per alojamiento
                ALTER TABLE alojamientos
                    ADD COLUMN IF NOT EXISTS extra_images JSONB DEFAULT '[]';

                -- 032: units per accommodation (e.g. 8 domos at Open Sky)
                ALTER TABLE alojamientos
                    ADD COLUMN IF NOT EXISTS total_units INTEGER DEFAULT 1;

                -- 033: EN/PT copy for booking web (fallback to ES name/description/group_name)
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS name_en TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS name_pt TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS description_en TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS description_pt TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS group_name_en TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS group_name_pt TEXT DEFAULT '';

                -- 028: coupons
                CREATE TABLE IF NOT EXISTS coupons (
                    id SERIAL PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT DEFAULT '',
                    discount_percent NUMERIC DEFAULT 0, discount_fixed NUMERIC DEFAULT 0,
                    extra_description TEXT DEFAULT '', max_uses INT DEFAULT 0,
                    uses_count INT DEFAULT 0, expires_at DATE DEFAULT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                ALTER TABLE coupons ADD COLUMN IF NOT EXISTS rules JSONB DEFAULT NULL;
                ALTER TABLE coupons ADD COLUMN IF NOT EXISTS valid_from DATE DEFAULT NULL;
                ALTER TABLE coupons ADD COLUMN IF NOT EXISTS booking_date_from DATE DEFAULT NULL;
                ALTER TABLE coupons ADD COLUMN IF NOT EXISTS booking_date_to DATE DEFAULT NULL;

                -- 027: stock management tables
                CREATE TABLE IF NOT EXISTS stock_products (
                    id SERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT DEFAULT '',
                    unit TEXT DEFAULT 'unidad', current_stock NUMERIC DEFAULT 0,
                    min_stock NUMERIC DEFAULT 0, cost_per_unit NUMERIC DEFAULT 0,
                    notes TEXT DEFAULT '', is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS extras_bom (
                    id SERIAL PRIMARY KEY, extra_slug TEXT NOT NULL,
                    product_id INT REFERENCES stock_products(id) ON DELETE CASCADE,
                    quantity NUMERIC DEFAULT 1, is_variant BOOLEAN DEFAULT FALSE,
                    variant_label TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_bom_slug ON extras_bom(extra_slug);
                CREATE TABLE IF NOT EXISTS stock_movements (
                    id SERIAL PRIMARY KEY,
                    product_id INT REFERENCES stock_products(id),
                    product_name TEXT DEFAULT '', delta NUMERIC NOT NULL,
                    reason TEXT DEFAULT '', booking_ref TEXT DEFAULT '',
                    extra_slug TEXT DEFAULT '', notes TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements(product_id);
                CREATE INDEX IF NOT EXISTS idx_movements_booking  ON stock_movements(booking_ref);
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS stock_consumed_at TIMESTAMPTZ;

                -- 029a: descuentos column (JSONB array of {amount,type,note})
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS descuentos JSONB DEFAULT '[]'::jsonb;

                -- 030: reserva flex tracking in all_appointments
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS has_flex    BOOLEAN DEFAULT FALSE;
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS flex_amount NUMERIC DEFAULT 0;

                -- 029: financial module tables
                CREATE TABLE IF NOT EXISTS marketing_costs (
                    id SERIAL PRIMARY KEY,
                    fecha DATE NOT NULL,
                    amount NUMERIC NOT NULL DEFAULT 0,
                    category TEXT DEFAULT 'general',
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                -- ensure columns exist even if table was previously created with different schema
                ALTER TABLE marketing_costs ADD COLUMN IF NOT EXISTS fecha        DATE    NOT NULL DEFAULT CURRENT_DATE;
                ALTER TABLE marketing_costs ADD COLUMN IF NOT EXISTS amount       NUMERIC NOT NULL DEFAULT 0;
                ALTER TABLE marketing_costs ADD COLUMN IF NOT EXISTS category     TEXT             DEFAULT 'general';
                ALTER TABLE marketing_costs ADD COLUMN IF NOT EXISTS notes        TEXT             DEFAULT '';
                ALTER TABLE marketing_costs ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ      DEFAULT NOW();
                ALTER TABLE marketing_costs ADD COLUMN IF NOT EXISTS updated_at   TIMESTAMPTZ      DEFAULT NOW();
                CREATE INDEX IF NOT EXISTS idx_marketing_costs_fecha ON marketing_costs(fecha);

                CREATE TABLE IF NOT EXISTS financial_budget (
                    id SERIAL PRIMARY KEY,
                    year INT NOT NULL,
                    month INT NOT NULL,
                    income_budget NUMERIC DEFAULT 0,
                    costs_budget NUMERIC DEFAULT 0,
                    marketing_budget NUMERIC DEFAULT 0,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(year, month)
                );

                -- 031: accommodation booking tables
                CREATE TABLE IF NOT EXISTS accommodation_bookings (
                    id SERIAL PRIMARY KEY,
                    booking_ref TEXT UNIQUE NOT NULL,
                    accommodation_id INTEGER,
                    accommodation_name TEXT DEFAULT '',
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT NOT NULL,
                    customer_email TEXT,
                    check_in DATE NOT NULL,
                    check_out DATE NOT NULL,
                    num_people INTEGER DEFAULT 1,
                    price_per_night INTEGER DEFAULT 0,
                    total_price INTEGER DEFAULT 0,
                    deposit_amount INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending_payment',
                    payment_id TEXT,
                    payment_order_id TEXT,
                    payment_status TEXT,
                    paid_at TIMESTAMPTZ,
                    hotboat_ref TEXT,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_accom_bookings_ref   ON accommodation_bookings(booking_ref);
                CREATE INDEX IF NOT EXISTS idx_accom_bookings_aloj  ON accommodation_bookings(accommodation_id);
                CREATE INDEX IF NOT EXISTS idx_accom_bookings_dates ON accommodation_bookings(check_in, check_out);

                CREATE TABLE IF NOT EXISTS accommodation_blocked_dates (
                    id SERIAL PRIMARY KEY,
                    accommodation_id INTEGER NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    reason TEXT DEFAULT 'Temporada alta',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_accom_blocked_aloj ON accommodation_blocked_dates(accommodation_id);

                -- 035: UTM ad source tracking for web bookings
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS utm_source   TEXT DEFAULT '';
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS utm_medium   TEXT DEFAULT '';
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS utm_campaign TEXT DEFAULT '';
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS utm_content  TEXT DEFAULT '';
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS parametro_url TEXT DEFAULT '';

                -- 033: booking page visitor funnel (analytics)
                CREATE TABLE IF NOT EXISTS booking_visitor_events (
                    id               SERIAL PRIMARY KEY,
                    session_id       VARCHAR(64) NOT NULL,
                    event_type       VARCHAR(96) NOT NULL,
                    extra_date       TEXT,
                    time_label       VARCHAR(16),
                    lang             VARCHAR(8) DEFAULT 'es',
                    referrer         TEXT DEFAULT '',
                    is_returning     BOOLEAN DEFAULT FALSE,
                    recorded_at      TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_booking_visitor_events_session
                    ON booking_visitor_events (session_id);
                CREATE INDEX IF NOT EXISTS idx_booking_visitor_events_recorded
                    ON booking_visitor_events (recorded_at);

                CREATE TABLE IF NOT EXISTS booking_visitor_sessions (
                    id                   SERIAL PRIMARY KEY,
                    session_id           VARCHAR(64) NOT NULL,
                    started_at           TIMESTAMPTZ NOT NULL,
                    ended_at             TIMESTAMPTZ NOT NULL,
                    lang                 VARCHAR(8) DEFAULT 'es',
                    referrer             TEXT DEFAULT '',
                    is_returning         BOOLEAN DEFAULT FALSE,
                    classification     TEXT DEFAULT '',
                    classification_desc  TEXT DEFAULT '',
                    event_count          INTEGER DEFAULT 0,
                    events_json          JSONB DEFAULT '[]'::jsonb,
                    email_sent           BOOLEAN DEFAULT FALSE,
                    created_at           TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_booking_visitor_sessions_started
                    ON booking_visitor_sessions (started_at);
                CREATE INDEX IF NOT EXISTS idx_booking_visitor_sessions_class
                    ON booking_visitor_sessions (classification);

                -- 036: per-day profile key (schedule type / urgency mode assigned to a day)
                ALTER TABLE urgency_days ADD COLUMN IF NOT EXISTS profile_key TEXT DEFAULT NULL;

                -- 037: per-day extra ghost times (additional grey slots visible in the calendar)
                ALTER TABLE urgency_days ADD COLUMN IF NOT EXISTS ghost_times JSONB DEFAULT '[]';

                -- 038: per-client trackable quote links (one unique short link per lead,
                -- so we know exactly if/when they clicked and what they did afterwards).
                CREATE TABLE IF NOT EXISTS tracked_quote_links (
                    id SERIAL PRIMARY KEY,
                    token VARCHAR(16) UNIQUE NOT NULL,
                    phone VARCHAR(50) NOT NULL,
                    customer_name TEXT DEFAULT '',
                    dest TEXT DEFAULT '/booking',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    first_clicked_at TIMESTAMPTZ,
                    last_clicked_at TIMESTAMPTZ,
                    click_count INT DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_tracked_links_phone ON tracked_quote_links(phone);

                -- Link each booking-site visitor event back to the tracked link (if any)
                -- that brought that visitor in, so the funnel can be viewed per client.
                ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS link_token VARCHAR(16);
                CREATE INDEX IF NOT EXISTS idx_booking_visitor_events_link_token ON booking_visitor_events(link_token);
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


def ensure_analytics_views() -> None:
    """Create/refresh the read-only SQL views used for conversion-funnel
    analysis. Kept in its own isolated function (own connection, own
    try/except at the call site) rather than folded into the big
    ensure_db_columns() script — a single bad statement there once blocked
    every migration after it, and CREATE OR REPLACE VIEW is exactly the
    kind of thing worth re-running on every deploy without that risk.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                -- One row per browsing session on the booking site: what did
                -- that visitor reach, regardless of whether a tracked link
                -- brought them in.
                CREATE OR REPLACE VIEW booking_funnel_sessions AS
                SELECT
                    session_id,
                    (ARRAY_AGG(link_token) FILTER (WHERE link_token IS NOT NULL))[1] AS link_token,
                    MIN(recorded_at) AS first_seen_at,
                    MAX(recorded_at) AS last_seen_at,
                    COUNT(*) AS event_count,
                    BOOL_OR(is_returning) AS is_returning,
                    BOOL_OR(event_type = 'view_prices')                                              AS viewed_prices,
                    BOOL_OR(event_type = 'view_reservar')                                             AS entered_booking_flow,
                    BOOL_OR(event_type = 'date_selected')                                             AS selected_date,
                    BOOL_OR(event_type = 'solicitud_form')                                            AS filled_request_form,
                    BOOL_OR(event_type = 'booking_completed')                                         AS completed_booking,
                    BOOL_OR(event_type IN ('view_experiencias', 'view_experiencia_detail'))           AS viewed_experiencias,
                    BOOL_OR(event_type IN ('view_alojamientos', 'view_alojamiento_detail'))           AS viewed_alojamientos,
                    BOOL_OR(event_type IN ('view_packs', 'view_pack_detail', 'view_arma_pack'))       AS viewed_packs
                FROM booking_visitor_events
                GROUP BY session_id;

                -- One row per tracked link (per WhatsApp client) with its
                -- conversion status, aggregated across all sessions tagged
                -- with that token.
                CREATE OR REPLACE VIEW tracked_link_conversion AS
                SELECT
                    tql.token,
                    tql.phone,
                    tql.customer_name,
                    tql.created_at        AS link_created_at,
                    tql.first_clicked_at,
                    tql.last_clicked_at,
                    tql.click_count,
                    MIN(bve.recorded_at) AS first_seen_at,
                    MAX(bve.recorded_at) AS last_seen_at,
                    COUNT(bve.id)        AS event_count,
                    BOOL_OR(bve.event_type = 'view_prices')      AS viewed_prices,
                    BOOL_OR(bve.event_type = 'view_reservar')    AS entered_booking_flow,
                    BOOL_OR(bve.event_type = 'date_selected')    AS selected_date,
                    BOOL_OR(bve.event_type = 'booking_completed') AS completed_booking
                FROM tracked_quote_links tql
                LEFT JOIN booking_visitor_events bve ON bve.link_token = tql.token
                GROUP BY tql.token, tql.phone, tql.customer_name, tql.created_at,
                         tql.first_clicked_at, tql.last_clicked_at, tql.click_count;

                -- Every single action a visitor took, one row per event, with
                -- phone/customer_name attached when it came from a tracked
                -- link. This is the actual behavior detail — the two views
                -- above only summarize whether a stage was reached, not what
                -- was clicked, in what order, or which date/pack/experience.
                CREATE OR REPLACE VIEW booking_visitor_activity AS
                SELECT
                    bve.id,
                    bve.session_id,
                    bve.event_type,
                    bve.extra_date,
                    bve.time_label,
                    bve.recorded_at,
                    bve.lang,
                    bve.referrer,
                    bve.is_returning,
                    bve.link_token,
                    tql.phone,
                    tql.customer_name
                FROM booking_visitor_events bve
                LEFT JOIN tracked_quote_links tql ON tql.token = bve.link_token
                ORDER BY bve.recorded_at DESC;
            """)
            conn.commit()


def ensure_visitor_identity_tables() -> None:
    """Create the tables that link anonymous browsing (session_id/visitor_id) to a
    real phone once someone books directly from the web (ads/organic/direct — not
    via a tracked_quote_links link, which is the only identity source the other
    analytics views above cover). Isolated from ensure_db_columns() for the same
    reason as ensure_analytics_views(): one bad statement here shouldn't block
    every migration listed after it.

    visitor_id matches hb_uid, the persistent localStorage id already set by
    hotboat-marketing-web's tracker.js on hotboat.cl (and forwarded as ?vid= to
    /booking) — so a summary aggregated by visitor_id spans landing + booking,
    not just the single session in which someone happens to book.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS visitor_id VARCHAR(64);
                CREATE INDEX IF NOT EXISTS idx_bve_visitor_id ON booking_visitor_events(visitor_id);

                CREATE TABLE IF NOT EXISTS booking_visitor_identity (
                    id           SERIAL PRIMARY KEY,
                    session_id   VARCHAR(64) NOT NULL,
                    visitor_id   VARCHAR(64),
                    phone        VARCHAR(32),
                    email        VARCHAR(200),
                    name         VARCHAR(200),
                    booking_ref  VARCHAR(50),
                    linked_at    TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_bvi_session_id ON booking_visitor_identity(session_id);
                CREATE INDEX IF NOT EXISTS idx_bvi_visitor_id ON booking_visitor_identity(visitor_id);
                CREATE INDEX IF NOT EXISTS idx_bvi_phone      ON booking_visitor_identity(phone);

                CREATE TABLE IF NOT EXISTS booking_visitor_summary (
                    phone               VARCHAR(32) PRIMARY KEY,
                    visitor_id          VARCHAR(64),
                    session_count       INTEGER DEFAULT 0,
                    event_count         INTEGER DEFAULT 0,
                    first_seen_at       TIMESTAMPTZ,
                    last_seen_at        TIMESTAMPTZ,
                    classification      TEXT DEFAULT '',
                    classification_desc TEXT DEFAULT '',
                    referrer_label      TEXT DEFAULT '',
                    updated_at          TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            conn.commit()


def ensure_dynamic_pricing_columns() -> None:
    """Add the columns that record, at booking-creation time, the exact
    dynamic-pricing multiplier applied and why (which factors contributed).
    Isolated from ensure_db_columns() for the same reason as
    ensure_analytics_views() — a single bad statement there once blocked
    every migration listed after it."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS dp_multiplier NUMERIC;
                ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS dp_factors JSONB;
            """)
            conn.commit()


def ensure_alojamientos_table() -> None:
    """Self-heals the `alojamientos` table, whatever state it's actually in.

    Turns out the table wasn't fully dropped — it survived but is missing
    specific columns (e.g. `group_name`, while `group_name_en`/`group_name_pt`
    are still there), which a plain CREATE TABLE IF NOT EXISTS silently
    no-ops on since the table object already exists. So: create a minimal
    skeleton if the table is truly gone, then ADD COLUMN IF NOT EXISTS for
    every column individually — converges to the full correct schema
    whether the table is missing entirely, missing a handful of columns
    (this case), or already fine. Schema matches exactly what
    /api/content/alojamientos and the admin CRUD endpoints
    (admin_router.py AlojamientoBody) read/write.

    Isolated from ensure_db_columns() — a single bad statement there once
    blocked every migration listed after it."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alojamientos (
                    id SERIAL PRIMARY KEY,
                    slug TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL
                );
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS group_name TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS icon TEXT DEFAULT '🏠';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS name_en TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS name_pt TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS description_en TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS description_pt TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS group_name_en TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS group_name_pt TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS price_from INTEGER DEFAULT 0;
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS cost_from INTEGER DEFAULT 0;
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS capacity INTEGER DEFAULT 2;
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS total_units INTEGER DEFAULT 1;
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS owner_whatsapp TEXT DEFAULT '';
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS image_path TEXT;
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS extra_images JSONB DEFAULT '[]'::jsonb;
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0;
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
                ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
                CREATE INDEX IF NOT EXISTS idx_alojamientos_slug   ON alojamientos(slug);
                CREATE INDEX IF NOT EXISTS idx_alojamientos_active ON alojamientos(is_active);
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
    cols = [
        "booking_ref",
        "customer_name",
        "customer_email",
        "customer_phone",
        "booking_date",
        "booking_time",
        "num_people",
    ]
    rows_out: List[dict] = []
    seen_ref: set = set()

    def _append(d: dict) -> None:
        ref = d.get("booking_ref")
        if ref and ref not in seen_ref:
            seen_ref.add(ref)
            rows_out.append(d)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT TRIM(aa.source_id) AS booking_ref,
                       aa.nombre_cliente AS customer_name,
                       aa.email AS customer_email,
                       aa.telefono AS customer_phone,
                       aa.fecha AS booking_date,
                       aa.hora AS booking_time,
                       NULLIF(aa.num_personas,'')::integer AS num_people
                FROM all_appointments aa
                JOIN hotboat_signatures hs ON hs.booking_ref = TRIM(aa.source_id)
                WHERE aa.source = 'hotboat_web'
                  AND aa.fecha = %s
                """,
                (target_date,),
            )
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                for k in ("booking_date", "booking_time"):
                    if d.get(k):
                        d[k] = str(d[k])
                _append(d)

    rows_out.sort(key=lambda x: str(x.get("booking_time") or ""))
    return rows_out


def get_all_bookings(limit: int = 200) -> List[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,
                       TRIM(source_id) AS booking_ref,
                       nombre_cliente AS customer_name,
                       telefono AS customer_phone,
                       fecha AS booking_date,
                       hora AS booking_time,
                       num_personas AS num_people,
                       ingreso_total AS total_price,
                       status,
                       created_at
                FROM all_appointments
                WHERE source = 'hotboat_web'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            cols = [
                "id",
                "booking_ref",
                "customer_name",
                "customer_phone",
                "booking_date",
                "booking_time",
                "num_people",
                "total_price",
                "status",
                "created_at",
            ]
            rows = cur.fetchall()
            result = []
            for r in rows:
                d = dict(zip(cols, r))
                for k in ("booking_date", "booking_time", "created_at"):
                    if d.get(k):
                        d[k] = str(d[k])
                result.append(d)
            return result
