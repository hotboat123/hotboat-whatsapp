"""GetYourGuide Supplier API — HotBoat as the "supplier system".

GetYourGuide calls the endpoints below (get-availabilities, reserve,
cancel-reservation, book, cancel-booking) on this server, and we call theirs
to notify availability changes (see app/booking/gyg_sync.py). Spec:
https://integrator.getyourguide.com/documentation/overview

Design (decided with the owner):
- A HotBoat time slot is ONE boat. Any GYG booking, for any group size 2-7,
  blocks the whole slot — the same as a website booking. Prices stay
  configured in the GYG supplier portal (we don't send prices).
- A GYG reservation/booking is a row in ``all_appointments`` with
  source='getyourguide'. That table already drives every availability rule
  (gap hours, urgency, vacation days, website, WhatsApp bot), so a GYG row
  blocks the slot everywhere with no extra blocking logic.
    reserve        -> row with status 'gyg_hold'  (blocks the slot; excluded
                      from revenue reports and from the abandoned-cart email,
                      which only looks at 'pending_payment')
    book           -> same row, status 'confirmed'
    cancel-*       -> status 'cancelled' (frees the slot)
- Disabled (every call answers AUTHORIZATION_FAILURE) until
  GYG_INBOUND_USER / GYG_INBOUND_PASSWORD are set — those are the Basic-auth
  credentials WE give GetYourGuide so it can call us.
- GYG always expects HTTP 200, with either {"data": ...} or {"errorCode": ...}.
"""
import base64
import hmac
import logging
import os
import random
import string
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

gyg_router = APIRouter(prefix="/gyg/1", tags=["getyourguide"])

CHILE_TZ = ZoneInfo("America/Santiago")
MIN_PEOPLE, MAX_PEOPLE = 2, 7
HOLD_MINUTES = 30
NON_BLOCKING_STATUSES = ("cancelled", "rejected", "cancelada", "solicitud")
_UNSUPPORTED_CATEGORIES = {"COLLECTIVE", "GROUP"}


def _configured_product_ids() -> set:
    raw = os.environ.get("GYG_PRODUCT_IDS", "hotboat-tour")
    return {p.strip() for p in raw.split(",") if p.strip()}


def _err(code: str, message: str, **extra) -> dict:
    return {"errorCode": code, "errorMessage": message, **extra}


def _authorized(request: Request) -> bool:
    user = os.environ.get("GYG_INBOUND_USER", "")
    password = os.environ.get("GYG_INBOUND_PASSWORD", "")
    if not user or not password:
        return False
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return False
    try:
        supplied = base64.b64decode(header[6:]).decode("utf-8")
    except Exception:
        return False
    return hmac.compare_digest(supplied, f"{user}:{password}")


def ensure_gyg_tables() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gyg_reservations (
                    reservation_reference TEXT PRIMARY KEY,
                    gyg_booking_reference TEXT NOT NULL,
                    product_id            TEXT NOT NULL,
                    appointment_id        INT,
                    fecha                 DATE NOT NULL,
                    hora                  TIME NOT NULL,
                    num_people            INT NOT NULL,
                    status                TEXT NOT NULL DEFAULT 'held',
                    expires_at            TIMESTAMPTZ NOT NULL,
                    booking_reference     TEXT,
                    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS gyg_res_gygref_idx ON gyg_reservations (gyg_booking_reference)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS gyg_res_bookref_idx ON gyg_reservations (booking_reference) WHERE booking_reference IS NOT NULL")
            conn.commit()


def _rand(n: int) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _parse_dt(raw: str) -> Optional[datetime]:
    """GYG sends ISO 8601 with a UTC offset; we always work in Chile local time."""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=CHILE_TZ)
    return dt.astimezone(CHILE_TZ)


def _iso_local(d, t: str) -> str:
    h, m = map(int, t.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=CHILE_TZ).isoformat()


async def bookable_slots(days: int = 150, fresh: bool = False) -> dict:
    """{'YYYY-MM-DD': ['HH:MM', ...]} of slots a website visitor could book
    right now: the public availability minus the greyed-out ones (urgency
    ghosts, existing bookings). Same source of truth as the booking page."""
    from app.booking import router as booking_router
    if fresh:
        booking_router._avail_cache.clear()
    data = await booking_router.get_availability(days=days)
    grey = data.get("fake_booked_slots") or {}
    out = {}
    for dk, times in (data.get("availability") or {}).items():
        free = [t for t in times if t not in set(grey.get(dk, []))]
        if free:
            out[dk] = sorted(free)
    return out


