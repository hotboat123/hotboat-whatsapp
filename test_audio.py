"""
Script de prueba para la funcionalidad de audio en WhatsApp
"""
import asyncio
import logging
import os
from app.whatsapp.client import WhatsAppClient
from app.config import get_settings

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_send_audio():
    """Probar envío de audio"""
    settings = get_settings()
    client = WhatsAppClient()
    
    # Número de prueba (reemplaza con tu número)
    test_phone = "56974950762"  # Número del Capitán Tomás
    
    print("\n" + "="*60)
    print("🎤 PRUEBA DE ENVÍO DE AUDIO")
    print("="*60)
    
    # Verificar que existe un archivo de audio de prueba
    test_audio_path = "media/audio/test.ogg"
    
    if not os.path.exists(test_audio_path):
        print(f"\n⚠️  No existe el archivo de prueba: {test_audio_path}")
        print("Creando directorio media/audio/...")
        os.makedirs("media/audio", exist_ok=True)
        print("\n📝 Para probar el envío de audio:")
        print(f"   1. Coloca un archivo de audio en: {test_audio_path}")
        print(f"   2. Ejecuta este script nuevamente")
        print("\n💡 Puedes usar cualquier formato: .ogg, .mp3, .m4a, .wav")
        return
    
    print(f"\n✅ Archivo de prueba encontrado: {test_audio_path}")
    print(f"📱 Enviando audio a: {test_phone}")
    
    try:
        # Método 1: Subir archivo local
        print("\n🔄 Subiendo audio a WhatsApp...")
        media_id = await client.upload_media(test_audio_path, "audio/ogg")
        
        if media_id:
            print(f"✅ Audio subido exitosamente. Media ID: {media_id}")
            
            print("\n📤 Enviando mensaje de audio...")
            result = await client.send_audio_message(
                to=test_phone,
                media_id=media_id
            )
            
            print(f"✅ Audio enviado exitosamente!")
            print(f"📊 Respuesta de WhatsApp: {result}")
        else:
            print("❌ Error subiendo el audio")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)


async def test_send_audio_from_url():
    """Probar envío de audio desde URL"""
    client = WhatsAppClient()
    
    # Número de prueba
    test_phone = "56974950762"
    
    # URL de audio de prueba (debe ser pública y accesible)
    test_audio_url = "https://example.com/test-audio.ogg"
    
    print("\n" + "="*60)
    print("🌐 PRUEBA DE ENVÍO DE AUDIO DESDE URL")
    print("="*60)
    print(f"\n📱 Enviando audio a: {test_phone}")
    print(f"🔗 URL: {test_audio_url}")
    
    try:
        result = await client.send_audio_message(
            to=test_phone,
            audio_url=test_audio_url
        )
        print(f"\n✅ Audio enviado exitosamente!")
        print(f"📊 Respuesta de WhatsApp: {result}")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Asegúrate de que:")
        print("   - La URL es pública y accesible")
        print("   - El archivo es un formato de audio válido")
        print("   - El servidor permite acceso desde WhatsApp")
    
    print("\n" + "="*60)


async def list_received_audios():
    """Listar audios recibidos"""
    from app.utils.media_handler import list_audio_files
    
    print("\n" + "="*60)
    print("📂 AUDIOS RECIBIDOS")
    print("="*60)
    
    audio_files = list_audio_files()
    
    if not audio_files:
        print("\n📭 No hay audios recibidos todavía")
        print("\n💡 Los audios recibidos se guardarán en: media/audio/")
    else:
        print(f"\n✅ Se encontraron {len(audio_files)} archivo(s) de audio:")
        for i, audio_path in enumerate(audio_files, 1):
            file_size = os.path.getsize(audio_path) / 1024  # KB
            print(f"\n{i}. {os.path.basename(audio_path)}")
            print(f"   📏 Tamaño: {file_size:.2f} KB")
            print(f"   📍 Ruta: {audio_path}")
    
    print("\n" + "="*60)


async def main():
    """Menú principal"""
    print("\n" + "="*60)
    print("🎤 PRUEBA DE FUNCIONALIDAD DE AUDIO - HOTBOAT WHATSAPP BOT")
    print("="*60)
    print("\nOpciones:")
    print("1. 📤 Enviar audio desde archivo local")
    print("2. 🌐 Enviar audio desde URL")
    print("3. 📂 Listar audios recibidos")
    print("4. 🔄 Ejecutar todas las pruebas")
    print("5. ❌ Salir")
    
    choice = input("\n👉 Elige una opción (1-5): ").strip()
    
    if choice == "1":
        await test_send_audio()
    elif choice == "2":
        await test_send_audio_from_url()
    elif choice == "3":
        await list_received_audios()
    elif choice == "4":
        await list_received_audios()
        await test_send_audio()
    elif choice == "5":
        print("\n👋 ¡Hasta luego!")
        return
    else:
        print("\n⚠️  Opción no válida")
    
    # Preguntar si quiere continuar
    continue_choice = input("\n¿Ejecutar otra prueba? (s/n): ").strip().lower()
    if continue_choice == "s":
        await main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Prueba cancelada por el usuario")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
