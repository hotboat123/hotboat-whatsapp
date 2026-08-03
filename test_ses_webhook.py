"""
Webhook que recibe eventos de SES vía SNS (Delivery, Bounce, Complaint).
SES no tiene webhooks HTTP directos como Resend — SNS empuja
notificaciones firmadas a un endpoint HTTPS que exponemos acá. Es la
parte más delicada de seguridad de toda la migración:

1. Verificación de firma: un mensaje SNS sin firma válida se rechaza
   (app.email.ses_webhook._verify_sns_signature).
2. Allowlist del host del certificado: SOLO se descarga el cert de
   verificación si el host es sns.<region>.amazonaws.com por https — si
   no se restringe esto, un atacante podría apuntar SigningCertURL a un
   host propio (SSRF / spoofing de firma).
3. SubscriptionConfirmation NO se autoconfirma con un GET automático a la
   SubscribeURL — se loguea nomás. La confirmación real (una sola vez, al
   armar el SNS Topic) se hace a mano pegando esa URL en el navegador.
4. Un Notification real se despacha por eventType (Bounce/Complaint
   quedan grep-ables en los logs como SES_BOUNCE/SES_COMPLAINT — ver
   app.email.ses_webhook._handle_ses_event). Este repo no persiste
   bounces en la base todavía (decisión explícita del plan aprobado:
   loguear primero, evaluar si vale la pena guardarlo después de verlo
   correr en producción) — a diferencia del proyecto hermano, que sí
   actualiza una fila de envíos por message id.

Adaptado de las plantillas de la migración de Happy Lápiz a SES.
"""
import base64
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.email.ses_webhook import (
    _build_string_to_sign,
    _is_allowed_cert_host,
    _verify_sns_signature,
    ses_webhook_router,
)