def _send_owner_email(subject: str, rows: list) -> None:
    """Emails the owner about a GetYourGuide event. Best-effort: a mail failure
    must never change the answer GYG gets (their booking is already saved)."""
    try:
        from html import escape
        from app.booking.booking_email import _get_admin_email
        from app.config import get_settings
        from app.email.send_email import send_email
        settings = get_settings()
        to = _get_admin_email(settings)
        if not to:
            logger.warning("GYG owner email skipped: no admin email configured")
            return
        from_addr = (
            (settings.resend_from_confirmations or "").strip()
            or (settings.email_from or "").strip()
            or "onboarding@resend.dev"
        )
        body = "".join(
            f'<tr><td style="padding:6px 14px 6px 0;color:#6b7280">{escape(k)}</td>'
            f'<td style="padding:6px 0;font-weight:600">{escape(str(v))}</td></tr>'
            for k, v in rows if v
        )
        html = (
            '<div style="font-family:Arial,sans-serif;font-size:15px;color:#111">'
            f'<h2 style="margin:0 0 12px">{escape(subject)}</h2>'
            f'<table style="border-collapse:collapse">{body}</table></div>'
        )
        result = send_email(to=to, subject=subject, html=html, from_address=from_addr, trigger="gyg_notification")
        if not result.get("sent"):
            logger.warning("GYG owner email not sent: %s", result.get("reason"))
    except Exception as e:
        logger.warning("GYG owner email failed: %s", e)


async def _notify_owner(subject: str, rows: list) -> None:
    import asyncio
    await asyncio.to_thread(_send_owner_email, subject, rows)


def _clear_availability_cache() -> None:
    try:
        from app.booking import router as booking_router
        booking_router._avail_cache.clear()
    except Exception:
        pass


# ── GET /1/get-availabilities/ ────────────────────────────────────────────────

@gyg_router.get("/get-availabilities/")
async def get_availabilities(request: Request, productId: str = "", fromDateTime: str = "", toDateTime: str = ""):
    if not _authorized(request):
        return _err("AUTHORIZATION_FAILURE", "The provided authentication credentials are not valid.")
    if productId not in _configured_product_ids():
        return _err("INVALID_PRODUCT", f"Unknown product {productId!r}.")
    start, end = _parse_dt(fromDateTime), _parse_dt(toDateTime)
    if not start or not end or end < start:
        return _err("VALIDATION_FAILURE", "fromDateTime/toDateTime must be ISO 8601 and in order.")
    try:
        now = datetime.now(CHILE_TZ)
        slots = await bookable_slots(fresh=True)
        availabilities = []
        for dk, times in sorted(slots.items()):
            d = datetime.fromisoformat(dk).date()
            for t in times:
                iso = _iso_local(d, t)
                dt = datetime.fromisoformat(iso)
                if dt <= now or dt < start or dt > end:
                    continue
                availabilities.append({"dateTime": iso, "vacancies": MAX_PEOPLE})
        return {"data": {"availabilities": availabilities}}
    except Exception as e:
        logger.exception("gyg get-availabilities failed")
        return _err("INTERNAL_SYSTEM_FAILURE", str(e)[:200])


# ── POST /1/reserve/ ──────────────────────────────────────────────────────────

def _total_people(items) -> Optional[int]:
    try:
        return sum(int(i.get("count") or 0) for i in items)
    except Exception:
        return None


