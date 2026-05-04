"""Send transactional HTML email via Resend (booking confirmations)."""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def send_booking_html(
    to: str,
    subject: str,
    html: str,
    from_address: str,
    api_key: str,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
) -> dict:
    """
    Returns Resend API response dict, or raises on failure.
    reply_to: if set, customer replies go to this address instead of the From address.
    """
    import resend

    if not api_key:
        raise ValueError("RESEND_API_KEY is not configured")

    resend.api_key = api_key
    payload = {
        "from": from_address,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if bcc:
        payload["bcc"] = bcc
    if reply_to:
        payload["reply_to"] = [reply_to]
    result = resend.Emails.send(payload)
    logger.info("Resend booking email sent to %s id=%s", to, result.get("id", "?"))
    return result
