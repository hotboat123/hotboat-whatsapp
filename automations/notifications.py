"""
Sistema de Notificaciones - Usa WhatsApp Business API del proyecto
"""
from typing import List
from app.whatsapp.client import whatsapp_client
from app.config import get_settings
from app.utils.logger import logger
import yaml
from pathlib import Path


class NotificationManager:
    """Gestiona las notificaciones por WhatsApp"""
    
    def __init__(self):
        self.settings = get_settings()
        self.config = self._load_config()
        self.phone_numbers = self._get_phone_numbers()
        
        if not self.phone_numbers:
            logger.warning("⚠️ No hay números de teléfono configurados para notificaciones")
            logger.info("💡 Agrega AUTOMATION_PHONE_NUMBERS en .env")
    
    def _load_config(self) -> dict:
        """Carga la configuración YAML"""
        config_path = Path(__file__).parent / "config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def _get_phone_numbers(self) -> List[str]:
        """Obtiene los números de teléfono desde las variables de entorno"""
        # Intenta obtener de la variable de entorno AUTOMATION_PHONE_NUMBERS
        phone_numbers_str = getattr(self.settings, 'automation_phone_numbers', '')
        
        if phone_numbers_str:
            # Formato: 56912345678,56987654321 (separados por coma, sin + ni espacios)
            return [num.strip() for num in phone_numbers_str.split(',') if num.strip()]
        
        return []
    
    async def initialize(self):
        """Inicializa el sistema de notificaciones"""
        logger.info("📱 Sistema de notificaciones WhatsApp inicializado")
        if self.phone_numbers:
            logger.info(f"📞 Enviando a {len(self.phone_numbers)} número(s)")
    
    async def send(self, message: str, priority: str = "medium"):
        """
        Envía una notificación por WhatsApp
        
        Args:
            message: Mensaje a enviar
            priority: Prioridad (critical, high, medium, low)
        """
        if not self.phone_numbers:
            logger.warning(f"⚠️ No hay destinatarios configurados para: {message[:50]}...")
            return
        
        # Verificar si se debe enviar según prioridad
        if not self._should_send(priority):
            logger.debug(f"Notificación de prioridad '{priority}' omitida según config")
            return
        
        # Agregar emoji según prioridad
        emoji_map = {
            "critical": "🚨",
            "high": "⚠️",
            "medium": "ℹ️",
            "low": "💬"
        }
        
        emoji = emoji_map.get(priority, "ℹ️")
        formatted_message = f"{emoji} {message}"
        
        # Enviar a todos los números configurados
        for phone_number in self.phone_numbers:
            try:
                await whatsapp_client.send_text_message(
                    to=phone_number,
                    message=formatted_message
                )
                logger.debug(f"📱 Notificación enviada a {phone_number}")
            except Exception as e:
                logger.error(f"❌ Error al enviar notificación a {phone_number}: {e}")
    
    def _should_send(self, priority: str) -> bool:
        """Verifica si se debe enviar la notificación según la prioridad"""
        priority_levels = self.config.get("notifications", {}).get("whatsapp", {}).get("priority_levels", {
            "critical": True,
            "high": True,
            "medium": True,
            "low": False
        })
        
        return priority_levels.get(priority, True)
    
    async def close(self):
        """Cierra el sistema de notificaciones"""
        logger.info("🔌 Sistema de notificaciones cerrado")

