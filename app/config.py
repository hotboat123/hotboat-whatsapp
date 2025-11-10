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
    
    # Server
    port: int = 8000
    host: str = "0.0.0.0"
    environment: str = "development"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()







