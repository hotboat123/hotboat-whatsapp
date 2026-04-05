"""FastAPI router for /booking and /api/booking/*"""
import logging, os
from typing import Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.booking.models import CreateBookingRequest
from app.booking.db import (
    create_booking, update_booking_payment,
    get_booking_by_ref, get_all_bookings, PRICES,
    generate_booking_ref,
)
from app.bot.availability import AvailabilityChecker
from app.availability.availability_config import AVAILABILITY_CONFIG

logger = logging.getLogger(__name__)
router = APIRouter()
CHILE_TZ = ZoneInfo("America/Santiago")


def _booking_html() -> str:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "booking.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Booking page not found</h1>"


@router.get("/booking", response_class=HTMLResponse)
async def booking_page():
    return _booking_html()


@router.get("/booking/success", response_class=HTMLResponse)
async def booking_success(
    booking_ref: str = Query(None), payment_id: str = Query(None),
    collection_id: str = Query(None), collection_status: str = Query(None)
):
    pid = payment_id or collection_id or ""
    pstatus = collection_status or "approved"
    if booking_ref and pid:
        try:
            update_booking_payment(booking_ref, pid, pid, pstatus)
        except Exception as e:
            logger.error(f"Payment update error: {e}")
    return _booking_html()


@router.get("/booking/failure", response_class=HTMLResponse)
async def booking_failure(booking_ref: str = Query(None)):
    return _booking_html()


@router.get("/booking/pending", response_class=HTMLResponse)
async def booking_pending(booking_ref: str = Query(None)):
    return _booking_html()


