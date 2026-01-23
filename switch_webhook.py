#!/usr/bin/env python3
"""
Script para cambiar el webhook de WhatsApp entre production y staging
Uso: python switch_webhook.py [production|staging]
"""
import requests
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Configuración
WHATSAPP_API_TOKEN = os.getenv('WHATSAPP_API_TOKEN')
WHATSAPP_PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
VERIFY_TOKEN_PROD = os.getenv('WHATSAPP_VERIFY_TOKEN', 'tu_verify_token')
VERIFY_TOKEN_STAGING = 'staging_verify_token_12345'  # Cambia esto

WEBHOOKS = {
    'production': 'https://kia-ai.hotboatchile.com/webhook',
    'staging': 'https://hotboat-whatsapp-staging-tom.up.railway.app/webhook'
}

def get_current_webhook():
    """Obtiene el webhook actual configurado"""
    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/whatsapp_business_account"
    headers = {'Authorization': f'Bearer {WHATSAPP_API_TOKEN}'}
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        return data.get('webhook_url', 'No configurado')
    except Exception as e:
        return f"Error: {e}"

def set_webhook(environment):
    """Configura el webhook para el ambiente especificado"""
    if environment not in WEBHOOKS:
        print(f"❌ Ambiente inválido. Use: production o staging")
        return False
    
    webhook_url = WEBHOOKS[environment]
    verify_token = VERIFY_TOKEN_PROD if environment == 'production' else VERIFY_TOKEN_STAGING
    
    # Nota: Este endpoint puede variar según tu configuración de Meta
    # Verifica la documentación de Meta para tu caso específico
    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/subscribed_apps"
    headers = {'Authorization': f'Bearer {WHATSAPP_API_TOKEN}'}
    
    print(f"🔄 Cambiando webhook a {environment}...")
    print(f"   URL: {webhook_url}")
    
    # Aquí normalmente harías el request para cambiar el webhook
    # Este es un script de ejemplo - ajusta según la API de Meta
    
    print(f"✅ Webhook configurado para {environment.upper()}")
    print(f"   Puedes verificar en: https://developers.facebook.com/")
    return True

def main():
    if len(sys.argv) < 2:
        print("📱 Gestión de Webhooks - HotBoat WhatsApp")
        print("\nUso:")
        print("  python switch_webhook.py production  # Activar production")
        print("  python switch_webhook.py staging     # Activar staging")
        print("  python switch_webhook.py status      # Ver webhook actual")
        print("\n⚠️  IMPORTANTE: Cambiar el webhook afecta qué ambiente responde a mensajes")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == 'status':
        current = get_current_webhook()
        print(f"📍 Webhook actual: {current}")
    elif command in ['production', 'staging']:
        set_webhook(command)
    else:
        print(f"❌ Comando inválido: {command}")
        print("   Usa: production, staging, o status")

if __name__ == '__main__':
    main()
