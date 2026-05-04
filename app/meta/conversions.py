"""
Meta Conversions API — report WhatsApp lead and purchase events back to Meta
so the ad algorithm can optimise delivery.

Docs: https://developers.facebook.com/docs/marketing-api/conversions-api
CTWA: https://developers.facebook.com/docs/marketing-api/conversions-api/ctwa
"""
import hashlib
import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_CAPI_URL = "https://graph.facebook.com/v18.0/{pixel_id}/events"


def _hash(value: str) -> str:
    """SHA-256 hash required by Meta for PII fields."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def _phone_e164(phone: str) -> str:
    """Normalise phone to E.164 digits only (no +)."""
    digits = "".join(c for c in phone if c.isdigit())
    if not digits.startswith("56") and len(digits) == 9:
        digits = "56" + digits
    return digits


async def fire_lead_event(
    phone_number: str,
    ctwa_clid: str | None = None,
    ad_name: str | None = None,
) -> bool:
    """
    Send a 'Lead' conversion event to Meta when someone first contacts via CTWA ad.
    Returns True if the API accepted it.
    """
    return await _fire_event("Lead", phone_number, ctwa_clid=ctwa_clid, ad_name=ad_name)


async def fire_purchase_event(
    phone_number: str,
    value: float,
    currency: str = "CLP",
    ctwa_clid: str | None = None,
    ad_name: str | None = None,
) -> bool:
    """
    Send a 'Purchase' conversion event to Meta when a booking is confirmed.
    """
    return await _fire_event(
        "Purchase", phone_number,
        ctwa_clid=ctwa_clid, ad_name=ad_name,
        value=value, currency=currency,
    )


async def _fire_event(
    event_name: str,
    phone_number: str,
    *,
    ctwa_clid: str | None = None,
    ad_name: str | None = None,
    value: float | None = None,
    currency: str = "CLP",
) -> bool:
    cfg = get_settings()
    pixel_id = cfg.meta_pixel_id
    token = cfg.meta_marketing_token or cfg.whatsapp_api_token

    if not pixel_id or not token:
        logger.debug("Meta Conversions API skipped: no pixel_id or token configured")
        return False

    phone_norm = _phone_e164(phone_number)
    user_data: dict = {
        "ph": [_hash(phone_norm)],
    }
    if ctwa_clid:
        user_data["ctwa_clid"] = ctwa_clid

    event: dict = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "action_source": "business_messaging",
        "messaging_channel": "whatsapp",
        "user_data": user_data,
    }
    if ad_name:
        event["custom_data"] = {"ad_name": ad_name}
    if value is not None:
        event.setdefault("custom_data", {})
        event["custom_data"]["value"] = value
        event["custom_data"]["currency"] = currency

    payload = {"data": [event], "access_token": token}

    try:
        url = _CAPI_URL.format(pixel_id=pixel_id)
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            logger.info(f"Meta CAPI {event_name} sent for {phone_number} | clid={ctwa_clid}")
            return True
        else:
            logger.warning(f"Meta CAPI {event_name} error {resp.status_code}: {resp.text[:300]}")
            return False
    except Exception as e:
        logger.warning(f"Meta CAPI {event_name} exception: {e}")
        return False