@router.get("/api/booking/dynamic-price")
async def get_dynamic_price(
    date: str = Query(..., description="YYYY-MM-DD"),
    persons: int = Query(2, ge=1, le=8),
):
    """Return dynamic price multiplier and adjusted prices for a given booking date."""
    try:
        from app.booking.operator_settings import get_dp_config, calculate_dynamic_multiplier
        from app.booking.db import PRICES
        from datetime import date as _date

        booking_date = _date.fromisoformat(date)
        today = datetime.now(CHILE_TZ).date()
        days_advance = max(0, (booking_date - today).days)

        # Count confirmed bookings on that day from hotboat_appointments
        bookings_on_day = 0
        try:
            from app.db.connection import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT COUNT(*) FROM hotboat_appointments
                           WHERE booking_date = %s
                             AND status NOT IN ('cancelled','rejected','solicitud')""",
                        (booking_date,),
                    )
                    bookings_on_day = cur.fetchone()[0]
        except Exception as e:
            logger.warning(f"dynamic-price: could not count bookings: {e}")

        cfg = get_dp_config()
        multiplier = calculate_dynamic_multiplier(
            booking_date, bookings_on_day, days_advance, cfg
        )

        # Round adjusted prices to nearest 1000 CLP
        adjusted: dict = {}
        for n, base in PRICES.items():
            adj = round(base * multiplier / 1000) * 1000
            adjusted[str(n)] = {"base": base, "adjusted": adj, "total": adj * n}

        # Determine which factor labels are active (for UI tooltip)
        active_factors = []
        if cfg.get("enabled"):
            for rule in sorted(cfg.get("fill_rate", []), key=lambda r: r["min_bookings"], reverse=True):
                if bookings_on_day >= rule["min_bookings"]:
                    pct = round((rule["multiplier"] - 1) * 100)
                    sign = "+" if pct >= 0 else ""
                    active_factors.append(f"Demanda del día: {sign}{pct}%")
                    break
            for rule in sorted(cfg.get("advance_booking", []), key=lambda r: r["min_days"], reverse=True):
                if days_advance >= rule["min_days"]:
                    pct = round((rule["multiplier"] - 1) * 100)
                    sign = "+" if pct >= 0 else ""
                    active_factors.append(f"Anticipación ({rule.get('label','')}): {sign}{pct}%")
                    break
            weekday = booking_date.weekday()
            wk_mult = float(cfg.get("weekday", {}).get(str(weekday), 1.0))
            if wk_mult != 1.0:
                pct = round((wk_mult - 1) * 100)
                sign = "+" if pct >= 0 else ""
                DAY_NAMES = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
                active_factors.append(f"{DAY_NAMES[weekday]}: {sign}{pct}%")

        return {
            "date": date,
            "dp_enabled": cfg.get("enabled", False),
            "days_advance": days_advance,
            "bookings_on_day": bookings_on_day,
            "multiplier": multiplier,
            "prices": adjusted,
            "active_factors": active_factors,
        }
    except Exception as e:
        logger.error(f"dynamic-price error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/booking/availability")
async def get_availability(days: int = Query(21, ge=1, le=60)):
    try:
        from app.booking.operator_settings import (
            get_vacation_days, is_urgency_mode, apply_urgency_filter
        )
        from app.db.connection import get_connection

        checker = AvailabilityChecker()
        now = datetime.now(CHILE_TZ)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=days)
        slots = await checker.get_available_slots(start, end)

        # Load vacation days for the range
        vacation_dates = {
            v["date"] for v in get_vacation_days(start.date(), end.date())
        }

        # Group slots by date, skipping vacation days
        grouped: dict = {}
        for s in slots:
            dk = str(s["date"])
            if dk in vacation_dates:
                continue
            if dk not in grouped:
                grouped[dk] = []
            grouped[dk].append(s["time"])

        # Apply urgency filter if enabled
        if is_urgency_mode():
            # Get already-booked slots per day from hotboat_appointments
            booked_by_day: dict = {}
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT booking_date::text, booking_time::text
                            FROM hotboat_appointments
                            WHERE booking_date >= %s AND booking_date <= %s
                              AND status NOT IN ('cancelled','rejected','solicitud','pending_payment')
                        """, (start.date(), end.date()))
                        for row in cur.fetchall():
                            d, t = row[0], row[1][:5]  # HH:MM
                            if d not in booked_by_day:
                                booked_by_day[d] = []
                            booked_by_day[d].append(t)
            except Exception as e:
                logger.warning(f"Urgency: could not fetch booked slots: {e}")

            urgency_grouped = {}
            for dk, times in grouped.items():
                booked = booked_by_day.get(dk, [])
                urgency_grouped[dk] = apply_urgency_filter(times, booked)
            grouped = {k: v for k, v in urgency_grouped.items() if v}

        return {
            "availability": grouped,
            "operating_hours": AVAILABILITY_CONFIG.operating_hours,
            "urgency_mode": is_urgency_mode(),
            "vacation_days": list(vacation_dates),
        }
    except Exception as e:
        logger.error(f"Availability error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/booking/prices")
async def get_prices():
    return {"prices": PRICES, "duration_hours": 2}


