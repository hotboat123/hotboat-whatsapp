"""Send transactional HTML email via Resend (booking confirmations)."""
import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def send_booking_html(
    to: Union[str, List[str]],
    subject: str,
    html: str,
    from_address: str,
    api_key: str,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """
    Returns Resend API response dict, or raises on failure.
    reply_to: if set, customer replies go to this address instead of the From address.
    attachments: [{"filename": str, "content": str|bytes, "content_type": str}, ...] —
    passed straight through to Resend's own attachments param.
    """
    import resend

    if not api_key:
        raise ValueError("RESEND_API_KEY is not configured")

    resend.api_key = api_key
    payload = {
        "from": from_address,
        "to": to if isinstance(to, list) else [to],
        "subject": subject,
        "html": html,
    }
    if bcc:
        payload["bcc"] = bcc
    if reply_to:
        payload["reply_to"] = [reply_to]
    if attachments:
        payload["attachments"] = [
            {
                "filename": a["filename"],
                "content": list(a["content"]) if isinstance(a["content"], (bytes, bytearray)) else a["content"],
                **({"content_type": a["content_type"]} if a.get("content_type") else {}),
            }
            for a in attachments
        ]
    result = resend.Emails.send(payload)
    logger.info("Resend booking email sent to %s id=%s", to, result.get("id", "?"))
    return result
