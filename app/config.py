"""
Configuration management using Pydantic Settings
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""
    
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
    
    # Automations
    automation_phone_numbers: str = ""  # Comma-separated phone numbers for automation notifications
    
    # Email notifications (using Resend API - works on Railway)
    email_enabled: bool = False
    resend_api_key: str = ""
    email_from: str = "onboarding@resend.dev"  # Change to your verified domain
    notification_emails: str = ""  # Comma-separated list of emails to notify
    
    # SMTP Email Configuration (alternative to Resend)
    email_host: str = ""
    email_port: str = ""
    email_username: str = ""
    email_password: str = ""
    email_use_tls: str = ""
    email_use_ssl: str = ""
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()