@gyg_router.post("/reserve/")
async def reserve(request: Request):
    if not _authorized(request):
        return _err("AUTHORIZATION_FAILURE", "The provided authentication credentials are not valid.")
    try:
        data = (await request.json()).get("data") or {}
        product_id = data.get("productId", "")
        gyg_ref = str(data.get("gygBookingReference") or "")
        items = data.get("bookingItems") or []
        dt = _parse_dt(data.get("dateTime"))
        if product_id not in _configured_product_ids():
            return _err("INVALID_PRODUCT", f"Unknown product {product_id!r}.")
        if not dt or not gyg_ref or not items:
            return _err("VALIDATION_FAILURE", "dateTime, gygBookingReference and bookingItems are required.")
        if dt <= datetime.now(CHILE_TZ):
            return _err("VALIDATION_FAILURE", "The requested time is in the past.")
        for it in items:
            if str(it.get("category", "")).upper() in _UNSUPPORTED_CATEGORIES:
                return _err("INVALID_TICKET_CATEGORY", "Only individual ticket categories are sellable.",
                            ticketCategory=it.get("category"))
        n = _total_people(items)
        if n is None or not (MIN_PEOPLE <= n <= MAX_PEOPLE):
            return _err("INVALID_PARTICIPANTS_CONFIGURATION",
                        f"HotBoat takes {MIN_PEOPLE} to {MAX_PEOPLE} people per boat.",
                        participantsConfiguration={"min": MIN_PEOPLE, "max": MAX_PEOPLE})

        ensure_gyg_tables()
        fecha, hora = dt.date(), dt.strftime("%H:%M")
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Serialise concurrent reserve/book/cancel for the same slot.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"gyg-slot:{fecha}:{hora}",))

                # GYG retries: same booking reference with a live hold -> same answer.
                cur.execute(
                    "SELECT reservation_reference, expires_at FROM gyg_reservations "
                    "WHERE gyg_booking_reference=%s AND fecha=%s AND hora=%s AND status IN ('held','booked') "
                    "AND expires_at > NOW() ORDER BY created_at DESC LIMIT 1",
                    (gyg_ref, fecha, hora),
                )
                existing = cur.fetchone()
                if existing:
                    return {"data": {"reservationReference": existing[0],
                                     "reservationExpiration": existing[1].astimezone(CHILE_TZ).isoformat()}}

                free = (await bookable_slots(fresh=True)).get(str(fecha), [])
                cur.execute(
                    "SELECT COUNT(*) FROM all_appointments WHERE fecha=%s AND hora=%s "
                    "AND (status IS NULL OR status <> ALL(%s))",
                    (fecha, hora, list(NON_BLOCKING_STATUSES)),
                )
                taken = cur.fetchone()[0]
                if hora not in free or taken:
                    return _err("NO_AVAILABILITY", f"The {fecha} {hora} slot is not available.")

                reservation_ref = "GYGH" + _rand(10)
                expires = datetime.now(CHILE_TZ) + timedelta(minutes=HOLD_MINUTES)
                cur.execute(
                    """INSERT INTO all_appointments
                           (source, source_id, appointment_id, fecha, hora, nombre_cliente, telefono,
                            servicio, num_personas, num_adultos, num_ninos,
                            ingreso_reserva, ingreso_extras, ingreso_total,
                            status, observaciones, created_at, updated_at)
                       VALUES ('getyourguide', %s, %s, %s, %s, 'GetYourGuide (reserva en espera)', '',
                               %s, %s, %s, %s, 0, 0, 0, 'gyg_hold', %s, NOW(), NOW())
                       RETURNING id""",
                    (reservation_ref, reservation_ref, fecha, hora,
                     f"GetYourGuide ({n}p)", str(n),
                     sum(int(i["count"]) for i in items if str(i.get("category")).upper() != "CHILD"),
                     sum(int(i["count"]) for i in items if str(i.get("category")).upper() == "CHILD"),
                     f"GYG ref {gyg_ref} — reserva en espera hasta {expires:%H:%M}"),
                )
                appt_id = cur.fetchone()[0]
                cur.execute(
                    """INSERT INTO gyg_reservations
                           (reservation_reference, gyg_booking_reference, product_id, appointment_id,
                            fecha, hora, num_people, status, expires_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, 'held', %s)""",
                    (reservation_ref, gyg_ref, product_id, appt_id, fecha, hora, n, expires),
                )
                conn.commit()
        _clear_availability_cache()
        return {"data": {"reservationReference": reservation_ref, "reservationExpiration": expires.isoformat()}}
    except Exception as e:
        logger.exception("gyg reserve failed")
        return _err("INTERNAL_SYSTEM_FAILURE", str(e)[:200])


# ── POST /1/cancel-reservation/ ───────────────────────────────────────────────

