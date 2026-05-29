"""
Web Push notification system using the W3C Push API + VAPID.
Replaces the previous Expo-based system.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from app.config import get_settings

CHILE_TZ = ZoneInfo("America/Santiago")
logger = logging.getLogger(__name__)

VAPID_CLAIMS = {"sub": "mailto:hotboatnotification@gmail.com"}


def _send_web_push_sync(subscription_info: dict, payload: dict, vapid_private_key: str) -> bool:
    """Blocking Web Push send — run inside asyncio.to_thread."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("pywebpush not installed — add pywebpush>=1.9.4,<2.0.0 to requirements.txt")
        return False
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims=VAPID_CLAIMS,
        )
        return True
    except Exception as exc:
        logger.warning("Web Push send failed (endpoint: %s...): %s",
                       subscription_info.get("endpoint", "")[:40], exc)
        return False


def _send_web_push_sync_verbose(subscription_info: dict, payload: dict, vapid_private_key: str) -> bool:
    """Same as _send_web_push_sync but raises on error (for test endpoint)."""
    from pywebpush import webpush, WebPushException
    webpush(
        subscription_info=subscription_info,
        data=json.dumps(payload),
        vapid_private_key=vapid_private_key,
        vapid_claims=VAPID_CLAIMS,
    )
    return True


class PushNotifier:
    """Send Web Push notifications to browsers/PWA installs."""

    def __init__(self):
        self.settings = get_settings()

    @property
    def _private_key(self) -> Optional[str]:
        return getattr(self.settings, "vapid_private_key", None) or None

    @property
    def enabled(self) -> bool:
        return bool(self._private_key)

    async def send_notification(
        self,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        priority: str = "high",
    ) -> bool:
        if not self.enabled:
            logger.warning("Web Push disabled — VAPID_PRIVATE_KEY not set.")
            return False

        subscriptions = await self._get_subscriptions()
        if not subscriptions:
            logger.warning("No Web Push subscriptions registered.")
            return False

        payload = {"title": title, "body": body, **(data or {})}
        results = await asyncio.gather(
            *[
                asyncio.to_thread(_send_web_push_sync, sub, payload, self._private_key)
                for sub in subscriptions
            ],
            return_exceptions=True,
        )
        sent = sum(1 for r in results if r is True)
        logger.info("Web Push sent to %d/%d subscription(s): %s", sent, len(subscriptions), title[:60])
        return sent > 0

    async def send_new_message_notification(
        self,
        contact_name: str,
        phone_number: str,
        message_preview: str,
        ad_source: str = None,
    ) -> bool:
        title = f"💬 {contact_name}"
        if ad_source:
            title = f"📢 {contact_name}  ·  {ad_source}"

        data = {
            "type": "new_message",
            "phone": phone_number,
            "contact_name": contact_name,
            "timestamp": datetime.now(CHILE_TZ).isoformat(),
        }
        if ad_source:
            data["ad_source"] = ad_source

        return await self.send_notification(title, message_preview[:100], data)

    async def register_subscription(self, endpoint: str, p256dh: str, auth: str) -> bool:
        try:
            from app.db.connection import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO web_push_subscriptions (endpoint, p256dh, auth)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (endpoint) DO UPDATE
                        SET p256dh = EXCLUDED.p256dh,
                            auth   = EXCLUDED.auth,
                            last_used_at = NOW()
                    """, (endpoint, p256dh, auth))
                    conn.commit()
            logger.info("Web Push subscription registered/updated")
            return True
        except Exception as exc:
            logger.error("Error registering Web Push subscription: %s", exc)
            return False

    async def unregister_subscription(self, endpoint: str) -> bool:
        try:
            from app.db.connection import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM web_push_subscriptions WHERE endpoint = %s", (endpoint,))
                    conn.commit()
            return True
        except Exception as exc:
            logger.error("Error unregistering Web Push subscription: %s", exc)
            return False

    async def _get_subscriptions(self) -> List[Dict]:
        try:
            from app.db.connection import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT endpoint, p256dh, auth FROM web_push_subscriptions
                        WHERE last_used_at > NOW() - INTERVAL '90 days'
                    """)
                    rows = cur.fetchall()
            return [
                {"endpoint": r[0], "keys": {"p256dh": r[1], "auth": r[2]}}
                for r in rows
            ]
        except Exception as exc:
            logger.error("Error fetching Web Push subscriptions: %s", exc)
            return []


# Global instance
push_notifier = PushNotifier()
