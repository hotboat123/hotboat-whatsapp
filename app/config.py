"""
Configuration management using Pydantic Settings
"""
import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )
    
    # Database
    database_url: str
    
    # WhatsApp
    whatsapp_api_token: str
    whatsapp_phone_number_id: str
    whatsapp_business_account_id: str
    whatsapp_verify_token: str
    
    # AI (Groq - FREE!)
    groq_api_key: str
    
    # Bot
    bot_name: str = "Capitan HotBoat"
    business_name: str = "Hot Boat"
    business_phone: str = "+56 9 75780920"
    business_email: str = "info@hotboatchile.com"
    business_website: str = "https://hotboatchile.com/es/"
    # Meta Pixel (optional). Injected on /pagar for PageView + InitiateCheckout.
    meta_pixel_id: str = ""
    # Meta Marketing API token for ad name lookup (optional — falls back to whatsapp_api_token)
    meta_marketing_token: str = ""
    # Facebook Page ID linked to the WhatsApp Business Account (required for Conversions API)
    meta_page_id: str = ""
    
    # Automations
    automation_phone_numbers: str = ""  # Comma-separated phone numbers for automation notifications
    
    # Email notifications (using Resend API - works on Railway)
    email_enabled: bool = False
    resend_api_key: str = ""
    email_from: str = "onboarding@resend.dev"  # Change to your verified domain
    # Booking confirmations (e.g. Reservas HotBoat <noreply@reservas.hotboat.cl>)
    resend_from_confirmations: str = ""
    # Optional BCC for every transactional booking email (comma-separated)
    resend_bcc_booking: str = ""
    notification_emails: str = ""  # Comma-separated list of emails to notify
    # Direct URL of the logo image used in booking emails (must be publicly accessible)
    email_logo_url: str = ""
    
    # SMTP Email Configuration (alternative to Resend)
    email_host: str = ""
    email_port: str = ""
    email_username: str = ""
    email_password: str = ""
    email_use_tls: str = ""
    email_use_ssl: str = ""

    # Web Push (PWA notifications) — generate with: openssl ecparam -name prime256v1 -genkey
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    
    # Server
    port: int = 8000
    host: str = "0.0.0.0"
    environment: str = "production"  # Options: production, staging, development
    log_level: str = "INFO"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment.lower() == "production"
    
    @property
    def is_staging(self) -> bool:
        """Check if running in staging/beta"""
        return self.environment.lower() in ["staging", "beta"]
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment.lower() == "development"

    @model_validator(mode="after")
    def resolve_meta_pixel_id_from_aliases(self):
        """Railway/UI may use another env name or paste IDs with invisible characters."""
        from app.meta_pixel import is_meta_pixel_enabled

        if is_meta_pixel_enabled(self.meta_pixel_id):
            return self
        for key in ("META_PIXEL_ID", "FACEBOOK_PIXEL_ID", "FB_PIXEL_ID"):
            raw = os.environ.get(key)
            if raw is None:
                continue
            if is_meta_pixel_enabled(raw):
                object.__setattr__(self, "meta_pixel_id", str(raw).strip())
                break
        return self


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()








