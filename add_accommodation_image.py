#!/usr/bin/env python3
"""
Script para agregar imágenes de alojamientos de forma fácil
"""
import os
import sys
import shutil
from pathlib import Path

# Nombres válidos de alojamientos
VALID_ACCOMMODATIONS = {
    "open_sky_domo_bath": "Open Sky - Domo con Tina de Baño",
    "open_sky_domo_hydromassage": "Open Sky - Domo con Hidromasaje",
    "relikura_cabin_2": "Raíces de Relikura - Cabaña 2 personas",
    "relikura_cabin_4": "Raíces de Relikura - Cabaña 4 personas",
    "relikura_cabin_6": "Raíces de Relikura - Cabaña 6 personas",
    "relikura_hostel": "Raíces de Relikura - Hostal",
}

ACCOMMODATION_DIR = Path(__file__).parent / "media" / "accommodations"


def show_usage():
    """Show usage information"""
    print("📸 Agregar Imagen de Alojamiento")
    print("\nUso:")
    print("  python add_accommodation_image.py <nombre> <ruta_imagen>")
    print("\nNombres válidos:")
    for key, name in VALID_ACCOMMODATIONS.items():
        print(f"  • {key:30} → {name}")
    print("\nEjemplo:")
    print("  python add_accommodation_image.py open_sky_domo_bath ~/Downloads/domo.jpg")


def add_image(accommodation_name: str, image_path: str) -> bool:
    """
    Add an accommodation image
    
    Args:
        accommodation_name: Key name for the accommodation
        image_path: Path to the source image
    
    Returns:
        True if successful
    """
    # Validate accommodation name
    if accommodation_name not in VALID_ACCOMMODATIONS:
        print(f"❌ Nombre inválido: {accommodation_name}")
        print(f"\n✅ Nombres válidos:")
        for key in VALID_ACCOMMODATIONS.keys():
            print(f"   • {key}")
        return False
    
    # Validate image exists
    source_path = Path(image_path)
    if not source_path.exists():
        print(f"❌ No se encontró la imagen: {image_path}")
        return False
    
    # Validate image format
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    if source_path.suffix.lower() not in valid_extensions:
        print(f"❌ Formato no válido: {source_path.suffix}")
        print(f"✅ Formatos válidos: {', '.join(valid_extensions)}")
        return False
    
    # Check file size (warn if > 5MB)
    file_size_mb = source_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 5:
        print(f"⚠️  Advertencia: La imagen es muy grande ({file_size_mb:.1f}MB)")
        print(f"   WhatsApp recomienda imágenes menores a 5MB")
        response = input("   ¿Continuar de todas formas? (s/n): ")
        if response.lower() != 's':
            return False
    
    # Create destination path
    ACCOMMODATION_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = ACCOMMODATION_DIR / f"{accommodation_name}{source_path.suffix.lower()}"
    
    # Copy image
    try:
        shutil.copy2(source_path, dest_path)
        print(f"✅ Imagen agregada exitosamente!")
        print(f"   Nombre: {VALID_ACCOMMODATIONS[accommodation_name]}")
        print(f"   Archivo: {dest_path.name}")
        print(f"   Tamaño: {file_size_mb:.2f}MB")
        print(f"   Ruta: {dest_path}")
        return True
    except Exception as e:
        print(f"❌ Error al copiar imagen: {e}")
        return False


def main():
    if len(sys.argv) != 3:
        show_usage()
        sys.exit(1)
    
    accommodation_name = sys.argv[1]
    image_path = sys.argv[2]
    
    success = add_image(accommodation_name, image_path)
    
    if success:
        print("\n🎉 ¡Listo! Ahora puedes:")
        print("   1. Verificar con: python check_accommodation_images.py")
        print("   2. Probar enviando: python test_accommodations_whatsapp.py <numero>")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