@gyg_router.post("/cancel-reservation/")
async def cancel_reservation(request: Request):
    if not _authorized(request):
        return _err("AUTHORIZATION_FAILURE", "The provided authentication credentials are not valid.")
    try:
        data = (await request.json()).get("data") or {}
        ref = data.get("reservationReference")
        if not ref:
            return _err("VALIDATION_FAILURE", "reservationReference is required.")
        ensure_gyg_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT appointment_id, status FROM gyg_reservations WHERE reservation_reference=%s", (ref,))
                row = cur.fetchone()
                if not row:
                    return _err("INVALID_RESERVATION", "Reservation does not exist.")
                appt_id, status = row
                if status == "booked":
                    return _err("INVALID_RESERVATION", "Reservation is already booked; cancel the booking instead.")
                if status == "held":
                    cur.execute("UPDATE gyg_reservations SET status='cancelled', updated_at=NOW() WHERE reservation_reference=%s", (ref,))
                    cur.execute("UPDATE all_appointments SET status='cancelled', updated_at=NOW() WHERE id=%s AND status='gyg_hold'", (appt_id,))
                conn.commit()
        _clear_availability_cache()
        return {"data": {}}
    except Exception as e:
        logger.exception("gyg cancel-reservation failed")
        return _err("INTERNAL_SYSTEM_FAILURE", str(e)[:200])


# ── POST /1/book/ ─────────────────────────────────────────────────────────────

@gyg_router.post("/book/")
async def book(request: Request):
    if not _authorized(request):
        return _err("AUTHORIZATION_FAILURE", "The provided authentication credentials are not valid.")
    try:
        data = (await request.json()).get("data") or {}
        res_ref = data.get("reservationReference")
        gyg_ref = str(data.get("gygBookingReference") or "")
        items = data.get("bookingItems") or []
        travelers = data.get("travelers") or []
        if not res_ref or not gyg_ref:
            return _err("VALIDATION_FAILURE", "reservationReference and gygBookingReference are required.")

        ensure_gyg_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT appointment_id, status, expires_at, fecha, hora, num_people, booking_reference, gyg_booking_reference "
                    "FROM gyg_reservations WHERE reservation_reference=%s FOR UPDATE",
                    (res_ref,),
                )
                row = cur.fetchone()
                if not row:
                    return _err("INVALID_RESERVATION", "Reservation does not exist.")
                appt_id, status, expires_at, fecha, hora, n_res, booking_ref, res_gyg_ref = row

                def _ok(ref):
                    return {"data": {"bookingReference": ref,
                                     "tickets": [{"category": "COLLECTIVE", "ticketCode": ref, "ticketCodeType": "TEXT"}]}}

                if status == "booked" and booking_ref and res_gyg_ref == gyg_ref:
                    return _ok(booking_ref)  # GYG retry
                if status != "held" or expires_at <= datetime.now(expires_at.tzinfo):
                    return _err("INVALID_RESERVATION", "Reservation expired or is not in a valid state.")
                n = _total_people(items)
                if n is not None and n != n_res:
                    return _err("VALIDATION_FAILURE", "bookingItems do not match the reservation.")

                lead = travelers[0] if travelers else {}
                name = " ".join(x for x in [lead.get("firstName"), lead.get("lastName")] if x) or "Cliente GetYourGuide"
                booking_ref = "GYG" + _rand(9)
                retail = ", ".join(f"{i.get('category')}x{i.get('count')} @{i.get('retailPrice')} {data.get('currency', '')}" for i in items)
                notes = f"GetYourGuide {gyg_ref} | {retail}"
                if lead.get("email"):
                    notes += f" | Email GYG: {lead['email']}"
                if data.get("comment"):
                    notes += f" | Comentario: {str(data['comment'])[:300]}"
                if data.get("travelerHotel"):
                    notes += f" | Hotel: {data['travelerHotel']}"
                # The traveler's email is kept only in observaciones, not in the
                # email column: HotBoat's own follow-up/marketing emails read that
                # column, and GYG customers are GYG's to contact.
                # ingreso_* stay 0 on purpose: GYG collects the money and pays the
                # supplier net of commission later, so booking it as a normal sale
                # would misstate revenue. Retail price is kept in observaciones.
                cur.execute(
                    """UPDATE all_appointments SET status='confirmed', nombre_cliente=%s, telefono=%s,
                              source_id=%s, observaciones=%s, updated_at=NOW() WHERE id=%s""",
                    (name, lead.get("phoneNumber") or "", booking_ref, notes, appt_id),
                )
                cur.execute(
                    "UPDATE gyg_reservations SET status='booked', booking_reference=%s, gyg_booking_reference=%s, updated_at=NOW() "
                    "WHERE reservation_reference=%s",
                    (booking_ref, gyg_ref, res_ref),
                )
                conn.commit()
        _clear_availability_cache()
        logger.info("GYG booking confirmed: %s (%s %s, %s people)", booking_ref, fecha, hora, n_res)
        await _notify_owner(f"Nueva reserva GetYourGuide — {fecha:%d/%m/%Y} {hora:%H:%M}", [
            ("Fecha", f"{fecha:%d/%m/%Y}"), ("Hora", f"{hora:%H:%M}"), ("Personas", n_res),
            ("Cliente", name), ("Teléfono", lead.get("phoneNumber")), ("Email", lead.get("email")),
            ("Hotel", data.get("travelerHotel")), ("Comentario", data.get("comment")),
            ("Detalle de precio (GYG)", retail), ("Referencia GYG", gyg_ref), ("Referencia HotBoat", booking_ref),
        ])
        return _ok(booking_ref)
    except Exception as e:
        logger.exception("gyg book failed")
        return _err("INTERNAL_SYSTEM_FAILURE", str(e)[:200])


