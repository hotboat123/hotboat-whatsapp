# 📸 Guía de Uso del Sistema de Imágenes

## Descripción General

El sistema de imágenes ahora está completamente funcional y permite:
- ✅ **Recibir imágenes** de usuarios y guardarlas localmente
- ✅ **Enviar imágenes** usando la WhatsApp Media Upload API
- ✅ **No requiere URLs públicas** - las imágenes se suben directamente a WhatsApp
- ✅ **Fallback automático** a URLs si están disponibles

## 📁 Estructura de Carpetas

El sistema crea automáticamente estas carpetas:

```
media/
├── received/          # Imágenes recibidas de usuarios
├── uploaded/          # Imágenes que has subido
└── accommodations/    # Imágenes de alojamientos
```

## 🖼️ Cómo Agregar Imágenes de Alojamientos

### Opción 1: Agregar archivos localmente (Recomendado)

1. Coloca tus imágenes en la carpeta `media/accommodations/`
2. Nombra los archivos exactamente así:
   - `open_sky_domo_bath.jpg` (o .png, .jpeg, .webp)
   - `open_sky_domo_hydromassage.jpg`
   - `relikura_cabin_2.jpg`
   - `relikura_cabin_4.jpg`
   - `relikura_cabin_6.jpg`
   - `relikura_hostel.jpg`

3. ¡Listo! El sistema las detectará automáticamente.

### Opción 2: Usar URLs públicas (Fallback)

Si prefieres usar URLs, edita el archivo `app/config/accommodations_config.py`:

```python
ACCOMMODATION_IMAGES = {
    "open_sky_domo_bath": "https://tu-servidor.com/imagen1.jpg",
    "open_sky_domo_hydromassage": "https://tu-servidor.com/imagen2.jpg",
    # ... etc
}
```

**Nota:** El sistema intentará primero usar archivos locales, y si no existen, usará las URLs.

## 🔄 Recibir Imágenes

Cuando un usuario envía una imagen:
1. Se descarga automáticamente
2. Se guarda en `media/received/` con el formato: `{media_id}_{timestamp}.jpg`
3. Se procesa el caption como mensaje de texto
4. El bot responde normalmente

## 📤 Enviar Imágenes Programáticamente

### Desde un archivo local:

```python
from app.whatsapp.client import whatsapp_client

# Subir imagen a WhatsApp
media_id = await whatsapp_client.upload_media("path/to/image.jpg")

# Enviar imagen con caption
await whatsapp_client.send_image_message(
    to="56912345678",
    media_id=media_id,
    caption="¡Mira esta imagen!"
)
```

### Desde una URL:

```python
await whatsapp_client.send_image_message(
    to="56912345678",
    image_url="https://ejemplo.com/imagen.jpg",
    caption="¡Mira esta imagen!"
)
```

## 🛠️ Funciones Útiles del Media Handler

```python
from app.utils.media_handler import (
    get_accommodation_image_path,
    list_accommodation_images,
    save_accommodation_image
)

# Ver qué imágenes de alojamientos están disponibles
images = list_accommodation_images()
# Returns: {'open_sky_domo_bath': '/path/to/file.jpg', ...}

# Obtener path de una imagen específica
path = get_accommodation_image_path("open_sky_domo_bath")
# Returns: '/path/to/open_sky_domo_bath.jpg' or None

# Guardar una nueva imagen de alojamiento
save_accommodation_image("open_sky_domo_bath", "source/image.jpg")
```

## 🔍 Solución de Problemas

### Las imágenes no se envían

1. **Verifica que los archivos existan:**
   ```python
   from app.utils.media_handler import list_accommodation_images
   print(list_accommodation_images())
   ```

2. **Revisa los logs** para ver errores de upload:
   ```
   ✅ Media uploaded successfully: xyz123
   ✅ Image sent successfully using media_id
   ```

3. **Verifica permisos** del token de WhatsApp:
   - Debe tener permisos para `whatsapp_business_messaging`
   - Debe tener acceso a la API de Media

### Las imágenes recibidas no se guardan

1. Verifica que la carpeta `media/received/` exista y tenga permisos de escritura
2. Revisa los logs para ver si hay errores de descarga

## 📝 Formatos de Imagen Soportados

- JPEG (.jpg, .jpeg)
- PNG (.png)
- WebP (.webp)

**Tamaño máximo:** 5 MB por imagen (límite de WhatsApp)

## 🚀 Ventajas del Nuevo Sistema

✅ **No necesitas servidor web público** para las imágenes
✅ **Más rápido** - las imágenes se suben directamente a WhatsApp
✅ **Más confiable** - no depende de URLs externas
✅ **Fallback automático** - si falla una opción, intenta otra
✅ **Guarda imágenes recibidas** - útil para análisis posterior

## 🔒 Seguridad

- Las imágenes se guardan localmente en el servidor
- Las imágenes recibidas están disponibles solo en el servidor
- Los media_id de WhatsApp expiran después de 30 días
- Considera implementar limpieza automática de imágenes antiguas

## 📦 Dependencias

El sistema usa las bibliotecas ya instaladas:
- `httpx` - Para hacer requests HTTP async
- `os` - Para manejo de archivos
- Standard library de Python

No se requieren dependencias adicionales.
