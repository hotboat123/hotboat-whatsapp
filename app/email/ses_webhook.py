"""
AWS SES delivery events, pushed via SNS to an HTTPS endpoint (SES has no
direct HTTP webhooks like Resend — everything goes through SNS).

Every message is signature-verified before being acted on — an unverified
POST to this URL could otherwise inject fake Bounce/Complaint events. Two
things matter for that verification:

- Signature: SNS signs each message (RSA, SHA1 for SignatureVersion "1",
  SHA256 for "2") over a canonical string built from specific fields, using
  a certificate SNS itself points to via SigningCertURL.
- Cert host allowlist: the signing certificate is only ever fetched if
  SigningCertURL's host matches sns.<region>.amazonaws.com over https — an
  attacker could otherwise point SigningCertURL at their own host and get
  us to "verify" a signature against a certificate they control (SSRF /
  signature spoofing). This check happens strictly before any network
  fetch, on the URL alone.

Separately, and unconditionally never automated regardless of signature
validity: SubscriptionConfirmation's SubscribeURL is only ever logged, never
fetched. That confirmation is a one-time step done by hand, in a browser,
when the SNS topic is first wired up — auto-fetching it would be a second,
needless SSRF surface for something that only ever needs to happen once.

SNS posts as Content-Type: text/plain (not application/json), so the body
must be parsed manually — FastAPI's request.json()/pydantic body binding
won't fire for it.
"""
import base64
import json
import logging
import re
import urllib.request
from functools import lru_cache
from urllib.parse import urlparse

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

ses_webhook_router = APIRouter()

_SNS_CERT_HOST_RE = re.compile(r"^sns\.[a-zA-Z0-9-]+\.amazonaws\.com$")

# Field order per AWS's spec — see:
# https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html
_NOTIFICATION_FIELDS = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
_SUBSCRIPTION_FIELDS = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]


def _is_allowed_cert_host(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    return bool(parsed.hostname and _SNS_CERT_HOST_RE.match(parsed.hostname))


@lru_cache(maxsize=8)
def _fetch_signing_cert(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 — host already allowlisted by caller
        return resp.read()


def _build_string_to_sign(message: dict) -> bytes:
    msg_type = message.get("Type", "")
    if msg_type == "Notification":
        fields = _NOTIFICATION_FIELDS
    elif msg_type in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        fields = _SUBSCRIPTION_FIELDS
    else:
        raise ValueError(f"Cannot build string-to-sign for message type: {msg_type!r}")

    parts = []
    for key in fields:
        if key in message:  # "Subject" is optional and often absent
            parts.append(key)
            parts.append(str(message[key]))
    return ("\n".join(parts) + "\n").encode("utf-8")


def _verify_sns_signature(message: dict) -> bool:
    cert_url = message.get("SigningCertURL", "")
    if not _is_allowed_cert_host(cert_url):
        logger.error("SES webhook: rejected SigningCertURL host: %s", cert_url)
        return False

    try:
        cert_bytes = _fetch_signing_cert(cert_url)
        public_key = x509.load_pem_x509_certificate(cert_bytes, default_backend()).public_key()
        signature = base64.b64decode(message.get("Signature", ""))
        string_to_sign = _build_string_to_sign(message)
        algo = hashes.SHA256() if str(message.get("SignatureVersion")) == "2" else hashes.SHA1()
        public_key.verify(signature, string_to_sign, padding.PKCS1v15(), algo)
        return True
    except InvalidSignature:
        logger.error("SES webhook: invalid SNS signature (TopicArn=%s)", message.get("TopicArn"))
        return False
    except Exception as e:
        logger.error("SES webhook: signature verification error: %s", e)
        return False


@ses_webhook_router.post("/api/webhooks/ses")
async def ses_events(request: Request):
    raw = await request.body()
    try:
        envelope = json.loads(raw)
    except Exception:
        logger.error("SES webhook: unparseable body: %s", raw[:500])
        return {"ok": False}

    if not _verify_sns_signature(envelope):
        raise HTTPException(status_code=400, detail="invalid SNS signature")

    msg_type = request.headers.get("x-amz-sns-message-type") or envelope.get("Type", "")

    if msg_type == "SubscriptionConfirmation":
        subscribe_url = envelope.get("SubscribeURL", "")
        logger.warning(
            "SES/SNS SubscriptionConfirmation received for TopicArn=%s — "
            "visit this URL manually in a browser to confirm it (NOT auto-fetched, "
            "to avoid an SSRF risk): %s",
            envelope.get("TopicArn"), subscribe_url,
        )
        return {"ok": True, "action": "manual_confirmation_required"}

    if msg_type == "UnsubscribeConfirmation":
        logger.warning("SES/SNS UnsubscribeConfirmation received: TopicArn=%s", envelope.get("TopicArn"))
        return {"ok": True}

    if msg_type == "Notification":
        try:
            message = json.loads(envelope.get("Message", "{}"))
        except Exception:
            logger.error("SES webhook: Notification with unparseable inner Message")
            return {"ok": False}
        _handle_ses_event(message)
        return {"ok": True}

    logger.warning("SES webhook: unrecognized message type: %s", msg_type)
    return {"ok": True}


def _handle_ses_event(message: dict) -> None:
    event_type = message.get("eventType") or message.get("notificationType") or ""

    if event_type == "Bounce":
        bounce = message.get("bounce", {}) or {}
        recipients = [r.get("emailAddress") for r in bounce.get("bouncedRecipients", []) if r.get("emailAddress")]
        bounce_type = bounce.get("bounceType", "?")
        bounce_subtype = bounce.get("bounceSubType", "?")
        log_fn = logger.error if bounce_type == "Permanent" else logger.warning
        log_fn("SES_BOUNCE type=%s subtype=%s recipients=%s", bounce_type, bounce_subtype, recipients)
        return

    if event_type == "Complaint":
        complaint = message.get("complaint", {}) or {}
        recipients = [r.get("emailAddress") for r in complaint.get("complainedRecipients", []) if r.get("emailAddress")]
        feedback_type = complaint.get("complaintFeedbackType", "?")
        logger.error("SES_COMPLAINT feedback_type=%s recipients=%s", feedback_type, recipients)
        return

    if event_type == "Delivery":
        # Noise, not actionable — skip logging at INFO+ to keep log volume down.
        logger.debug("SES_DELIVERY message=%s", message.get("mail", {}).get("messageId"))
        return

    logger.info("SES event received: eventType=%s", event_type or "unknown")
