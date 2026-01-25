#!/usr/bin/env python3
"""
Script para listar todas las imágenes de alojamientos disponibles
"""
from pathlib import Path
import os

ACCOMMODATION_DIR = Path(__file__).parent / "media" / "accommodations"


def list_images():
    """List all accommodation images"""
    print("📸 Imágenes de Alojamientos Disponibles")
    print(f"📁 Directorio: {ACCOMMODATION_DIR}\n")
    
    if not ACCOMMODATION_DIR.exists():
        print("❌ El directorio de alojamientos no existe")
        print(f"   Creándolo en: {ACCOMMODATION_DIR}")
        ACCOMMODATION_DIR.mkdir(parents=True, exist_ok=True)
        return
    
    images = []
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    
    for file in ACCOMMODATION_DIR.iterdir():
        if file.is_file() and file.suffix.lower() in valid_extensions:
            size_mb = file.stat().st_size / (1024 * 1024)
            images.append({
                'name': file.stem,
                'filename': file.name,
                'size': size_mb,
                'path': file
            })
    
    if not images:
        print("📭 No hay imágenes todavía")
        print("\n💡 Para agregar imágenes:")
        print("   python add_accommodation_image.py <nombre> <ruta_imagen>")
        return
    
    # Sort by name
    images.sort(key=lambda x: x['name'])
    
    print(f"Total: {len(images)} imagen(es)\n")
    print(f"{'Nombre':<35} {'Archivo':<30} {'Tamaño':>10}")
    print("-" * 80)
    
    total_size = 0
    for img in images:
        print(f"{img['name']:<35} {img['filename']:<30} {img['size']:>8.2f}MB")
        total_size += img['size']
    
    print("-" * 80)
    print(f"{'TOTAL':<35} {len(images)} archivo(s) {total_size:>18.2f}MB\n")
    
    # Show paths
    print("📂 Rutas completas:")
    for img in images:
        print(f"   {img['path']}")


if __name__ == "__main__":
    list_images()
