# 📄 Documentos para WhatsApp

Esta carpeta contiene documentos (PDFs) que el bot enviará automáticamente por WhatsApp.

## 📁 Archivos Requeridos

### alojamientos.pdf

**Propósito:** Información completa de alojamientos (Open Sky y Raíces de Relikura)

**Cuándo se envía:** Cuando un cliente selecciona "6. Alojamientos y Packs" → "2. Solo Alojamientos"

### pack_1_noche.pdf

**Propósito:** Pack completo de 1 noche (Alojamiento + HotBoat)

**Cuándo se envía:** Cuando un cliente selecciona "6. Alojamientos y Packs" → "1. Packs Completos" → "1"

### pack_2_noches.pdf

**Propósito:** Pack completo de 2 noches (Alojamiento + HotBoat + Rafting)

**Cuándo se envía:** Cuando un cliente selecciona "6. Alojamientos y Packs" → "1. Packs Completos" → "2"

### pack_3_noches.pdf

**Propósito:** Pack completo de 3 noches (Alojamiento + HotBoat + Rafting + Cabalgata)

**Cuándo se envía:** Cuando un cliente selecciona "6. Alojamientos y Packs" → "1. Packs Completos" → "3"

**Contenido sugerido:**
- Fotos de cada alojamiento
- Precios detallados
- Características y servicios incluidos
- Ubicación y contacto
- Políticas de reserva y cancelación
- Cómo hacer la reserva

**Formato:**
- Máximo 10MB (límite de WhatsApp para documentos)
- Orientación: Vertical preferible (móviles)
- Diseño: Simple y claro, fácil de leer en móvil

---

## 🚀 Cómo Agregar el PDF

### Paso 1: Crea tu PDF

Puedes usar:
- **Canva** - Fácil y visual
- **Google Docs** - Exportar como PDF
- **PowerPoint** - Guardar como PDF
- **Adobe InDesign** - Profesional

### Paso 2: Guarda los archivos

Guarda tus PDFs con los nombres exactos:
```
alojamientos.pdf
pack_1_noche.pdf
pack_2_noches.pdf
pack_3_noches.pdf
```

### Paso 3: Copia a esta carpeta

Copia todos los PDFs a:
```
media/documents/
```

### Paso 4: Deploy

Si estás usando Railway:
```bash
git add media/documents/*.pdf
git commit -m "Add accommodation and package PDFs"
git push
```

⚠️ **Importante:** Asegúrate de que los archivos estén permitidos en `.gitignore`. El archivo `media/.gitignore` ya está configurado para permitir PDFs en `documents/`.

---

## ✅ Verificar

Para verificar que el PDF funciona:

1. Envía un mensaje de WhatsApp a tu bot
2. Selecciona "6. Alojamientos" del menú
3. Deberías recibir un mensaje con el PDF adjunto

---

## 📊 Flujo Completo

### Opción 1: Packs Completos
```
Cliente: "6"
   ↓
Bot: "🏠📦 Alojamientos y Packs en Pucón"
     "1️⃣ Packs Completos"
     "2️⃣ Solo Alojamientos"
     "3️⃣ Arma tu Pack"
   ↓
Cliente: "1" (Packs Completos)
   ↓
Bot: "🎁 Packs Completos - Todo Incluido"
     "¿Cuántas noches? 1, 2, o 3"
   ↓
Cliente: "2"
   ↓
Bot: "✅ Pack de 2 Noches Seleccionado"
     [PDF adjunto: pack_2_noches.pdf]
     "El Capitán Tomás te contactará pronto"
```

### Opción 2: Solo Alojamientos
```
Cliente: "6" → "2"
   ↓
Bot: [PDF adjunto: alojamientos.pdf]
     "¿Qué alojamiento prefieres?"
     "1️⃣ Open Sky"
     "2️⃣ Raíces de Relikura"
   ↓
Cliente responde y sigue el flujo de reserva
```

### Opción 3: Arma tu Pack
```
Cliente: "6" → "3"
   ↓
Bot: "🛒 Arma tu Pack Personalizado"
     "Elige actividades: 1-HotBoat, 2-Rafting, 3-Volcán, 4-Cabalgata, 5-Vehículo"
   ↓
Cliente: "1, 2, 4"
   ↓
Bot: "¿Quieres agregar alojamiento?"
   ↓
Bot notifica al Capitán Tomás con el resumen
```

---

## 💡 Tips para un Buen PDF

### Contenido
- ✅ **Primera página:** Portada atractiva con logo
- ✅ **Páginas siguientes:** Un alojamiento por página
- ✅ **Fotos grandes:** Que se vean bien en móvil
- ✅ **Precios destacados:** Fáciles de encontrar
- ✅ **CTA clara:** "Contacta para reservar"

### Diseño
- ✅ **Fuentes grandes** (mínimo 12pt)
- ✅ **Alto contraste** (texto oscuro, fondo claro)
- ✅ **Espacios en blanco** (no saturar)
- ✅ **Colores de marca** (consistentes con HotBoat)

### Técnico
- ✅ **Comprime el PDF** si pesa más de 5MB
- ✅ **Orientación vertical** (mejor para móviles)
- ✅ **Páginas: 4-8** (no muy largo)
- ✅ **Resolución:** 72-150 DPI (web)

---

## 🆘 Troubleshooting

### "❌ No pude enviar el PDF"

**Causa:** El archivo no existe o es muy grande

**Solución:**
1. Verifica que el archivo se llame exactamente `alojamientos.pdf`
2. Verifica que esté en la carpeta `media/documents/`
3. Verifica que pese menos de 10MB
4. Comprime el PDF si es necesario

### "El PDF se ve mal en WhatsApp"

**Solución:**
- Usa orientación vertical (portrait)
- Reduce la resolución de las imágenes
- Usa fuentes más grandes
- Prueba en tu móvil antes de publicar

---

## 🎨 Herramientas para Comprimir PDF

Si tu PDF es muy grande:

- **Online:** https://www.ilovepdf.com/compress_pdf
- **Mac:** Vista Previa → Archivo → Exportar → Quartz Filter: Reduce File Size
- **Windows:** Adobe Acrobat → Archivo → Reducir tamaño

---

**¿Necesitas ayuda?** Contacta al equipo de desarrollo.
