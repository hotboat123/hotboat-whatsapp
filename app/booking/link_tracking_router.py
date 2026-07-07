"""Per-client trackable quote links.

Lets the operator generate a unique short link for ONE specific WhatsApp
lead (e.g. to send "cotiza tu fecha aquí" for dynamic pricing). Opening the
link logs the click against that exact client, then redirects into the
booking site carrying a `?lt=<token>` param — every subsequent funnel event
already tracked by booking-soft.html (_trackEvent) gets tagged with that
token, so the admin can see precisely: did they click? when? what did they
do afterwards (viewed prices, picked a date, completed the booking, or
dropped off)?
"""
import logging
import os
import secrets
import string

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.db.connection import get_connection

logger = logging.getLogger(__name__)
link_tracking_router = APIRouter()

_ALPHABET = string.ascii_lowercase + string.digits


def _check_auth(key: str):
    pass  # auth disabled — same as rest of admin


def _gen_token(n: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def _base_url() -> str:
    """Domain used for the /ir/{token} redirect link sent to customers.
    Prefers PUBLIC_BASE_URL if set (e.g. for local/dev testing on a
    different host); otherwise always uses the real customer-facing
    domain — never the Railway-generated one (staging or otherwise),
    since that's an internal URL customers shouldn't see."""
    base = (os.environ.get("PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    return base or "https://whatsapp.hotboat.cl"


class CreateLinkBody(BaseModel):
    phone: str
    customer_name: str = ""
    dest: str = "/booking"


def create_tracked_link_for_phone(phone: str, customer_name: str = "", dest: str = "/booking") -> dict:
    """Core logic behind POST /api/admin/tracked-links, reusable from plain
    Python (e.g. the WhatsApp bot) without going through the HTTP layer.
    Returns {"token": None, "url": None} if phone has no digits."""
    phone_digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not phone_digits:
        return {"token": None, "url": None}

    token = _gen_token()
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Colisión con un token existente es extremadamente improbable
            # (36^8 combinaciones), pero se reintenta por seguridad.
            for _ in range(3):
                cur.execute("SELECT 1 FROM tracked_quote_links WHERE token=%s", (token,))
                if not cur.fetchone():
                    break
                token = _gen_token()
            cur.execute(
                """INSERT INTO tracked_quote_links (token, phone, customer_name, dest)
                   VALUES (%s, %s, %s, %s)""",
                (token, phone_digits, (customer_name or "").strip(), dest or "/booking"),
            )
            conn.commit()

    base = _base_url()
    url = f"{base}/ir/{token}" if base else f"/ir/{token}"
    return {"token": token, "url": url}


@link_tracking_router.post("/api/admin/tracked-links")
def create_tracked_link(body: CreateLinkBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    result = create_tracked_link_for_phone(body.phone, body.customer_name, body.dest)
    if not result["token"]:
        raise HTTPException(status_code=400, detail="Teléfono requerido")
    return {"ok": True, **result}


@link_tracking_router.get("/ir/{token}")
def open_tracked_link(token: str):
    """Registra el clic (primera vez y contador) y redirige al destino con
    el token embebido para que el embudo de esa visita quede identificado."""
    token = (token or "").strip()[:16]
    dest = "/booking"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT dest FROM tracked_quote_links WHERE token=%s", (token,))
            row = cur.fetchone()
            if row:
                dest = row[0] or "/booking"
                cur.execute(
                    """UPDATE tracked_quote_links
                       SET click_count = click_count + 1,
                           last_clicked_at = NOW(),
                           first_clicked_at = COALESCE(first_clicked_at, NOW())
                       WHERE token=%s""",
                    (token,),
                )
                conn.commit()
            else:
                logger.warning("Tracked link no encontrado: %s", token)
    sep = "&" if "?" in dest else "?"
    return RedirectResponse(url=f"{dest}{sep}lt={token}", status_code=302)


@link_tracking_router.get("/api/admin/tracked-links")
def list_tracked_links(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT token, phone, customer_name, created_at,
                          first_clicked_at, last_clicked_at, click_count
                   FROM tracked_quote_links
                   ORDER BY created_at DESC LIMIT 300"""
            )
            cols = ["token", "phone", "customer_name", "created_at",
                    "first_clicked_at", "last_clicked_at", "click_count"]
            rows = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                for k in ("created_at", "first_clicked_at", "last_clicked_at"):
                    if d.get(k):
                        d[k] = str(d[k])
                rows.append(d)
    return {"links": rows}


@link_tracking_router.get("/api/admin/tracked-links/{token}/funnel")
def get_tracked_link_funnel(token: str, x_admin_key: str = Header("")):
    """Datos del link + línea de tiempo de eventos de esa visita puntual."""
    _check_auth(x_admin_key)
    token = (token or "").strip()[:16]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT token, phone, customer_name, created_at,
                          first_clicked_at, last_clicked_at, click_count
                   FROM tracked_quote_links WHERE token=%s""",
                (token,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Link no encontrado")
            link = dict(zip(
                ["token", "phone", "customer_name", "created_at",
                 "first_clicked_at", "last_clicked_at", "click_count"],
                row,
            ))
            for k in ("created_at", "first_clicked_at", "last_clicked_at"):
                if link.get(k):
                    link[k] = str(link[k])

            cur.execute(
                """SELECT event_type, extra_date, time_label, recorded_at
                   FROM booking_visitor_events
                   WHERE link_token = %s
                   ORDER BY recorded_at ASC""",
                (token,),
            )
            events = [
                {"event_type": e[0], "extra_date": e[1], "time_label": e[2], "recorded_at": str(e[3])}
                for e in cur.fetchall()
            ]
    return {"link": link, "events": events}
