# 📄 Documentos para WhatsApp

Esta carpeta contiene documentos (PDFs) que el bot enviará automáticamente por WhatsApp.

## 📁 Archivos Requeridos

### alojamientos.pdf

**Propósito:** Información completa de alojamientos (Open Sky y Raíces de Relikura)

**Cuándo se envía:** Cuando un cliente selecciona la opción "6. Alojamientos" del menú principal

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

### Paso 2: Guarda el archivo

Guarda tu PDF con el nombre exacto:
```
alojamientos.pdf
```

### Paso 3: Copia a esta carpeta

Copia `alojamientos.pdf` a:
```
media/documents/
```

### Paso 4: Deploy

Si estás usando Railway:
```bash
git add media/documents/alojamientos.pdf
git commit -m "Add accommodations PDF"
git push
```

---

## ✅ Verificar

Para verificar que el PDF funciona:

1. Envía un mensaje de WhatsApp a tu bot
2. Selecciona "6. Alojamientos" del menú
3. Deberías recibir un mensaje con el PDF adjunto

---

## 📊 Flujo Completo

```
Cliente: "6"
   ↓
Bot: "🏠 Alojamientos en Pucón"
     "Te envío un PDF con toda la información..."
     [PDF adjunto: alojamientos.pdf]
   ↓
Bot: "📄 Revisa el PDF y luego respóndeme:
      1️⃣ ¿Qué alojamiento prefieres?
      2️⃣ ¿Qué tipo de habitación?
      ..."
   ↓
Cliente responde con sus preferencias
   ↓
Bot: "✅ Perfecto! He recibido tu solicitud..."
     "⏳ Déjame verificar disponibilidad..."
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
