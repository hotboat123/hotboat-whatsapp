"""
Single funnel for all outgoing transactional email.

Every call site in the app should import `send_email` from here instead of
calling a provider (Resend, SES) directly. This is what makes a global
provider flip (`settings.email_provider`) and the `EMAIL_OVERRIDE_TO` safety
valve apply everywhere at once, instead of needing to be wired into every
call site individually.
"""
import logging
from typing import Any, Dict, List, Optional, Union

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_email(
    to: Union[str, List[str]],
    subject: str,
    html: str,
    from_address: str,
    *,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    trigger: str = "unspecified",
) -> Dict[str, Any]:
    """
    Returns {"sent": bool, "reason": str, "provider": str, "message_id": str|None}.
    Never raises — callers keep the existing "check out['sent']" pattern.

    `trigger` is a free-text label used only for logging (e.g. "booking_confirmed",
    "low_stock_alert") — it doesn't affect routing today, but keeps the door open
    for a future per-trigger provider filter without touching call sites again.
    """
    settings = get_settings()

    if not settings.email_enabled:
        return {"sent": False, "reason": "email_disabled", "provider": None, "message_id": None}

    # EMAIL_OVERRIDE_TO — enforced here, first, before provider selection, so
    # no call site can ever bypass it. Redirects both `to` and `bcc`: a real
    # BCC address leaking real customer data during a staging test is exactly
    # the risk this flag exists to prevent. `reply_to` is left untouched — it
    # doesn't cause a send, it only affects where a human reply would land.
    override = (settings.email_override_to or "").strip()
    real_to, real_bcc = to, bcc
    if override:
        logger.warning(
            "EMAIL_OVERRIDE_TO active: redirecting mail (trigger=%s, real_to=%s, real_bcc=%s) -> %s",
            trigger, real_to, real_bcc, override,
        )
        to = override
        bcc = None
        subject = f"[OVERRIDE was: {real_to}] {subject}"

    provider = (settings.email_provider or "resend").strip().lower()

    try:
        if provider == "ses":
            result = _send_via_ses(settings, to=to, subject=subject, html=html,
                                    from_address=from_address, bcc=bcc, reply_to=reply_to)
            message_id = result.get("MessageId")
        else:
            result = _send_via_resend(settings, to=to, subject=subject, html=html,
                                       from_address=from_address, bcc=bcc, reply_to=reply_to)
            message_id = result.get("id") if isinstance(result, dict) else None
        return {"sent": True, "reason": "ok", "provider": provider, "message_id": message_id}
    except Exception as e:
        error_detail = str(e)
        resp = getattr(e, "response", None)
        if isinstance(resp, dict) and "Error" in resp:
            # botocore.exceptions.ClientError (SES)
            error_detail += f" | ses_code={resp['Error'].get('Code')} ses_message={resp['Error'].get('Message')}"
        elif resp is not None:
            # Resend's ResendError — response is not a plain dict
            error_detail += f" | response: {resp}"
        if hasattr(e, "body"):
            error_detail += f" | body: {e.body}"
        logger.error(
            "Email send FAILED provider=%s trigger=%s to=%s from=%s | %s",
            provider, trigger, to, from_address, error_detail,
        )
        return {"sent": False, "reason": error_detail, "provider": provider, "message_id": None}


def _send_via_resend(settings, *, to, subject, html, from_address, bcc, reply_to):
    from app.email.resend_booking import send_booking_html

    api_key = (settings.resend_api_key or "").strip()
    if not api_key:
        raise ValueError("RESEND_API_KEY is not configured")
    return send_booking_html(
        to=to, subject=subject, html=html, from_address=from_address,
        api_key=api_key, bcc=bcc, reply_to=reply_to,
    )


def _send_via_ses(settings, *, to, subject, html, from_address, bcc, reply_to):
    from app.email.ses_provider import send_booking_html_ses

    return send_booking_html_ses(
        to=to, subject=subject, html=html, from_address=from_address,
        access_key=settings.aws_access_key_id,
        secret_key=settings.aws_secret_access_key,
        region=settings.aws_region,
        configuration_set=settings.ses_configuration_set,
        bcc=bcc, reply_to=reply_to,
    )
