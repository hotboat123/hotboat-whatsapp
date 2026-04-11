"""Public endpoints for passenger T&C signature form."""
import logging
import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
signatures_router = APIRouter()

FIRMA_HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "firma.html")


class SignaturePayload(BaseModel):
    passenger_name: str
    passenger_email: Optional[str] = None
    passenger_phone: Optional[str] = None
    passenger_birthday: Optional[str] = None
    accepted_tc: bool = True


def _resolve_booking(booking_ref: str) -> Optional[dict]:
    """
    Resolve any booking ref format to a dict with booking info.
    Supports:
      - 'HB-YYYY-XXXXX'  → hotboat_appointments.booking_ref
      - 'AA-{int}'       → all_appointments.id
    """
    from app.db.connection import get_connection

    if not booking_ref:
        return None

    # AA-{id} format → all_appointments
    if booking_ref.upper().startswith("AA-"):
        try:
            apt_id = int(booking_ref[3:])
        except ValueError:
            return None
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nombre_cliente, fecha, hora, num_personas, email FROM all_appointments WHERE id=%s",
                    (apt_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "customer_name": row[0] or "",
                    "booking_date": str(row[1]) if row[1] else "",
                    "booking_time": str(row[2])[:5] if row[2] else "",
                    "num_people": row[3],
                    "customer_email": row[4] or "",
                    "booking_ref": booking_ref,
                }

    # HB-xxxx format → hotboat_appointments
    from app.booking.db import get_booking_by_ref
    b = get_booking_by_ref(booking_ref)
    if b:
        return {
            "customer_name": b.get("customer_name") or "",
            "booking_date": str(b.get("booking_date") or ""),
            "booking_time": str(b.get("booking_time") or "")[:5],
            "num_people": b.get("num_people"),
            "customer_email": b.get("customer_email") or "",
            "booking_ref": booking_ref,
        }
    return None


@signatures_router.get("/firma", response_class=HTMLResponse)
async def serve_firma_generic():
    """Serve the T&C signing page without a booking ref (generic QR code on-site)."""
    try:
        with open(FIRMA_HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Página de firma no encontrada")


@signatures_router.get("/firma/{booking_ref:path}", response_class=HTMLResponse)
async def serve_firma_form(booking_ref: str):
    """Serve the T&C signing page pre-linked to a specific booking."""
    try:
        with open(FIRMA_HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Página de firma no encontrada")


@signatures_router.get("/api/firma/bookings")
async def get_bookings_for_date(date: str = ""):
    """Return bookings for a given date (YYYY-MM-DD) for the walk-in selector."""
    from app.db.connection import get_connection
    from datetime import date as _date

    if not date:
        date = str(_date.today())

    try:
        target = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido, usa YYYY-MM-DD")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, nombre_cliente, hora, num_personas, source, source_id
                   FROM all_appointments
                   WHERE fecha = %s
                     AND status NOT IN ('cancelled', 'cancelada')
                   ORDER BY hora ASC NULLS LAST""",
                (target,),
            )
            rows = []
            for row in cur.fetchall():
                apt_id, nombre, hora, num_personas, source, source_id = row
                # Build the booking_ref the same way admin_router does
                if source == "hotboat_web" and source_id:
                    bref = source_id
                else:
                    bref = f"AA-{apt_id}"
                rows.append({
                    "booking_ref": bref,
                    "nombre_cliente": nombre or "Sin nombre",
                    "hora": str(hora)[:5] if hora else "",
                    "num_personas": num_personas or "?",
                })
    return {"date": date, "bookings": rows}


@signatures_router.get("/api/firma/{booking_ref}/info")
async def get_booking_info_for_firma(booking_ref: str):
    """Return minimal booking details shown on the signature form."""
    booking = _resolve_booking(booking_ref)
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return {
        "booking_ref": booking["booking_ref"],
        "booking_date": booking["booking_date"],
        "booking_time": booking["booking_time"],
        "num_people": booking["num_people"],
        "customer_name": booking["customer_name"],
    }


@signatures_router.post("/api/firma/{booking_ref}")
async def submit_signature(booking_ref: str, payload: SignaturePayload, request: Request):
    """Save passenger T&C signature and notify admin."""
    from app.booking.db import create_signature, ensure_signatures_table

    try:
        ensure_signatures_table()
    except Exception as e:
        logger.warning("ensure_signatures_table: %s", e)

    booking = _resolve_booking(booking_ref)
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "")

    sig = create_signature(
        booking_ref=booking_ref,
        data=payload.model_dump(),
        ip=ip,
    )

    try:
        from app.booking.signatures_email import notify_admin_new_signature
        notify_admin_new_signature(sig, booking)
    except Exception as e:
        logger.warning("notify_admin_new_signature failed: %s", e)

    return {"ok": True, "id": sig["id"]}
