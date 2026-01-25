# 🏠 Guía de Imágenes de Alojamientos para WhatsApp

Esta guía te ayudará a agregar y gestionar imágenes de alojamientos que el bot enviará automáticamente por WhatsApp.

## 📁 Estructura de Carpetas

```
media/
└── accommodations/
    ├── open_sky_domo_bath.jpg
    ├── open_sky_domo_hydromassage.jpg
    ├── relikura_cabin_2.jpg
    ├── relikura_cabin_4.jpg
    ├── relikura_cabin_6.jpg
    └── relikura_hostel.jpg
```

## 🎯 Alojamientos Disponibles

### 1. Open Sky (Parejas Románticas)

**Archivos esperados:**
- `open_sky_domo_bath.jpg` - Domo con tina de baño ($100.000/noche)
- `open_sky_domo_hydromassage.jpg` - Domo con hidromasaje ($120.000/noche)

**Qué fotografiar:**
- ✅ Vista interior del domo transparente
- ✅ La tina de baño o hidromasaje destacado
- ✅ Vista nocturna con estrellas si es posible
- ✅ Ambiente romántico e íntimo

### 2. Raíces de Relikura (Familiar)

**Archivos esperados:**
- `relikura_cabin_2.jpg` - Cabaña para 2 personas ($60.000/noche)
- `relikura_cabin_4.jpg` - Cabaña para 4 personas ($80.000/noche)
- `relikura_cabin_6.jpg` - Cabaña para 6 personas ($100.000/noche)
- `relikura_hostel.jpg` - Hostal económico ($20.000/noche por persona)

**Qué fotografiar:**
- ✅ Vista exterior de cada cabaña/hostal
- ✅ La tinaja exterior visible
- ✅ El entorno natural (río, árboles)
- ✅ Interior cómodo y familiar

---

## 🚀 Cómo Agregar Imágenes

### Método 1: Manual (Copiar y Pegar)

1. **Prepara tus imágenes:**
   - Formato: JPG, JPEG, PNG o WEBP
   - Tamaño recomendado: Máximo 5MB cada una
   - Resolución: Al menos 1080px de ancho

2. **Renombra los archivos** exactamente como se indica arriba:
   ```
   open_sky_domo_bath.jpg
   open_sky_domo_hydromassage.jpg
   relikura_cabin_2.jpg
   relikura_cabin_4.jpg
   relikura_cabin_6.jpg
   relikura_hostel.jpg
   ```

3. **Copia los archivos** a la carpeta:
   ```
   media/accommodations/
   ```

4. **¡Listo!** El bot las detectará automáticamente.

---

### Método 2: Script Automático (Recomendado)

Usa el script para agregar imágenes de forma más fácil:

```bash
# Agregar una imagen
python add_accommodation_image.py open_sky_domo_bath ruta/a/tu/imagen.jpg

# Ver todas las imágenes disponibles
python list_accommodation_images.py

# Verificar que todo esté listo
python check_accommodation_images.py
```

---

## 📤 Cómo Funcionan en WhatsApp

Cuando un cliente pregunta por alojamientos, el bot:

1. **Envía el mensaje introductorio:**
   ```
   🌊🔥 *HotBoat + Alojamiento en Pucón*
   Arma tu experiencia a tu medida...
   ```

2. **Envía cada alojamiento con su imagen:**
   - Primero la imagen
   - Luego el caption con:
     - Nombre del alojamiento
     - Descripción
     - Precio
     - Características

3. **Ejemplo de caption:**
   ```
   *Open Sky - Domo con Tina de Baño*
   
   Domo transparente con vista a las estrellas, 
   perfecto para parejas románticas 🌌
   
   💰 $100.000 / noche (2 pers.)
   
   • Domo transparente
   • Tina de baño interior
   • Vista a las estrellas
   • Experiencia romántica
   ```

---

## ✅ Verificar Configuración

### 1. Verificar que las imágenes existen:

```bash
python check_accommodation_images.py
```

**Salida esperada:**
```
🏠 Verificando imágenes de alojamientos...

✅ open_sky_domo_bath: media/accommodations/open_sky_domo_bath.jpg
✅ open_sky_domo_hydromassage: media/accommodations/open_sky_domo_hydromassage.jpg
✅ relikura_cabin_2: media/accommodations/relikura_cabin_2.jpg
✅ relikura_cabin_4: media/accommodations/relikura_cabin_4.jpg
✅ relikura_cabin_6: media/accommodations/relikura_cabin_6.jpg
✅ relikura_hostel: media/accommodations/relikura_hostel.jpg

🎉 Todas las imágenes están listas!
```

### 2. Probar el envío por WhatsApp:

```bash
python test_accommodations_whatsapp.py +56912345678
```

Esto enviará todas las imágenes de alojamientos al número especificado.

---

## 🎨 Tips para Mejores Imágenes

