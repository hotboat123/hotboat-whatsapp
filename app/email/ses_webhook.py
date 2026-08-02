"""
AWS SES delivery events, pushed via SNS to an HTTPS endpoint (SES has no
direct HTTP webhooks like Resend — everything goes through SNS).

Two message types matter here:

- SubscriptionConfirmation: SNS sends this once, right after the topic
  subscription is created, with a SubscribeURL that must be visited to
  activate the subscription. We deliberately do NOT fetch it automatically —
  a server automatically visiting an attacker-controlled URL is a classic
  SSRF vector, and this endpoint has no way to verify a SubscriptionConfirmation
  actually came from AWS before that confirmation happens. Instead we log it
  prominently so a human confirms it once, by hand, in a browser.
- Notification: the actual Bounce/Complaint/Delivery events.

SNS posts as Content-Type: text/plain (not application/json), so the body
must be parsed manually — FastAPI's request.json()/pydantic body binding
won't fire for it.
"""
import json
import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

ses_webhook_router = APIRouter()


@ses_webhook_router.post("/api/webhooks/ses")
async def ses_events(request: Request):
    raw = await request.body()
    try:
        envelope = json.loads(raw)
    except Exception:
        logger.error("SES webhook: unparseable body: %s", raw[:500])
        return {"ok": False}

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
