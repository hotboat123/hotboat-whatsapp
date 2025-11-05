"""
Script principal para ejecutar el sistema de automatizaciones
Ejecuta: python run_automations.py
"""
import asyncio
import signal
import sys
from pathlib import Path

from app.config import get_settings
from app.db.connection import init_db, close_db
from app.utils.logger import logger

from automations.notifications import NotificationManager
from automations.monitors.appointments_monitor import AppointmentsMonitor
from automations.monitors.stock_monitor import StockMonitor

import yaml


class AutomationSystem:
    """Sistema principal de automatizaciones"""
    
    def __init__(self):
        self.settings = get_settings()
        self.config = self._load_config()
        self.running = False
        self.monitors = []
        self.notification_manager = None
        
    def _load_config(self) -> dict:
        """Carga la configuración YAML"""
        config_path = Path("automations/config.yaml")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}
    
    async def initialize(self):
        """Inicializa el sistema"""
        logger.info("🚀 Iniciando HotBoat Automations...")
        
        # Inicializar conexión a base de datos
        await init_db()
        logger.info("✅ Conexión a base de datos establecida")
        
        # Inicializar sistema de notificaciones
        self.notification_manager = NotificationManager()
        await self.notification_manager.initialize()
        
        # Inicializar monitores
        await self._initialize_monitors()
        
        # Notificación de inicio
        if self.config.get("general", {}).get("startup_notification", True):
            await self.notification_manager.send(
                message="✅ Sistema de automatizaciones HotBoat iniciado correctamente",
                priority="medium"
            )
        
        logger.info(f"✅ Sistema inicializado con {len(self.monitors)} monitores activos")
    
    async def _initialize_monitors(self):
        """Inicializa los monitores configurados"""
        monitors_config = self.config.get("monitors", {})
        
        # Monitor de Appointments
        if monitors_config.get("appointments", {}).get("enabled", False):
            appointments_monitor = AppointmentsMonitor(
                config=monitors_config["appointments"],
                notification_manager=self.notification_manager
            )
            self.monitors.append(appointments_monitor)
            logger.info("📅 Monitor de Appointments activado")
        
        # Monitor de Stock
        if monitors_config.get("stock", {}).get("enabled", False):
            stock_monitor = StockMonitor(
                config=monitors_config["stock"],
                notification_manager=self.notification_manager
            )
            self.monitors.append(stock_monitor)
            logger.info("📦 Monitor de Stock activado")
        
        if not self.monitors:
            logger.warning("⚠️ No hay monitores habilitados. Edita automations/config.yaml")
    
    async def start(self):
        """Inicia el sistema de monitoreo"""
        self.running = True
        
        if not self.monitors:
            logger.error("❌ No hay monitores para ejecutar")
            return
        
        # Iniciar todos los monitores en paralelo
        tasks = [monitor.start() for monitor in self.monitors]
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("🛑 Deteniendo monitores...")
        except Exception as e:
            logger.error(f"❌ Error en el sistema: {e}", exc_info=True)
            await self.notification_manager.send(
                message=f"❌ Error crítico en el sistema: {e}",
                priority="critical"
            )
    
    async def stop(self):
        """Detiene el sistema de monitoreo"""
        logger.info("🛑 Deteniendo HotBoat Automations...")
        self.running = False
        
        # Detener todos los monitores
        for monitor in self.monitors:
            await monitor.stop()
        
        # Cerrar sistema de notificaciones
        if self.notification_manager:
            await self.notification_manager.close()
        
        # Cerrar conexión a base de datos
        await close_db()
        
        logger.info("✅ Sistema detenido correctamente")


async def main():
    """Función principal"""
    system = AutomationSystem()
    
    # Configurar manejo de señales para shutdown graceful
    loop = asyncio.get_event_loop()
    
    def signal_handler(sig):
        logger.info(f"⚠️ Señal recibida: {sig}")
        asyncio.create_task(system.stop())
    
    # Registrar señales
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
    
    try:
        await system.initialize()
        await system.start()
    except KeyboardInterrupt:
        logger.info("⚠️ Interrupción del usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
        return 1
    finally:
        await system.stop()
    
    return 0


if __name__ == "__main__":
    try:
        # En Windows, usar ProactorEventLoop
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Programa interrumpido por el usuario")
        sys.exit(0)

