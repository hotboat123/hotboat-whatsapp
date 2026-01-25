#!/usr/bin/env python3
"""
Script para probar el envío de alojamientos con imágenes por WhatsApp
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.whatsapp.client import whatsapp_client
from app.bot.accommodations import accommodations_handler


async def test_send_accommodations(phone_number: str):
    """
    Send accommodation information with images to a phone number
    
    Args:
        phone_number: WhatsApp phone number (with country code, no +)
    """
    print(f"📤 Enviando información de alojamientos a {phone_number}...")
    print(f"🔄 Cargando imágenes...\n")
    
    # Get accommodations with images
    items = accommodations_handler.get_accommodations_with_images()
    
    print(f"📦 Total de items a enviar: {len(items)}")
    print(f"   • Textos: {sum(1 for i in items if i['type'] == 'text')}")
    print(f"   • Imágenes: {sum(1 for i in items if i['type'] == 'image')}")
    print()
    
    sent_count = 0
    failed_count = 0
    
    for idx, item in enumerate(items, 1):
        if item['type'] == 'text':
            # Send text message
            try:
                await whatsapp_client.send_message(phone_number, item['content'])
                print(f"✅ [{idx}/{len(items)}] Texto enviado")
                sent_count += 1
                await asyncio.sleep(0.5)  # Small delay between messages
            except Exception as e:
                print(f"❌ [{idx}/{len(items)}] Error enviando texto: {e}")
                failed_count += 1
        
        elif item['type'] == 'image':
            # Send image with caption
            image_path = item.get('image_path')
            image_url = item.get('image_url')
            caption = item.get('caption', '')
            
            if not image_path and not image_url:
                print(f"⚠️  [{idx}/{len(items)}] Sin imagen disponible, enviando solo caption")
                try:
                    await whatsapp_client.send_message(phone_number, caption)
                    sent_count += 1
                except Exception as e:
                    print(f"❌ Error: {e}")
                    failed_count += 1
                continue
            
            # Try to upload and send
            try:
                if image_path and os.path.exists(image_path):
                    # Upload local file
                    print(f"📤 [{idx}/{len(items)}] Subiendo imagen local: {os.path.basename(image_path)}")
                    media_id = await whatsapp_client.upload_media(image_path)
                    
                    # Send with media ID
                    await whatsapp_client.send_image_message(
                        to=phone_number,
                        caption=caption,
                        media_id=media_id
                    )
                    print(f"✅ [{idx}/{len(items)}] Imagen enviada con éxito")
                    sent_count += 1
                else:
                    print(f"❌ [{idx}/{len(items)}] Imagen no encontrada: {image_path}")
                    failed_count += 1
                
                await asyncio.sleep(1)  # Delay between images
                
            except Exception as e:
                print(f"❌ [{idx}/{len(items)}] Error enviando imagen: {e}")
                failed_count += 1
    
    print("\n" + "="*60)
    print(f"📊 Resumen:")
    print(f"   ✅ Enviados: {sent_count}")
    print(f"   ❌ Fallidos: {failed_count}")
    print(f"   📦 Total: {len(items)}")
    
    if failed_count == 0:
        print(f"\n🎉 ¡Todos los mensajes se enviaron correctamente!")
    else:
        print(f"\n⚠️  Algunos mensajes fallaron. Revisa los errores arriba.")


def main():
    if len(sys.argv) != 2:
        print("📱 Probar Envío de Alojamientos por WhatsApp")
        print("\nUso:")
        print("  python test_accommodations_whatsapp.py <numero>")
        print("\nEjemplo:")
        print("  python test_accommodations_whatsapp.py 56912345678")
        print("\nNota: El número debe incluir el código de país sin el '+'")
        sys.exit(1)
    
    phone_number = sys.argv[1]
    
    # Validate phone number format
    if not phone_number.isdigit() or len(phone_number) < 10:
        print("❌ Número de teléfono inválido")
        print("   Debe incluir código de país y solo dígitos")
        print("   Ejemplo: 56912345678 (Chile)")
        sys.exit(1)
    
    print("🚀 Iniciando prueba de envío...")
    print(f"📱 Número destino: +{phone_number}\n")
    
    # Run async function
    asyncio.run(test_send_accommodations(phone_number))


if __name__ == "__main__":
    main()
