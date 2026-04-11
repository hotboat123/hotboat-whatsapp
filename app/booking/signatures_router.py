"""Public endpoints for passenger T&C signature form."""
import logging
import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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


@signatures_router.get("/firma/{booking_ref}", response_class=HTMLResponse)
async def serve_firma_form(booking_ref: str):
    """Serve the T&C signing page (linked from QR code)."""
    try:
        with open(FIRMA_HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Página de firma no encontrada")


@signatures_router.get("/api/firma/{booking_ref}/info")
async def get_booking_info_for_firma(booking_ref: str):
    """Return minimal booking details shown on the signature form."""
    from app.booking.db import get_booking_by_ref
    booking = get_booking_by_ref(booking_ref)
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return {
        "booking_ref": booking_ref,
        "booking_date": str(booking.get("booking_date") or ""),
        "booking_time": str(booking.get("booking_time") or "")[:5],
        "num_people": booking.get("num_people"),
        "customer_name": booking.get("customer_name") or "",
    }


@signatures_router.post("/api/firma/{booking_ref}")
async def submit_signature(booking_ref: str, payload: SignaturePayload, request: Request):
    """Save passenger T&C signature and notify admin."""
    from app.booking.db import get_booking_by_ref, create_signature, ensure_signatures_table

    # Make sure table exists (in case migration hasn't run yet)
    try:
        ensure_signatures_table()
    except Exception as e:
        logger.warning("ensure_signatures_table: %s", e)

    booking = get_booking_by_ref(booking_ref)
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "")

    sig = create_signature(
        booking_ref=booking_ref,
        data=payload.model_dump(),
        ip=ip,
    )

    # Notify admin asynchronously (don't fail the request if email fails)
    try:
        from app.booking.signatures_email import notify_admin_new_signature
        notify_admin_new_signature(sig, booking)
    except Exception as e:
        logger.warning("notify_admin_new_signature failed: %s", e)

    return {"ok": True, "id": sig["id"]}
