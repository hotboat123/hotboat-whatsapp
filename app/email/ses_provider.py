"""Send transactional HTML email via AWS SES (sesv2 client)."""
import logging
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@lru_cache()
def _get_client(access_key: str, secret_key: str, region: str):
    import boto3
    return boto3.client(
        "sesv2",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def _safe_from_header(from_address: str) -> str:
    """
    Encode ONLY the display-name portion of a 'Name <addr>' string, leaving
    the email address bare.

    Handing the raw string straight to SES/a MIME encoder RFC-2047-encodes
    the whole thing (name + address) when the name has non-ASCII characters
    (e.g. accented "Mi Tienda Ñañá"), and SES then rejects the result with
    "Missing final '@domain'". parseaddr/formataddr avoids that by encoding
    only the name.
    """
    name, addr = parseaddr(from_address)
    if not addr:
        return from_address  # already bare or unparseable — pass through as-is
    return formataddr((name, addr))


def _build_raw_message(*, to, subject, html, from_address, bcc, reply_to, attachments) -> bytes:
    """Hand-built MIME message for the Content={"Raw": ...} path — SES only
    needs this when a call site needs something Content={"Simple": ...}
    can't carry (attachments here; custom headers if that's ever needed).
    Recipients go in real headers, since SES ignores Destination for Raw
    content and expects To/Cc/Bcc in the MIME text itself."""
    to_list = to if isinstance(to, list) else [to]
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = ", ".join(to_list)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText(html, "html", "utf-8"))

    for a in attachments:
        content = a["content"]
        if isinstance(content, str):
            content = content.encode("utf-8")
        part = MIMEApplication(content, Name=a["filename"])
        part["Content-Disposition"] = f'attachment; filename="{a["filename"]}"'
        if a.get("content_type"):
            part.set_type(a["content_type"])
        msg.attach(part)

    return msg.as_bytes()


def send_booking_html_ses(
    to: Union[str, List[str]],
    subject: str,
    html: str,
    from_address: str,
    access_key: str,
    secret_key: str,
    region: str,
    configuration_set: str = "",
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """
    Returns the SES sesv2 send_email response dict, or raises on failure.

    Uses Content={"Simple": {...}} for the common case — no custom headers
    (e.g. List-Unsubscribe) are supported that way. With `attachments`, falls
    back to Content={"Raw": {"Data": <bytes>}} with a hand-built MIME message
    (still run the From header through _safe_from_header first).
    """
    if not access_key or not secret_key:
        raise ValueError("AWS SES credentials are not configured")

    client = _get_client(access_key, secret_key, region)
    safe_from = _safe_from_header(from_address)

    if attachments:
        raw = _build_raw_message(
            to=to, subject=subject, html=html, from_address=safe_from,
            bcc=bcc, reply_to=reply_to, attachments=attachments,
        )
        kwargs = dict(FromEmailAddress=safe_from, Content={"Raw": {"Data": raw}})
        if configuration_set:
            kwargs["ConfigurationSetName"] = configuration_set
        result = client.send_email(**kwargs)
        logger.info("SES booking email (raw, %d attachment(s)) sent to %s id=%s",
                    len(attachments), to, result.get("MessageId", "?"))
        return result

    destination = {"ToAddresses": to if isinstance(to, list) else [to]}
    if bcc:
        destination["BccAddresses"] = bcc

    kwargs = dict(
        FromEmailAddress=safe_from,
        Destination=destination,
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
            }
        },
    )
    if reply_to:
        kwargs["ReplyToAddresses"] = [reply_to]
    if configuration_set:
        kwargs["ConfigurationSetName"] = configuration_set

    result = client.send_email(**kwargs)
    logger.info("SES booking email sent to %s id=%s", to, result.get("MessageId", "?"))
    return result