@router.post("/api/booking/create")
async def create_booking_endpoint(request: CreateBookingRequest):
    try:
        n = request.num_people
        if not (2 <= n <= 7):
            raise HTTPException(status_code=400, detail="Capacidad: 2-7 personas")
        price_pp = PRICES.get(n, 69990)
        subtotal = price_pp * n
        extras_list = [e.dict() for e in request.extras]
        extras_total = sum(e["price"] * e["quantity"] for e in extras_list)
        flex_amount = int(subtotal * 0.1) if request.has_flex else 0
        total = subtotal + extras_total + flex_amount
        data = {
            "customer_name": request.customer_name,
            "customer_phone": request.customer_phone,
            "customer_email": request.customer_email,
            "booking_date": request.booking_date,
            "booking_time": request.booking_time,
            "num_people": n,
            "price_per_person": price_pp,
            "subtotal": subtotal,
            "extras": extras_list,
            "extras_total": extras_total,
            "has_flex": request.has_flex,
            "flex_amount": flex_amount,
            "total_price": total,
            "source": request.source,
            "notes": request.notes,
        }
        result = create_booking(data)
        booking_ref = result["booking_ref"]

        # Determine amount to charge (50% deposit, support test_price override)
        if request.test_price is not None and request.test_price > 0:
            woo_monto_reserva = request.test_price
            woo_monto_extras  = 0
            logger.info(f"TEST MODE: overriding WooCommerce total to {request.test_price} CLP for {booking_ref}")
        else:
            # Charge 50% upfront as deposit via Webpay/Transbank
            woo_monto_reserva = round((subtotal + flex_amount) * 0.5)
            woo_monto_extras  = round(extras_total * 0.5)

        payment_url = None
        woo_order_id = None
        try:
            from app.payment.woocommerce import create_order as woo_create_order
            woo_order = await woo_create_order(
                reservation_id=0,
                booking_ref=booking_ref,
                nombre=request.customer_name,
                telefono=request.customer_phone,
                email=request.customer_email,
                monto_reserva=woo_monto_reserva,
                monto_extras=woo_monto_extras,
                fecha=request.booking_date,
                num_personas=request.num_people,
            )
            payment_url  = woo_order.get("payment_url")
            woo_order_id = woo_order.get("order_id")
        except Exception as pe:
            logger.warning(f"WooCommerce skip: {pe}")
            try:
                payment_url = await _create_mp_preference(booking_ref, request, total)
            except Exception as mpe:
                logger.warning(f"MercadoPago skip: {mpe}")

        # Store WooCommerce order ID so the webhook can find this booking
        if woo_order_id:
            try:
                from app.db.connection import get_connection as _gc
                with _gc() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE hotboat_appointments SET payment_order_id=%s WHERE booking_ref=%s",
                            (str(woo_order_id), booking_ref)
                        )
                        conn.commit()
            except Exception as ue:
                logger.warning(f"Could not save woo_order_id for {booking_ref}: {ue}")

        # NOTE: we do NOT sync to all_appointments here.
        # _sync_hotboat_to_all is called by the WooCommerce webhook once payment is confirmed.
        return {
            "booking_ref": booking_ref,
            "status": result["status"],
            "total_price": total,
            "payment_url": payment_url,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create booking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _create_mp_preference(booking_ref: str, req: CreateBookingRequest, total: int) -> Optional[str]:
    import httpx
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    if not token:
        return None
    base = os.getenv("PUBLIC_BASE_URL", "https://hotboat-app.up.railway.app")
    payload = {
        "items": [{"id": booking_ref, "quantity": 1, "currency_id": "CLP", "unit_price": total,
                   "title": f"HotBoat {req.booking_date} {req.booking_time} {req.num_people}p"}],
        "payer": {"name": req.customer_name, "phone": {"number": req.customer_phone}},
        "back_urls": {
            "success": f"{base}/booking/success?booking_ref={booking_ref}",
            "failure": f"{base}/booking/failure?booking_ref={booking_ref}",
            "pending": f"{base}/booking/pending?booking_ref={booking_ref}",
        },
        "auto_return": "approved",
        "external_reference": booking_ref,
        "statement_descriptor": "HotBoat Chile",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.mercadopago.com/checkout/preferences",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        r.raise_for_status()
        d = r.json()
        return d.get("init_point") or d.get("sandbox_init_point")


@router.get("/api/booking/{booking_ref}")
async def get_booking(booking_ref: str):
    b = get_booking_by_ref(booking_ref)
    if not b:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return b


@router.get("/api/bookings/admin")
async def list_bookings(limit: int = Query(100, ge=1, le=500)):
    try:
        return {"bookings": get_all_bookings(limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SolicitudRequest(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    dates_preference: Optional[str] = None
    people: Optional[str] = None
    notes: Optional[str] = None
    service_type: str = "general"
    title: str = "Solicitud"


@router.post("/api/booking/solicitud")
async def create_solicitud(request: SolicitudRequest):
    """Create a service request (experience, accommodation, pack) — notifies admin."""
    try:
        from app.db.connection import get_connection
        notes_full = (
            f"Servicio: {request.title}\n"
            f"Tipo: {request.service_type}\n"
            f"Fechas: {request.dates_preference or '-'}\n"
            f"Personas: {request.people or '-'}\n"
            f"Notas: {request.notes or '-'}"
        )
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO hotboat_appointments"
                    " (booking_ref,customer_name,customer_phone,customer_email,"
                    "  booking_date,booking_time,num_people,"
                    "  price_per_person,subtotal,total_price,status,source,notes)"
                    " VALUES (%s,%s,%s,%s,CURRENT_DATE,'00:00',1,0,0,0,'solicitud','web',%s)"
                    " RETURNING booking_ref",
                    (
                        generate_booking_ref(),
                        request.customer_name, request.customer_phone,
                        request.customer_email, notes_full
                    )
                )
                ref = cur.fetchone()[0]
                conn.commit()
        try:
            await _notify_solicitud(request, ref)
        except Exception as ne:
            logger.warning(f"Solicitud notification failed: {ne}")
        return {"status": "ok", "booking_ref": ref}
    except Exception as e:
        logger.error(f"Error creating solicitud: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _sync_hotboat_to_all(booking_ref: str, data: dict, status: str):
    """Upsert a hotboat web booking into all_appointments."""
    from app.db.connection import get_connection
    from psycopg.types.json import Jsonb as PgJson
    import re
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM all_appointments WHERE source='hotboat_web' AND source_id=%s", (booking_ref,))
            existing = cur.fetchone()
            if existing:
                # Update status (and total in case it changed) instead of silently returning
                cur.execute(
                    "UPDATE all_appointments SET status=%s, updated_at=NOW() WHERE id=%s",
                    (status, existing[0])
                )
                conn.commit()
                return
            fecha = data.get("booking_date")
            hora = data.get("booking_time")
            num_p = data.get("num_people")
            cur.execute("""
                INSERT INTO all_appointments
                (source, source_id, appointment_id, fecha, hora,
                 nombre_cliente, email, telefono,
                 servicio, num_personas,
                 ingreso_reserva, ingreso_extras, ingreso_total,
                 costo_operativo_fijo, costo_operativo_total,
                 status, extras_json, observaciones, created_at, updated_at)
                VALUES ('hotboat_web',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,18000,18000,%s,%s,%s,NOW(),NOW())
            """, (
                booking_ref, booking_ref, fecha, hora,
                data.get("customer_name"), data.get("customer_email"), data.get("customer_phone"),
                f"HotBoat Web ({num_p}p)", str(num_p),
                float(data.get("subtotal", 0)), float(data.get("extras_total", 0)), float(data.get("total_price", 0)),
                status, PgJson(data.get("extras") or []), data.get("notes")
            ))
            conn.commit()


async def _notify_solicitud(req: SolicitudRequest, ref: str):
    import os, httpx as _httpx
    token = os.getenv("WHATSAPP_API_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    admin = os.getenv("ADMIN_PHONE", "56974950762")
    if not token or not phone_id:
        return
    msg = (
        f"📋 *Nueva Solicitud Web* ({ref})\n\n"
        f"*Servicio:* {req.title}\n"
        f"*Cliente:* {req.customer_name}\n"
        f"*Telefono:* {req.customer_phone}\n"
        f"*Fechas:* {req.dates_preference or '-'}\n"
        f"*Personas:* {req.people or '-'}\n"
        f"*Notas:* {req.notes or '-'}"
    )
    async with _httpx.AsyncClient() as client:
        await client.post(
            f"https://graph.facebook.com/v17.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "to": admin,
                  "type": "text", "text": {"body": msg}},
            timeout=10
        )


