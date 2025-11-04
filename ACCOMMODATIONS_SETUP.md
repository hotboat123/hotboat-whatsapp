# 🏨 Configuración de Alojamientos con Imágenes

## 📋 Resumen

El sistema ahora soporta enviar información de alojamientos con imágenes en WhatsApp. Cuando un usuario pregunta por alojamientos, recibe:
- Un mensaje de texto con información general
- Imágenes de cada opción de alojamiento con descripción y precio

## 🖼️ Dónde alojar las imágenes

**📖 Ver guía completa:** `GUIA_ALOJAMIENTO_IMAGENES.md`

### Recomendación: **Hostinger** (si ya lo tienes) o **Cloudinary** (alternativa gratis)

Las imágenes deben estar disponibles públicamente vía HTTPS. Opciones recomendadas:

### 1. **Hostinger** ⭐ (Recomendado si ya lo tienes)
- **Costo: $0 adicional** (ya pagas el hosting)
- Sube las imágenes vía File Manager o FTP
- URL: `https://tudominio.com/images/accommodations/nombre.jpg`
- Ver guía completa en `GUIA_ALOJAMIENTO_IMAGENES.md`

### 2. **Cloudinary** (Alternativa gratis)
- URL: https://cloudinary.com
- Gratis hasta 25GB de almacenamiento
- CDN rápido y optimización automática
- Fácil de usar (drag & drop)

### 3. **AWS S3 + CloudFront** (Profesional)
- Escalable y confiable
- Requiere configuración de AWS
- Costo según uso

## 📝 Cómo agregar las URLs de imágenes

1. Edita el archivo `app/config/accommodations_config.py`

2. Reemplaza las URLs de ejemplo con las URLs reales de tus imágenes:

```python
ACCOMMODATION_IMAGES = {
    "open_sky_domo_bath": "https://tu-cdn.com/images/open-sky-domo-bath.jpg",
    "open_sky_domo_hydromassage": "https://tu-cdn.com/images/open-sky-domo-hydromassage.jpg",
    "relikura_cabin_2": "https://tu-cdn.com/images/relikura-cabin-2.jpg",
    "relikura_cabin_4": "https://tu-cdn.com/images/relikura-cabin-4.jpg",
    "relikura_cabin_6": "https://tu-cdn.com/images/relikura-cabin-6.jpg",
    "relikura_hostel": "https://tu-cdn.com/images/relikura-hostel.jpg",
}
```

## ✅ Requisitos de las imágenes

- **Formato**: JPG, PNG o WebP
- **Tamaño máximo**: 5MB (límite de WhatsApp)
- **Resolución recomendada**: 800x600px o 1200x900px (buena calidad sin ser demasiado pesado)
- **Acceso**: Deben ser accesibles públicamente sin autenticación
- **HTTPS**: Deben estar servidas vía HTTPS (requisito de WhatsApp)

## 🔍 Cómo probar

1. Asegúrate de que todas las URLs en `accommodations_config.py` apunten a imágenes reales
2. Reinicia el servidor
3. Envía un mensaje a WhatsApp con: "alojamientos", "hotel", "cabañas", etc.
4. Deberías recibir:
   - Un mensaje de texto introductorio
   - Imágenes de cada opción con descripción y precio

## 🎨 Recomendaciones de diseño

Para mejores resultados en WhatsApp:
- Usa imágenes de alta calidad pero optimizadas (no más de 500KB)
- Asegúrate de que las imágenes muestren bien el alojamiento
- Considera agregar texto/watermark con el nombre del alojamiento en la imagen misma
- Mantén un estilo consistente entre todas las imágenes

## 🚨 Si no hay URL configurada

Si una imagen no tiene URL configurada (o está como `None`), el sistema enviará solo el texto descriptivo sin la imagen. Esto permite que el sistema funcione incluso si no todas las imágenes están listas.

## 📸 Ejemplo de estructura de carpetas (si usas Cloudinary)

```
accommodations/
├── open-sky/
│   ├── domo-bath.jpg
│   └── domo-hydromassage.jpg
└── relikura/
    ├── cabin-2.jpg
    ├── cabin-4.jpg
    ├── cabin-6.jpg
    └── hostel.jpg
```

## 💡 Tips adicionales

- **Optimización**: Usa herramientas como TinyPNG o ImageOptim para reducir el tamaño
- **CDN**: Un CDN hará que las imágenes se carguen más rápido
- **Backup**: Mantén copias de las imágenes en caso de que el servicio falle
- **Testing**: Prueba las URLs antes de agregarlas para asegurarte de que funcionan