### Calidad de Imagen
- ✅ **Buena iluminación** (luz natural preferible)
- ✅ **Enfoque nítido** (sin blur)
- ✅ **Colores vivos** pero naturales
- ❌ Evitar imágenes oscuras o borrosas
- ❌ Evitar logos o watermarks grandes

### Composición
- ✅ **Mostrar el espacio completo** (wide shot)
- ✅ **Destacar la característica principal** (tina, hidromasaje, río)
- ✅ **Ambiente acogedor** (camas hechas, limpio, ordenado)
- ❌ Evitar personas en las fotos (privacidad)
- ❌ Evitar objetos personales visibles

### Formato Técnico
- ✅ **Formato horizontal** (16:9 o 4:3)
- ✅ **JPG con buena compresión** (80-90% calidad)
- ✅ **1080px - 2048px de ancho** máximo
- ❌ Evitar imágenes muy pesadas (>5MB)
- ❌ Evitar formatos raros (TIFF, BMP)

---

## 🔄 Actualizar Imágenes

Si quieres cambiar una imagen:

1. **Reemplaza el archivo** en `media/accommodations/` con el mismo nombre
2. **Reinicia el servidor** (Railway lo hace automáticamente)
3. **Prueba** enviando un mensaje de alojamientos

Las imágenes se cachean en WhatsApp por 24-48h, así que puede tardar un poco en verse el cambio.

---

## 🆘 Troubleshooting

### "❌ No se encontró la imagen X"

**Solución:**
1. Verifica que el archivo esté en `media/accommodations/`
2. Verifica que el nombre sea **exactamente** como se indica
3. Verifica que la extensión sea `.jpg`, `.jpeg`, `.png` o `.webp`

### "❌ Error al subir imagen a WhatsApp"

**Solución:**
1. Verifica que la imagen sea menor a 5MB
2. Verifica que el formato sea compatible (JPG, PNG, WEBP)
3. Intenta reducir el tamaño de la imagen

### "Las imágenes no se ven en WhatsApp"

**Solución:**
1. Verifica que el archivo no esté corrupto (ábrelo en tu PC)
2. Verifica los permisos del archivo (debe ser legible)
3. Revisa los logs del servidor para errores específicos

---

## 📞 Cuándo se Envían los Alojamientos

El bot envía automáticamente información de alojamientos cuando detecta:

- ✅ Palabras como: "alojamiento", "hotel", "cabaña", "domo", "hostal", "quedarse", "dormir"
- ✅ Preguntas sobre dónde quedarse en Pucón
- ✅ Consultas sobre paquetes completos (HotBoat + alojamiento)

También puedes forzar el envío desde Kia-Ai si el bot no lo detecta automáticamente.

---

## 📝 Agregar Nuevos Alojamientos

Si quieres agregar un nuevo alojamiento (ej: "Cabañas del Volcán"):

1. **Agrega la imagen:**
   ```
   media/accommodations/cabanas_volcan.jpg
   ```

2. **Edita la configuración:**
   `app/config/accommodations_config.py`
   ```python
   ACCOMMODATION_IMAGES = {
       # ... existing ones ...
       "cabanas_volcan": "https://your-cdn.com/cabanas-volcan.jpg",
   }
   ```

3. **Edita el handler:**
   `app/bot/accommodations.py`
   - Agrega un nuevo `AccommodationInfo`
   - Inclúyelo en `get_all_accommodations()`
   - Actualiza `get_accommodations_with_images()`

4. **Actualiza las traducciones:**
   `app/bot/translations.py`
   - Actualiza el mensaje de "accommodations"

---

## 🚀 Deployment

### Local (Testing)
Las imágenes en `media/accommodations/` se usan automáticamente.

### Railway (Production)
Las imágenes se incluyen en el deploy. Si agregas nuevas:
```bash
git add media/accommodations/
git commit -m "Add new accommodation images"
git push
```

Railway las incluirá en el próximo deploy.

### Usando URLs Externas (Opcional)
Si prefieres usar un CDN (Cloudinary, AWS S3):

1. Sube las imágenes a tu CDN
2. Actualiza `app/config/accommodations_config.py` con las URLs públicas
3. Las imágenes locales serán fallback si la URL falla

---

## ✨ Resultado Final

Cuando todo esté configurado, el cliente recibirá:

```
[Imagen del Domo con Tina]
*Open Sky - Domo con Tina de Baño*
Domo transparente con vista a las estrellas...
💰 $100.000 / noche (2 pers.)

[Imagen del Domo con Hidromasaje]
*Open Sky - Domo con Hidromasaje*
...

[Imagen Cabaña 2 personas]
*Raíces de Relikura - Cabaña 2 personas*
...
```

¡Todo automático y hermoso! 🎉

---

**¿Necesitas ayuda?** Revisa los logs del servidor o ejecuta los scripts de verificación.