# ── POST /1/cancel-booking/ ───────────────────────────────────────────────────

@gyg_router.post("/cancel-booking/")
async def cancel_booking(request: Request):
    if not _authorized(request):
        return _err("AUTHORIZATION_FAILURE", "The provided authentication credentials are not valid.")
    try:
        data = (await request.json()).get("data") or {}
        ref = data.get("bookingReference")
        if not ref:
            return _err("VALIDATION_FAILURE", "bookingReference is required.")
        ensure_gyg_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT appointment_id, status, fecha, hora, num_people, gyg_booking_reference FROM gyg_reservations WHERE booking_reference=%s FOR UPDATE", (ref,))
                row = cur.fetchone()
                if not row:
                    return _err("INVALID_BOOKING", "Booking does not exist.")
                appt_id, status, fecha, hora, n_people, gyg_ref = row
                if status == "cancelled":
                    return _err("BOOKING_ALREADY_CANCELED", "The booking has been cancelled already.")
                if datetime.combine(fecha, hora, tzinfo=CHILE_TZ) < datetime.now(CHILE_TZ):
                    return _err("BOOKING_IN_PAST", "The booking is in the past.")
                cur.execute("UPDATE gyg_reservations SET status='cancelled', updated_at=NOW() WHERE booking_reference=%s", (ref,))
                cur.execute("UPDATE all_appointments SET status='cancelled', updated_at=NOW() WHERE id=%s", (appt_id,))
                conn.commit()
        _clear_availability_cache()
        logger.info("GYG booking cancelled: %s", ref)
        await _notify_owner(f"Reserva GetYourGuide CANCELADA — {fecha:%d/%m/%Y} {hora:%H:%M}", [
            ("Fecha", f"{fecha:%d/%m/%Y}"), ("Hora", f"{hora:%H:%M}"), ("Personas", n_people),
            ("Referencia GYG", gyg_ref), ("Referencia HotBoat", ref),
            ("Estado", "El horario quedó libre otra vez"),
        ])
        return {"data": {}}
    except Exception as e:
        logger.exception("gyg cancel-booking failed")
        return _err("INTERNAL_SYSTEM_FAILURE", str(e)[:200])


def release_expired_holds() -> int:
    """Frees slots whose GYG reservation was never booked (called by the scheduler)."""
    try:
        ensure_gyg_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE gyg_reservations SET status='expired', updated_at=NOW() "
                    "WHERE status='held' AND expires_at < NOW() RETURNING appointment_id"
                )
                ids = [r[0] for r in cur.fetchall() if r[0]]
                if ids:
                    cur.execute("UPDATE all_appointments SET status='cancelled', updated_at=NOW() WHERE id = ANY(%s) AND status='gyg_hold'", (ids,))
                conn.commit()
        if ids:
            _clear_availability_cache()
            logger.info("GYG: released %d expired hold(s)", len(ids))
        return len(ids)
    except Exception as e:
        logger.error("GYG expired-hold release failed: %s", e)
        return 0
