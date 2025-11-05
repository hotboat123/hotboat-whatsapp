"""
Script de prueba para verificar la configuración de automatizaciones
Ejecuta: python test_automations.py
"""
import asyncio
import sys

# Colores
class C:
    G = '\033[92m'  # Green
    R = '\033[91m'  # Red
    Y = '\033[93m'  # Yellow
    B = '\033[94m'  # Blue
    E = '\033[0m'   # End


async def test_automations():
    """Prueba la configuración"""
    print("\n" + "="*60)
    print("🔍 TEST DE CONFIGURACIÓN - AUTOMATIZACIONES")
    print("="*60 + "\n")
    
    all_ok = True
    
    # 1. Test imports
    print(f"{C.B}[1/5]{C.E} Verificando imports...")
    try:
        from app.config import get_settings
        from app.db.connection import init_db, close_db
        from automations.notifications import NotificationManager
        from automations.monitors.appointments_monitor import AppointmentsMonitor
        print(f"{C.G}✅ Imports OK{C.E}")
    except Exception as e:
        print(f"{C.R}❌ Error en imports: {e}{C.E}")
        return False
    
    # 2. Test config
    print(f"\n{C.B}[2/5]{C.E} Verificando configuración...")
    try:
        settings = get_settings()
        print(f"{C.G}✅ Configuración cargada{C.E}")
        
        # Verificar números
        if settings.automation_phone_numbers:
            numbers = [n.strip() for n in settings.automation_phone_numbers.split(',') if n.strip()]
            print(f"{C.G}✅ {len(numbers)} número(s) configurado(s){C.E}")
            for num in numbers:
                print(f"   📱 {num}")
        else:
            print(f"{C.Y}⚠️ No hay números configurados{C.E}")
            print(f"{C.Y}💡 Agrega AUTOMATION_PHONE_NUMBERS en .env{C.E}")
            all_ok = False
    except Exception as e:
        print(f"{C.R}❌ Error: {e}{C.E}")
        return False
    
    # 3. Test database
    print(f"\n{C.B}[3/5]{C.E} Probando conexión a base de datos...")
    try:
        await init_db()
        print(f"{C.G}✅ Conexión exitosa{C.E}")
        
        # Test query
        from automations.database import execute_query
        result = await execute_query("SELECT COUNT(*) as count FROM appointments;")
        count = result[0]['count'] if result else 0
        print(f"{C.G}✅ Tabla appointments existe ({count} registros){C.E}")
        
        await close_db()
    except Exception as e:
        print(f"{C.R}❌ Error: {e}{C.E}")
        all_ok = False
    
    # 4. Test notifications
    print(f"\n{C.B}[4/5]{C.E} Probando sistema de notificaciones...")
    try:
        manager = NotificationManager()
        await manager.initialize()
        print(f"{C.G}✅ Sistema de notificaciones OK{C.E}")
        
        if manager.phone_numbers:
            # Preguntar si enviar prueba
            print(f"\n{C.B}¿Quieres enviar un mensaje de prueba a tu WhatsApp? (s/n): {C.E}", end='')
            response = input().lower()
            
            if response == 's':
                print(f"{C.B}Enviando mensaje de prueba...{C.E}")
                await manager.send(
                    message="🧪 Mensaje de prueba del sistema de automatizaciones HotBoat",
                    priority="medium"
                )
                print(f"{C.G}✅ Mensaje enviado! Revisa tu WhatsApp{C.E}")
            else:
                print(f"{C.Y}⏭️ Omitiendo mensaje de prueba{C.E}")
        else:
            print(f"{C.Y}⚠️ No hay números configurados, omitiendo prueba de envío{C.E}")
        
        await manager.close()
    except Exception as e:
        print(f"{C.R}❌ Error: {e}{C.E}")
        all_ok = False
    
    # 5. Test monitors
    print(f"\n{C.B}[5/5]{C.E} Verificando monitores...")
    try:
        import yaml
        from pathlib import Path
        
        config_path = Path("automations/config.yaml")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        monitors_config = config.get("monitors", {})
        
        if monitors_config.get("appointments", {}).get("enabled"):
            print(f"{C.G}✅ Monitor de Appointments habilitado{C.E}")
        else:
            print(f"{C.Y}⚠️ Monitor de Appointments deshabilitado{C.E}")
        
        if monitors_config.get("stock", {}).get("enabled"):
            print(f"{C.G}✅ Monitor de Stock habilitado{C.E}")
        else:
            print(f"{C.Y}ℹ️ Monitor de Stock deshabilitado{C.E}")
    except Exception as e:
        print(f"{C.R}❌ Error: {e}{C.E}")
    
    # Resumen
    print("\n" + "="*60)
    if all_ok:
        print(f"{C.G}✨ ¡TODO LISTO!{C.E}")
        print(f"\n{C.B}Para ejecutar:{C.E}")
        print(f"  python run_automations.py")
    else:
        print(f"{C.Y}⚠️ Hay algunos problemas de configuración{C.E}")
        print(f"\n{C.B}Pasos siguientes:{C.E}")
        print(f"  1. Agrega AUTOMATION_PHONE_NUMBERS en .env")
        print(f"  2. Asegúrate de que la base de datos esté corriendo")
        print(f"  3. Ejecuta este test nuevamente")
    print("="*60 + "\n")
    
    return all_ok


if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        result = asyncio.run(test_automations())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print(f"\n\n{C.Y}Prueba cancelada{C.E}")
        sys.exit(1)
    except Exception as e:
        print(f"{C.R}Error inesperado: {e}{C.E}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

