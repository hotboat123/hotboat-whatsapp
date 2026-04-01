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


@router.get("/api/booking/availability")
async def get_availability(days: int = Query(21, ge=1, le=60)):
    try:
        checker = AvailabilityChecker()
        now = datetime.now(CHILE_TZ)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=days)
        slots = await checker.get_available_slots(start, end)
        grouped: dict = {}
        for s in slots:
            dk = str(s["date"])
            if dk not in grouped:
                grouped[dk] = []
            grouped[dk].append(s["time"])
        return {"availability": grouped, "operating_hours": AVAILABILITY_CONFIG.operating_hours}
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
        payment_url = None
        try:
            payment_url = await _create_mp_preference(result["booking_ref"], request, total)
        except Exception as pe:
            logger.warning(f"MercadoPago skip: {pe}")
        return {
            "booking_ref": result["booking_ref"],
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


