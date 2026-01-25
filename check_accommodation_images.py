#!/usr/bin/env python3
"""
Script para verificar que todas las imágenes de alojamientos estén disponibles
"""
import os
from pathlib import Path
from app.utils.media_handler import ACCOMMODATION_DIR, list_accommodation_images

# Alojamientos requeridos
REQUIRED_ACCOMMODATIONS = {
    "open_sky_domo_bath": "Open Sky - Domo con Tina de Baño",
    "open_sky_domo_hydromassage": "Open Sky - Domo con Hidromasaje",
    "relikura_cabin_2": "Raíces de Relikura - Cabaña 2 personas",
    "relikura_cabin_4": "Raíces de Relikura - Cabaña 4 personas",
    "relikura_cabin_6": "Raíces de Relikura - Cabaña 6 personas",
    "relikura_hostel": "Raíces de Relikura - Hostal",
}


def check_images():
    """Check if all required accommodation images exist"""
    print("🏠 Verificando imágenes de alojamientos...")
    print(f"📁 Directorio: {ACCOMMODATION_DIR}\n")
    
    available_images = list_accommodation_images()
    
    all_ok = True
    missing = []
    found = []
    
    for key, name in REQUIRED_ACCOMMODATIONS.items():
        if key in available_images:
            path = available_images[key]
            file_size = os.path.getsize(path) / (1024 * 1024)  # MB
            print(f"✅ {key:30} → {os.path.basename(path):30} ({file_size:.2f}MB)")
            found.append(key)
        else:
            print(f"❌ {key:30} → NO ENCONTRADA")
            missing.append((key, name))
            all_ok = False
    
    print("\n" + "="*70)
    
    if all_ok:
        print(f"\n🎉 ¡Perfecto! Todas las {len(REQUIRED_ACCOMMODATIONS)} imágenes están disponibles")
        print("\n✅ El bot puede enviar alojamientos con imágenes por WhatsApp")
    else:
        print(f"\n⚠️  Faltan {len(missing)} imagen(es):")
        for key, name in missing:
            print(f"   • {key} ({name})")
        
        print("\n📝 Para agregar imágenes faltantes:")
        print("   python add_accommodation_image.py <nombre> <ruta_imagen>")
        print("\n   Ejemplo:")
        if missing:
            print(f"   python add_accommodation_image.py {missing[0][0]} ~/Downloads/imagen.jpg")
    
    # Show extra images
    extra_images = set(available_images.keys()) - set(REQUIRED_ACCOMMODATIONS.keys())
    if extra_images:
        print(f"\n📦 Imágenes adicionales encontradas ({len(extra_images)}):")
        for key in extra_images:
            print(f"   • {key}")
    
    return all_ok


if __name__ == "__main__":
    import sys
    success = check_images()
    sys.exit(0 if success else 1)
