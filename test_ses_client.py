"""
Envío directo vía SES (cliente sesv2), mockeado — nunca toca AWS real.

Cubre el bug real encontrado migrando el proyecto hermano (Happy Lápiz) a
SES: un nombre de remitente con tilde/ñ ("Mi Tienda Ñañá") asignado crudo
al header From hace que Python codifique RFC-2047 el header COMPLETO,
incluida la dirección — SES rechaza eso con "Missing final '@domain'".
El fix es email.utils.parseaddr/formataddr para codificar SOLO el
display name (app.email.ses_provider._safe_from_header).

Nota sobre alcance: a diferencia del proyecto hermano, app.email.ses_provider
manda con Content={"Simple": {...}} (no MIME crudo vía Content={"Raw": ...})
porque ningún call site de este repo necesita headers custom
(List-Unsubscribe) ni tags hoy — son todos transaccionales, no campañas de
marketing. Los tests de headers/tags de la plantilla original quedan
marcados skip con ese motivo en vez de forzar una implementación que el
plan aprobado dejó explícitamente para "si hace falta más adelante".

Adaptado de las plantillas de la migración de Happy Lápiz a SES.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.email.ses_provider import _safe_from_header, send_booking_html_ses


@pytest.fixture()
def fake_ses_client():
    """boto3.client('sesv2', ...) mockeado — nunca sale a la red."""
    client = MagicMock()
    client.send_email.return_value = {"MessageId": "fake-message-id-123"}
    return client


class TestFromHeaderEncoding:
    def test_accented_display_name_keeps_address_bare(self):
        """_safe_from_header no debe tocar la dirección aunque el nombre
        tenga tildes/ñ — solo el display name se codifica RFC-2047."""
        result = _safe_from_header("Mi Tienda Ñañá <hola@mitienda.cl>")
        assert result.endswith("<hola@mitienda.cl>"), (
            "la dirección no debe corromperse por el encoding del nombre"
        )
        assert "hola@mitienda.cl" in result
        # El nombre SÍ debe quedar codificado (no ASCII plano) — confirma
        # que efectivamente se aplicó el fix, no que simplemente no se tocó nada.
        assert "Ñañá" not in result or "=?" in result

    def test_plain_ascii_from_is_unaffected(self):
        result = _safe_from_header("HotBoat Reservas <reservas@hotboat.cl>")
        assert result == "HotBoat Reservas <reservas@hotboat.cl>"

    def test_accented_display_name_reaches_ses_send_call_intact(self, fake_ses_client):
        """Extremo a extremo: manda vía send_booking_html_ses con un nombre
        acentuado y confirma que el kwarg FromEmailAddress que le llega a
        boto3 tiene la dirección intacta."""
        with patch("app.email.ses_provider._get_client", return_value=fake_ses_client):
            send_booking_html_ses(
                to="destino@ejemplo.com",
                subject="Asunto de prueba",
                html="<p>Hola</p>",
                from_address="Mi Tienda Ñañá <hola@mitienda.cl>",
                access_key="fake", secret_key="fake", region="us-east-2",
            )

        call_kwargs = fake_ses_client.send_email.call_args.kwargs
        from email.utils import parseaddr
        _, addr = parseaddr(call_kwargs["FromEmailAddress"])
        assert addr == "hola@mitienda.cl"


class TestCustomHeaders:
    @pytest.mark.skip(
        reason="No implementado: ningún call site de este repo necesita "
        "List-Unsubscribe u otros headers custom hoy (son emails "
        "transaccionales, no campañas). send_booking_html_ses manda con "
        "Content={'Simple': ...}; el plan aprobado documenta el camino a "
        "Content={'Raw': ...} con MIME armado a mano como próximo paso si "
        "algún call site llega a necesitarlo — no se construyó especulativamente."
    )
    def test_list_unsubscribe_header_is_included(self):
        pass

    @pytest.mark.skip(reason="Depende de soporte de headers custom — ver motivo arriba.")
    def test_simple_send_email_api_is_not_used_when_headers_needed(self):
        pass


class TestTags:
    @pytest.mark.skip(
        reason="No implementado: no hay uso de tags de Resend en este repo "
        "hoy, así que no había nada que preservar al migrar a SES EmailTags."
    )
    def test_tags_are_forwarded_as_email_tags(self):
        pass


class TestErrorHandling:
    def test_ses_error_propagates_to_caller(self, fake_ses_client):
        """Un error de SES (sandbox, dirección no verificada, etc.) tiene
        que propagarse — send_booking_html_ses no debe tragárselo. Es
        app.email.send_email.send_email (un nivel arriba) quien lo atrapa
        y lo convierte en {"sent": False, "reason": ...} sin tumbar el
        resto del batch — ver test_ses_email_override_and_provider.py."""
        fake_ses_client.send_email.side_effect = Exception("Email address is not verified")

        with patch("app.email.ses_provider._get_client", return_value=fake_ses_client):
            with pytest.raises(Exception, match="Email address is not verified"):
                send_booking_html_ses(
                    to="destino@ejemplo.com", subject="s", html="h",
                    from_address="reservas@hotboat.cl",
                    access_key="fake", secret_key="fake", region="us-east-2",
                )

    def test_missing_credentials_raises_before_any_network_call(self, fake_ses_client):
        with patch("app.email.ses_provider._get_client", return_value=fake_ses_client):
            with pytest.raises(ValueError, match="AWS SES credentials"):
                send_booking_html_ses(
                    to="destino@ejemplo.com", subject="s", html="h",
                    from_address="reservas@hotboat.cl",
                    access_key="", secret_key="", region="us-east-2",
                )
        fake_ses_client.send_email.assert_not_called()