@pytest.fixture(scope="module")
def signing_keypair():
    """Real RSA keypair + self-signed cert, used to actually sign test
    messages the same way SNS would — so the happy path is a genuine
    signature verification, not just a mocked True."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2020, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2099, 1, 1, tzinfo=timezone.utc))
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return private_key, cert_pem


def _sign_message(message: dict, private_key) -> str:
    string_to_sign = _build_string_to_sign(message)
    signature = private_key.sign(string_to_sign, padding.PKCS1v15(), hashes.SHA1())
    return base64.b64encode(signature).decode("ascii")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(ses_webhook_router)
    return TestClient(app)


class TestCertHostAllowlist:
    """El allowlist es la defensa clave — probarlo con casos que DEBEN
    fallar es más importante que el caso feliz."""

    @pytest.mark.parametrize(
        "signing_cert_url,should_be_allowed",
        [
            ("https://sns.us-east-2.amazonaws.com/SimpleNotificationService-abc123.pem", True),
            ("https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-abc123.pem", True),
            ("https://evil.com/fake-cert.pem", False),
            ("https://sns.us-east-2.amazonaws.com.evil.com/cert.pem", False),
            ("http://sns.us-east-2.amazonaws.com/cert.pem", False),  # no-https también debe fallar
            ("https://s3.amazonaws.com/sns.us-east-2.amazonaws.com/cert.pem", False),
        ],
    )
    def test_only_real_sns_hosts_are_allowed(self, signing_cert_url, should_be_allowed):
        assert _is_allowed_cert_host(signing_cert_url) == should_be_allowed


class TestSignatureVerification:
    def test_invalid_signature_is_rejected(self):
        message = {
            "Type": "Notification",
            "MessageId": "abc-123",
            "Message": json.dumps({"eventType": "Delivery"}),
            "Timestamp": "2026-01-01T00:00:00.000Z",
            "TopicArn": "arn:aws:sns:us-east-2:123:hotboat-ses-events",
            "SigningCertURL": "https://sns.us-east-2.amazonaws.com/cert.pem",
            "Signature": base64.b64encode(b"not-a-real-signature").decode("ascii"),
            "SignatureVersion": "1",
        }
        with patch("app.email.ses_webhook._fetch_signing_cert") as mock_fetch:
            mock_fetch.return_value = b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----"
            assert _verify_sns_signature(message) is False

    def test_valid_signature_is_accepted(self, signing_keypair):
        private_key, cert_pem = signing_keypair
        message = {
            "Type": "Notification",
            "MessageId": "abc-123",
            "Message": json.dumps({"eventType": "Delivery"}),
            "Timestamp": "2026-01-01T00:00:00.000Z",
            "TopicArn": "arn:aws:sns:us-east-2:123:hotboat-ses-events",
            "SigningCertURL": "https://sns.us-east-2.amazonaws.com/cert.pem",
            "SignatureVersion": "1",
        }
        message["Signature"] = _sign_message(message, private_key)

        with patch("app.email.ses_webhook._fetch_signing_cert") as mock_fetch:
            mock_fetch.return_value = cert_pem
            assert _verify_sns_signature(message) is True

    def test_rejects_disallowed_cert_host_without_fetching(self, signing_keypair):
        private_key, _ = signing_keypair
        message = {
            "Type": "Notification",
            "MessageId": "abc-123",
            "Message": json.dumps({"eventType": "Delivery"}),
            "Timestamp": "2026-01-01T00:00:00.000Z",
            "TopicArn": "arn:aws:sns:us-east-2:123:hotboat-ses-events",
            "SigningCertURL": "https://evil.com/fake-cert.pem",
            "SignatureVersion": "1",
        }
        message["Signature"] = _sign_message(message, private_key)

        with patch("app.email.ses_webhook._fetch_signing_cert") as mock_fetch:
            assert _verify_sns_signature(message) is False
            mock_fetch.assert_not_called()


class TestSubscriptionConfirmationNeverAutoConfirms:
    """El caso más importante de este archivo: confirmar que NUNCA se
    hace un request HTTP saliente automático a SubscribeURL."""

    def test_subscription_confirmation_only_logs_does_not_fetch_subscribe_url(self, client, signing_keypair):
        private_key, cert_pem = signing_keypair
        payload = {
            "Type": "SubscriptionConfirmation",
            "MessageId": "sub-123",
            "Message": "You have chosen to subscribe to the topic...",
            "SubscribeURL": "https://sns.us-east-2.amazonaws.com/?Action=ConfirmSubscription&TopicArn=...",
            "Timestamp": "2026-01-01T00:00:00.000Z",
            "Token": "abcToken",
            "TopicArn": "arn:aws:sns:us-east-2:123:hotboat-ses-events",
            "SigningCertURL": "https://sns.us-east-2.amazonaws.com/cert.pem",
            "SignatureVersion": "1",
        }
        payload["Signature"] = _sign_message(payload, private_key)

        with patch("app.email.ses_webhook._fetch_signing_cert", return_value=cert_pem), \
             patch("urllib.request.urlopen") as mock_urlopen:
            response = client.post("/api/webhooks/ses", content=json.dumps(payload),
                                    headers={"content-type": "text/plain"})

            assert response.status_code == 200
            assert response.json()["action"] == "manual_confirmation_required"
            # _fetch_signing_cert is mocked above specifically so we can
            # assert the ONLY thing not mocked — a raw urlopen call — is
            # never hit with the SubscribeURL (or at all, in this test).
            mock_urlopen.assert_not_called()


class TestNotificationDispatch:
    @pytest.mark.parametrize(
        "ses_event_type,log_prefix",
        [
            ("Bounce", "SES_BOUNCE"),
            ("Complaint", "SES_COMPLAINT"),
        ],
    )
    def test_event_type_logs_with_grep_able_prefix(self, client, signing_keypair, caplog, ses_event_type, log_prefix):
        """Este repo no tiene todavía una tabla de envíos con message id
        para actualizar el estado (a diferencia del proyecto hermano) —
        la decisión del plan aprobado fue loguear primero, de forma
        grep-able, y evaluar persistirlo después. Este test confirma esa
        parte: el prefijo queda en el log."""
        private_key, cert_pem = signing_keypair
        inner = {
            "eventType": ses_event_type,
            "bounce": {"bounceType": "Permanent", "bounceSubType": "General",
                       "bouncedRecipients": [{"emailAddress": "bounce@simulator.amazonses.com"}]},
            "complaint": {"complaintFeedbackType": "abuse",
                          "complainedRecipients": [{"emailAddress": "complaint@simulator.amazonses.com"}]},
        }
        envelope = {
            "Type": "Notification",
            "MessageId": "notif-123",
            "Message": json.dumps(inner),
            "Timestamp": "2026-01-01T00:00:00.000Z",
            "TopicArn": "arn:aws:sns:us-east-2:123:hotboat-ses-events",
            "SigningCertURL": "https://sns.us-east-2.amazonaws.com/cert.pem",
            "SignatureVersion": "1",
        }
        envelope["Signature"] = _sign_message(envelope, private_key)

        with patch("app.email.ses_webhook._fetch_signing_cert", return_value=cert_pem):
            with caplog.at_level("WARNING"):
                response = client.post("/api/webhooks/ses", content=json.dumps(envelope),
                                        headers={"content-type": "text/plain"})

        assert response.status_code == 200
        assert any(log_prefix in rec.message for rec in caplog.records)

    def test_unsigned_notification_is_rejected_with_400(self, client):
        envelope = {
            "Type": "Notification",
            "Message": json.dumps({"eventType": "Bounce"}),
            "SigningCertURL": "https://evil.com/cert.pem",
            "Signature": "bm90LXJlYWw=",
            "SignatureVersion": "1",
        }
        response = client.post("/api/webhooks/ses", content=json.dumps(envelope),
                                headers={"content-type": "text/plain"})
        assert response.status_code == 400
