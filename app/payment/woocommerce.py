"""
WooCommerce payment integration for HotBoat.

Creates orders via WooCommerce REST API and returns payment links
that are sent to clients via WhatsApp.
"""
import os
import hmac
import hashlib
import logging
from urllib.parse import quote
import httpx

logger = logging.getLogger(__name__)

WOO_URL    = os.getenv("WOO_URL", "https://hotboatchile.com")
WOO_CK     = os.getenv("WOO_CK", "")
WOO_CS     = os.getenv("WOO_CS", "")
WOO_SECRET = os.getenv("WOO_WEBHOOK_SECRET", "")
# Public URL of our FastAPI server — used to build branded /pagar links
APP_URL    = os.getenv("PUBLIC_BASE_URL", os.getenv("APP_URL", "https://hotboat-whatsapp-staging-tom.up.railway.app"))

_API = f"{WOO_URL}/wp-json/wc/v3"
_AUTH = (WOO_CK, WOO_CS)


async def create_order(
    *,
    reservation_id: int,
    nombre: str,
    telefono: str | None,
    email: str | None,
    monto_reserva: float,
    monto_extras: float = 0.0,
    fecha: str | None = None,
    num_personas: int | None = None,
) -> dict:
    """
    Create a WooCommerce order and return its payment URL.

    Returns:
        {
          "order_id": int,
          "payment_url": str,   # direct checkout link to send the client
          "status": str,
        }
    """
    total = monto_reserva + monto_extras

    # Build line items as fee_lines (no product catalog needed)
    fee_lines = [
        {
            "name": f"Reserva HotBoat{f' – {num_personas} personas' if num_personas else ''}{f' ({fecha})' if fecha else ''}",
            "total": str(int(monto_reserva)),
        }
    ]
    if monto_extras > 0:
        fee_lines.append({
            "name": "Extras",
            "total": str(int(monto_extras)),
        })

    # Split name into first/last for WooCommerce billing
    parts = (nombre or "Cliente").strip().split()
    first = parts[0]
    last  = " ".join(parts[1:]) if len(parts) > 1 else "."

    payload = {
        "status": "pending",
        "currency": "CLP",
        "billing": {
            "first_name": first,
            "last_name":  last,
            "phone":      telefono or "",
            "email":      email or "reserva@hotboatchile.com",
            "country":    "CL",
        },
        "fee_lines": fee_lines,
        "meta_data": [
            {"key": "hotboat_reservation_id", "value": str(reservation_id)},
        ],
        "customer_note": f"Reserva #{reservation_id} – HotBoat Chile",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{_API}/orders", auth=_AUTH, json=payload)
        resp.raise_for_status()
        data = resp.json()

    order_id    = data["id"]
    order_key   = data.get("order_key", "")
    woo_payment_url = (
        data.get("payment_url") or
        f"{WOO_URL}/checkout/order-pay/{order_id}/?pay_for_order=true&key={order_key}"
    )

    # Build branded /pagar landing page URL that wraps the WooCommerce checkout
    # woo_payment_url contains ? and & so it must be percent-encoded as a param value
    branded_url = (
        f"{APP_URL}/pagar"
        f"?order_id={order_id}"
        f"&key={quote(order_key, safe='')}"
        f"&woo_url={quote(woo_payment_url, safe='')}"
    )

    logger.info(f"WooCommerce order {order_id} created for reservation {reservation_id} – {branded_url}")
    return {
        "order_id":       order_id,
        "order_key":      order_key,
        "payment_url":    branded_url,      # branded page sent to client
        "woo_direct_url": woo_payment_url,  # raw WooCommerce URL (backup)
        "status":         data.get("status", "pending"),
        "total":          total,
    }


async def get_order(order_id: int) -> dict:
    """Fetch a WooCommerce order by ID."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{_API}/orders/{order_id}", auth=_AUTH)
        resp.raise_for_status()
        return resp.json()


async def mark_order_complete(order_id: int) -> None:
    """Mark a WooCommerce order as completed."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.put(
            f"{_API}/orders/{order_id}",
            auth=_AUTH,
            json={"status": "completed"},
        )
        resp.raise_for_status()


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """
    Verify the X-WC-Webhook-Signature header.
    WooCommerce signs with HMAC-SHA256 using the webhook secret.
    """
    if not WOO_SECRET:
        return True   # no secret configured → accept all (dev mode)
    expected = hmac.new(
        WOO_SECRET.encode(),
        body,
        hashlib.sha256,
    ).digest()
    import base64
    return hmac.compare_digest(
        base64.b64encode(expected).decode(),
        signature,
    )
