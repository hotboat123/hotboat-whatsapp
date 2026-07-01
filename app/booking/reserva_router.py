"""Public 'Mi Reserva' page: reservation summary + add extras + location.

Used as the destination link for WhatsApp day-of reminder templates
(button URL = /mireserva/{booking_ref}). No admin key required — the
booking_ref itself acts as the access token, same security model already
used by /firma/{ref} and /tabla/{ref}.
"""
import json as _json
import logging
import os
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
reserva_router = APIRouter()

RESERVA_HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "mireserva.html")

# Keep in sync with app/booking/booking_email.py _MAPS_URL
MAPS_URL = "https://maps.app.goo.gl/jVYVHRzekkmFRjEH7"


def _resolve_appointment_row(booking_ref: str):
    """Return the raw all_appointments row needed to append extras, or None."""
    from app.db.connection import get_connection
    ref = (booking_ref or "").strip()
    if not ref:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, extras_json, COALESCE(ingreso_reserva,0), COALESCE(ingreso_extras,0),
                          COALESCE(flex_amount,0), COALESCE(coupon_discount,0)
                   FROM all_appointments WHERE source='hotboat_web' AND source_id=%s LIMIT 1""",
                (ref,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "extras_json": row[1],
                "ingreso_reserva": float(row[2]),
                "ingreso_extras": float(row[3]),
                "flex_amount": float(row[4]),
                "coupon_discount": float(row[5]),
            }


@reserva_router.get("/mireserva/{booking_ref}", response_class=HTMLResponse)
async def serve_mireserva(booking_ref: str):
    if os.path.exists(RESERVA_HTML_PATH):
        with open(RESERVA_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>Página no encontrada</h1>", status_code=404)


@reserva_router.get("/api/mireserva/{booking_ref}")
async def get_mireserva_info(booking_ref: str):
    if booking_ref.strip().lower() == "demo":
        # Datos de muestra: para que la revisión de Meta y las pruebas propias
        # abran una página con contenido real en vez de un 404.
        return {
            "booking_ref": "HB-2026-DEMO",
            "customer_name": "Cliente",
            "booking_date": "2026-12-24",
            "booking_time": "19:00",
            "num_people": 2,
            "status": "confirmed",
            "total_price": 169378,
            "subtotal": 153980,
            "extras_total": 0,
            "extras": [],
            "has_flex": False,
            "flex_amount": 15398,
            "maps_url": MAPS_URL,
        }
    from app.booking.db import get_booking_by_ref
    b = get_booking_by_ref(booking_ref)
    if not b:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return {
        "booking_ref": b.get("booking_ref") or booking_ref,
        "customer_name": b.get("customer_name") or "",
        "booking_date": b.get("booking_date") or "",
        "booking_time": (b.get("booking_time") or "")[:5],
        "num_people": b.get("num_people"),
        "status": b.get("status") or "",
        "total_price": b.get("total_price") or 0,
        "subtotal": b.get("subtotal") or 0,
        "extras_total": b.get("extras_total") or 0,
        "extras": b.get("extras") or [],
        "has_flex": bool(b.get("has_flex")),
        "flex_amount": b.get("flex_amount") or 0,
        "maps_url": MAPS_URL,
    }


class AddExtraItem(BaseModel):
    name: str
    price: float
    quantity: int = 1


class AddExtrasRequest(BaseModel):
    extras: List[AddExtraItem]


@reserva_router.post("/api/mireserva/{booking_ref}/extras")
async def add_extras_to_booking(booking_ref: str, body: AddExtrasRequest):
    if not body.extras:
        raise HTTPException(status_code=400, detail="Selecciona al menos un extra")

    if booking_ref.strip().lower() == "demo":
        added = sum(i.price * i.quantity for i in body.extras)
        return {"ok": True, "extras_total": added, "total_price": 169378 + added, "added_total": added, "demo": True}

    row = _resolve_appointment_row(booking_ref)
    if not row:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    # Parse existing extras_json — may be a plain list (web format) or a dict
    # wrapping {"price_per_person":..., "extras":[...]} (also web format, legacy shape).
    ej = row["extras_json"]
    if isinstance(ej, str):
        try:
            ej = _json.loads(ej)
        except Exception:
            ej = None
    if isinstance(ej, dict):
        existing_list = list(ej.get("extras") or [])
        wrapper = dict(ej)
    elif isinstance(ej, list):
        existing_list = list(ej)
        wrapper = None
    else:
        existing_list = []
        wrapper = None

    by_name = {str(e.get("name", "")).strip().lower(): e for e in existing_list if isinstance(e, dict)}
    added_total = 0.0
    for item in body.extras:
        key = item.name.strip().lower()
        if key in by_name:
            by_name[key]["quantity"] = int(by_name[key].get("quantity", 1)) + item.quantity
        else:
            new_item = {"name": item.name, "price": item.price, "quantity": item.quantity}
            existing_list.append(new_item)
            by_name[key] = new_item
        added_total += item.price * item.quantity

    if wrapper is not None:
        wrapper["extras"] = existing_list
        new_extras_json = wrapper
    else:
        new_extras_json = existing_list

    new_extras_total = row["ingreso_extras"] + added_total
    new_total = row["ingreso_reserva"] + new_extras_total + row["flex_amount"] - row["coupon_discount"]
    if new_total < 0:
        new_total = 0

    from psycopg.types.json import Jsonb as PgJson
    from app.db.connection import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE all_appointments
                   SET extras_json=%s, ingreso_extras=%s, ingreso_total=%s, updated_at=NOW()
                   WHERE id=%s""",
                (PgJson(new_extras_json), new_extras_total, new_total, row["id"]),
            )
            conn.commit()

    logger.info("Extras agregados a %s desde /mireserva: +%s (nuevo total %s)",
                booking_ref, added_total, new_total)

    return {
        "ok": True,
        "extras_total": new_extras_total,
        "total_price": new_total,
        "added_total": added_total,
    }
