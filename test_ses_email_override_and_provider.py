"""
La red de seguridad de toda la migración Resend -> SES.

1. EMAIL_OVERRIDE_TO: si está seteada (staging), TODO envío se redirige a
   esa dirección sin importar el destinatario real (to Y bcc) — con el
   destinatario original taggeado en el asunto para que siga siendo
   trazable. Se aplica en UN SOLO lugar (app.email.send_email.send_email),
   no repetido en cada call site.

2. Resolución de proveedor: settings.email_provider decide Resend vs SES,
   global (no por tienda/cliente — a diferencia del proyecto hermano donde
   esto se adaptó de, acá es un solo negocio, no multi-tenant, así que no
   existe el concepto de "entidad migrada" por separado). El default
   siempre es "resend" hasta que se cambie explícitamente.

Adaptado de las plantillas de la migración de Happy Lápiz a SES.
"""
import subprocess
from pathlib import Path

import pytest

from app.email import send_email as send_email_module
from app.config import get_settings

REPO_ROOT = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fake_provider(monkeypatch):
    """Stub out the actual provider call so no real send happens; captures
    exactly what send_email() decided to send."""
    calls = []

    def _fake(settings, *, to, subject, html, from_address, bcc, reply_to):
        calls.append(dict(to=to, subject=subject, bcc=bcc, from_address=from_address, reply_to=reply_to))
        return {"id": "fake-id-123", "MessageId": "fake-id-123"}

    monkeypatch.setattr(send_email_module, "_send_via_resend", _fake)
    monkeypatch.setattr(send_email_module, "_send_via_ses", _fake)
    return calls


class TestEmailOverride:
    def test_noop_when_override_not_set(self, monkeypatch, fake_provider):
        settings = get_settings()
        monkeypatch.setattr(settings, "email_enabled", True)
        monkeypatch.setattr(settings, "email_override_to", "")

        result = send_email_module.send_email(
            to="real@cliente.com", subject="Asunto", html="<p>hola</p>",
            from_address="noreply@hotboat.cl",
        )

        assert result["sent"] is True
        assert fake_provider[0]["to"] == "real@cliente.com"
        assert fake_provider[0]["subject"] == "Asunto"

    def test_redirects_to_and_bcc_when_set(self, monkeypatch, fake_provider):
        settings = get_settings()
        monkeypatch.setattr(settings, "email_enabled", True)
        monkeypatch.setattr(settings, "email_override_to", "tester@ejemplo.com")

        result = send_email_module.send_email(
            to="real1@cliente.com", subject="Asunto", html="<p>hola</p>",
            from_address="noreply@hotboat.cl", bcc=["admin@hotboat.cl"],
        )

        assert result["sent"] is True
        call = fake_provider[0]
        assert call["to"] == "tester@ejemplo.com"
        assert "real1@cliente.com" in call["subject"]
        # bcc must be suppressed too, not just `to` — a real bcc leaking
        # customer data during a staging test is exactly the risk this
        # flag exists to prevent.
        assert call["bcc"] is None

    def test_override_is_applied_by_every_send_call_site(self):
        """El test más importante de este archivo: confirmar que ningún
        call site llama al SDK de Resend o boto3 directo, saltándose
        send_email() (y por lo tanto el override)."""
        result_resend = subprocess.run(
            ["grep", "-rl", "resend.Emails.send", str(REPO_ROOT / "app")],
            capture_output=True, text=True,
        )
        files_calling_resend_directly = [f for f in result_resend.stdout.splitlines() if f]
        assert len(files_calling_resend_directly) == 1, (
            f"el SDK de Resend se llama directo desde más de un archivo: {files_calling_resend_directly}"
        )
        assert files_calling_resend_directly[0].replace("\\", "/").endswith("app/email/resend_booking.py")

        result_boto = subprocess.run(
            ["grep", "-rl", "boto3.client(", str(REPO_ROOT / "app")],
            capture_output=True, text=True,
        )
        files_calling_boto_directly = [f for f in result_boto.stdout.splitlines() if f]
        assert len(files_calling_boto_directly) == 1, (
            f"boto3.client() se llama directo desde más de un archivo: {files_calling_boto_directly}"
        )
        assert files_calling_boto_directly[0].replace("\\", "/").endswith("app/email/ses_provider.py")


class TestProviderResolution:
    def test_default_provider_stays_resend_until_explicit_opt_in(self, monkeypatch, fake_provider):
        settings = get_settings()
        monkeypatch.setattr(settings, "email_enabled", True)
        monkeypatch.setattr(settings, "email_provider", "resend")
        monkeypatch.setattr(settings, "email_override_to", "")

        result = send_email_module.send_email(
            to="cliente@ejemplo.com", subject="s", html="h", from_address="f@f.com",
        )
        assert result["provider"] == "resend"

    def test_provider_flips_globally_with_the_flag(self, monkeypatch, fake_provider):
        """Este proyecto usa un flag global único (no por tienda/cliente
        como en el proyecto hermano) — decisión tomada porque es un solo
        negocio, no multi-tenant. Confirma que el flag efectivamente
        cambia el proveedor usado."""
        settings = get_settings()
        monkeypatch.setattr(settings, "email_enabled", True)
        monkeypatch.setattr(settings, "email_override_to", "")

        monkeypatch.setattr(settings, "email_provider", "ses")
        result = send_email_module.send_email(
            to="cliente@ejemplo.com", subject="s", html="h", from_address="f@f.com",
        )
        assert result["provider"] == "ses"

    @pytest.mark.skip(
        reason="No aplica: este proyecto es un solo negocio, no multi-tenant. "
        "El corte de proveedor es un flag global (email_provider), no por "
        "tienda/cliente como en el proyecto hermano de donde se adaptó esta "
        "plantilla — no existe el concepto de 'entidad migrada' por separado."
    )
    def test_migrated_entity_uses_ses_without_affecting_others(self):
        pass
