# 🏠 Inicio Rápido: Imágenes de Alojamientos

Esta guía te llevará paso a paso para configurar las imágenes de alojamientos.

## ✅ Checklist Rápido

- [ ] **Paso 1:** Prepara tus 6 imágenes
- [ ] **Paso 2:** Renombra los archivos correctamente
- [ ] **Paso 3:** Copia las imágenes a `media/accommodations/`
- [ ] **Paso 4:** Verifica con el script
- [ ] **Paso 5:** Prueba enviando por WhatsApp

---

## 📸 Paso 1: Prepara tus Imágenes

Necesitas **6 imágenes** en total:

### Open Sky (2 imágenes)
1. **Domo con tina de baño** - Foto del domo con la tina visible
2. **Domo con hidromasaje** - Foto del domo con hidromasaje visible

### Raíces de Relikura (4 imágenes)
3. **Cabaña 2 personas** - Cabaña pequeña para parejas
4. **Cabaña 4 personas** - Cabaña mediana para familia pequeña
5. **Cabaña 6 personas** - Cabaña grande para grupos
6. **Hostal** - Foto del hostal económico

**Requisitos técnicos:**
- ✅ Formato: JPG, JPEG, PNG o WEBP
- ✅ Tamaño: Máximo 5MB por imagen
- ✅ Resolución: Al menos 1080px de ancho
- ✅ Orientación: Horizontal preferible

---

## ✏️ Paso 2: Renombra los Archivos

Renombra tus imágenes **EXACTAMENTE** así:

```
open_sky_domo_bath.jpg
open_sky_domo_hydromassage.jpg
relikura_cabin_2.jpg
relikura_cabin_4.jpg
relikura_cabin_6.jpg
relikura_hostel.jpg
```

⚠️ **Importante:** Los nombres deben ser exactos, con minúsculas y guiones bajos.

---

## 📂 Paso 3: Copia las Imágenes

### Opción A: Manual (Drag & Drop)

1. Abre la carpeta del proyecto
2. Navega a: `media/accommodations/`
3. Arrastra las 6 imágenes a esa carpeta

### Opción B: Con Script

```bash
# Desde la raíz del proyecto
python add_accommodation_image.py open_sky_domo_bath ~/Downloads/domo1.jpg
python add_accommodation_image.py open_sky_domo_hydromassage ~/Downloads/domo2.jpg
python add_accommodation_image.py relikura_cabin_2 ~/Downloads/cabana2.jpg
python add_accommodation_image.py relikura_cabin_4 ~/Downloads/cabana4.jpg
python add_accommodation_image.py relikura_cabin_6 ~/Downloads/cabana6.jpg
python add_accommodation_image.py relikura_hostel ~/Downloads/hostal.jpg
```

El script te avisará si hay algún problema con las imágenes.

---

## ✅ Paso 4: Verifica la Configuración

Ejecuta el script de verificación:

```bash
python check_accommodation_images.py
```

**Resultado esperado:**

```
🏠 Verificando imágenes de alojamientos...

✅ open_sky_domo_bath           → open_sky_domo_bath.jpg           (1.23MB)
✅ open_sky_domo_hydromassage   → open_sky_domo_hydromassage.jpg   (1.45MB)
✅ relikura_cabin_2             → relikura_cabin_2.jpg             (0.98MB)
✅ relikura_cabin_4             → relikura_cabin_4.jpg             (1.12MB)
✅ relikura_cabin_6             → relikura_cabin_6.jpg             (1.34MB)
✅ relikura_hostel              → relikura_hostel.jpg              (0.87MB)

🎉 ¡Perfecto! Todas las 6 imágenes están disponibles
```

Si falta alguna imagen, el script te dirá cuál.

---

## 📤 Paso 5: Prueba el Envío por WhatsApp

Prueba enviando los alojamientos a tu propio número:

```bash
python test_accommodations_whatsapp.py TU_NUMERO
```

**Ejemplo:**
```bash
python test_accommodations_whatsapp.py 56912345678
```

Recibirás en WhatsApp:
1. Mensaje introductorio
2. **2 imágenes** de Open Sky (con captions)
3. **3 imágenes** de cabañas Relikura (con captions)
4. **1 imagen** del hostal (con caption)
5. Mensaje de cierre con instrucciones

Si todo se ve bien, **¡listo!** 🎉

---

## 🔄 Deployment

### Si estás usando Railway:

```bash
git add media/accommodations/
git commit -m "Add accommodation images"
git push
```

Las imágenes se incluirán automáticamente en el deploy.

### Si estás en local:

No necesitas hacer nada, las imágenes ya están disponibles.

---

## 🆘 Problemas Comunes

### "❌ No se encontró la imagen X"

**Solución:**
- Verifica que el archivo esté en `media/accommodations/`
- Verifica que el nombre sea exacto (con minúsculas y guiones bajos)
- Verifica la extensión (.jpg, .jpeg, .png, o .webp)

### "⚠️ La imagen es muy grande"

**Solución:**
- Comprime la imagen en: https://tinyjpg.com/
- O usa un editor de fotos para reducir el tamaño
- Objetivo: Menos de 5MB

### "❌ Error enviando imagen por WhatsApp"

**Solución:**
- Verifica que tengas configurado `WHATSAPP_API_TOKEN` en tu `.env`
- Verifica que el número de WhatsApp Business esté activo
- Revisa los logs del servidor para más detalles

---

## 📊 ¿Cómo Funciona en Producción?

Cuando un cliente pregunta por alojamientos (dice "alojamiento", "hotel", "cabaña", etc.), el bot:

1. **Detecta la intención** automáticamente
2. **Busca las imágenes** en `media/accommodations/`
3. **Sube cada imagen** a WhatsApp
4. **Envía la imagen** con su caption descriptivo
5. **Registra todo** en la conversación

El cliente recibe:
```
[Foto hermosa del domo]

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

## 🎨 Tips para Mejores Resultados

### Composición de las Fotos
- ✅ Fotos con buena iluminación (luz natural)
- ✅ Espacio limpio y ordenado
- ✅ Enfoque en la característica principal (tina, hidromasaje, río)
- ✅ Fotos horizontales (16:9 o 4:3)

### Lo que NO hacer
- ❌ Fotos oscuras o borrosas
- ❌ Personas visibles (privacidad)
- ❌ Objetos personales desordenados
- ❌ Logos o watermarks grandes
- ❌ Imágenes muy pesadas (>5MB)

---

## 📖 Recursos Adicionales

- **Guía completa:** `GUIA_IMAGENES_ALOJAMIENTOS.md`
- **Configuración técnica:** `app/config/accommodations_config.py`
- **Handler de alojamientos:** `app/bot/accommodations.py`
- **Traducciones:** `app/bot/translations.py`

---

## ✨ ¡Eso es Todo!

Una vez que completes estos 5 pasos, tu bot estará enviando hermosas imágenes de alojamientos automáticamente por WhatsApp. 🎉

¿Necesitas ayuda? Revisa la guía completa o ejecuta los scripts de verificación.
