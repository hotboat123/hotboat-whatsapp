"""Tells GetYourGuide when HotBoat's availability changes (mandatory part of
their Supplier API: POST /1/notify-availability-update).

GYG asks integrators NOT to send scheduled full dumps, only changes. So a
scheduler tick (every ~2 min) computes the bookable slots for the next 150
days, diffs them against the last snapshot we stored, and sends just the
slots whose vacancies changed (7 = free boat, 0 = taken/blocked). Any cause
of change — website booking, WhatsApp bot, admin edit, vacation day, urgency
profile, GYG's own booking — is picked up because we diff the real
availability, not individual events.

The first tick with credentials configured only records a baseline (GYG
already asks get-availabilities for the initial state); it sends nothing.
Off entirely until GYG_NOTIFY_USER / GYG_NOTIFY_PASSWORD are set.
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict

import httpx

from app.booking.gyg_router import (
    CHILE_TZ, MAX_PEOPLE, _configured_product_ids, _iso_local, bookable_slots, release_expired_holds,
)
from app.booking.operator_settings import get_setting, set_setting

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "gyg_availability_snapshot"
_BATCH = 200


def _notify_configured() -> bool:
    return bool(os.environ.get("GYG_NOTIFY_USER") and os.environ.get("GYG_NOTIFY_PASSWORD"))


async def _current_snapshot() -> Dict[str, int]:
    now = datetime.now(CHILE_TZ)
    snap: Dict[str, int] = {}
    for dk, times in (await bookable_slots(fresh=True)).items():
        d = datetime.fromisoformat(dk).date()
        for t in times:
            iso = _iso_local(d, t)
            if datetime.fromisoformat(iso) > now:
                snap[iso] = MAX_PEOPLE
    return snap


async def sync_availability_once() -> dict:
    """One diff-and-notify pass. Returns a small summary for logs/tests."""
    release_expired_holds()
    if not _notify_configured():
        return {"skipped": "credentials not configured"}

    current = await _current_snapshot()
    raw = get_setting(_SNAPSHOT_KEY, "")
    if not raw:
        set_setting(_SNAPSHOT_KEY, json.dumps(current))
        return {"baseline": len(current)}

    previous: Dict[str, int] = json.loads(raw)
    now = datetime.now(CHILE_TZ)
    changes = []
    for iso in sorted(set(current) | set(previous)):
        if datetime.fromisoformat(iso) <= now:
            continue
        new_v, old_v = current.get(iso, 0), previous.get(iso, 0)
        if new_v != old_v:
            changes.append({"dateTime": iso, "vacancies": new_v})
    if not changes:
        return {"changes": 0}

    base = os.environ.get("GYG_NOTIFY_BASE", "https://supplier-api.getyourguide.com").rstrip("/")
    auth = (os.environ["GYG_NOTIFY_USER"], os.environ["GYG_NOTIFY_PASSWORD"])
    new_snapshot = dict(previous)
    sent = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for product_id in sorted(_configured_product_ids()):
            for i in range(0, len(changes), _BATCH):
                batch = changes[i:i + _BATCH]
                try:
                    resp = await client.post(
                        f"{base}/1/notify-availability-update", auth=auth,
                        json={"data": {"productId": product_id, "availabilities": batch}},
                    )
                except Exception as e:
                    logger.warning("GYG notify failed (will retry next tick): %s", e)
                    return {"sent": sent, "error": str(e)[:100]}
                if resp.status_code not in (200, 202):
                    logger.warning("GYG notify rejected %s: %s", resp.status_code, resp.text[:300])
                    return {"sent": sent, "error": f"HTTP {resp.status_code}"}
                sent += len(batch)
                for c in batch:
                    if c["vacancies"]:
                        new_snapshot[c["dateTime"]] = c["vacancies"]
                    else:
                        new_snapshot.pop(c["dateTime"], None)
    set_setting(_SNAPSHOT_KEY, json.dumps(new_snapshot))
    logger.info("GYG availability notified: %d change(s)", sent)
    return {"sent": sent}
