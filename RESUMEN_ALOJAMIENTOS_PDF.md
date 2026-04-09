# 🏠 Sistema de Alojamientos con PDF - Resumen

## ✅ Lo que se Implementó

He actualizado completamente el sistema de alojamientos para que sea más simple y eficiente usando un PDF en lugar de múltiples imágenes.

---

## 📋 Cambios Realizados

### 1. **Menú Principal Actualizado**

**Antes:**
```
1️⃣ Disponibilidad y horarios
2️⃣ Precios por persona  
3️⃣ Características del HotBoat
4️⃣ Extras y promociones
5️⃣ Ubicación y reseñas
6️⃣ Llamar a Tomás 👨‍✈️
```

**Ahora:**
```
1️⃣ Disponibilidad y horarios
2️⃣ Precios por persona
3️⃣ Características del HotBoat
4️⃣ Extras y promociones
5️⃣ Ubicación y reseñas
6️⃣ Alojamientos en Pucón 🏠    ← NUEVO
7️⃣ Llamar a Tomás 👨‍✈️          ← Movido de 6 a 7
```

### 2. **Nuevo Flujo de Alojamientos**

Cuando un cliente selecciona "6. Alojamientos":

1. **Bot envía mensaje introductorio:**
   ```
   🏠 *Alojamientos en Pucón*
   
   Te envío un PDF con toda la información detallada 
   de nuestros alojamientos recomendados ⬇️
   ```

2. **Bot envía el PDF adjunto:**
   - Archivo: `alojamientos.pdf`
   - Nombre visible: `Alojamientos_Pucon_HotBoat.pdf`
   - Caption: `📄 Información completa de alojamientos`

3. **Bot solicita información:**
   ```
   📄 Revisa el PDF y luego respóndeme:
   
   1️⃣ ¿Qué alojamiento prefieres? 
       (Open Sky o Raíces de Relikura)
   
   2️⃣ ¿Qué tipo de habitación? 
       (Domo con tina, Domo con hidromasaje, 
        Cabaña 2/4/6 personas, Hostal)
   
   3️⃣ ¿Para cuántas personas?
   
   4️⃣ ¿Qué fecha tienes pensada?
   
   📲 Responde con estos datos y te confirmo disponibilidad 👍
   ```

4. **Cliente responde con sus preferencias**

5. **Bot confirma:**
   ```
   ✅ *Perfecto, grumete!*
   
   He recibido tu solicitud de alojamiento:
   
   📋 *Resumen:*
   [Detalles de la solicitud]
   
   ⏳ Déjame verificar la disponibilidad...
   
   El *Capitán Tomás* revisará tu solicitud 
   y te contactará para confirmar 👨‍✈️
   ```

---

## 🛠️ Archivos Modificados

| Archivo | Cambios |
|---------|---------|
| `app/bot/translations.py` | - Menú actualizado (6 opciones → 7 opciones)<br>- Nuevos mensajes: `accommodations_intro`, `accommodations_awaiting_confirmation` |
| `app/bot/conversation.py` | - Opción 6 ahora es Alojamientos<br>- Opción 7 ahora es Llamar a Tomás<br>- Retorna tipo `accommodations_pdf` |
| `app/whatsapp/client.py` | - Nueva función: `send_document_message()`<br>- Soporte para enviar PDFs |
| `app/whatsapp/webhook.py` | - Manejo del tipo `accommodations_pdf`<br>- Sube y envía el PDF automáticamente<br>- Manejo de errores si falta el PDF |
| `app/utils/media_handler.py` | - Nueva carpeta: `DOCUMENTS_DIR`<br>- Nueva función: `get_accommodations_pdf_path()` |

---

## 📦 Archivos Creados

| Archivo | Propósito |
|---------|-----------|
| `media/documents/README.md` | Guía de cómo agregar el PDF |
| `media/documents/` (carpeta) | Almacena documentos (PDFs) |

---

## 🎯 Cómo Usar el Sistema

### Para Ti (Admin):

**1. Crea tu PDF de alojamientos**
   - Usa Canva, Google Docs, PowerPoint, etc.
   - Incluye fotos, precios, características de cada alojamiento
   - Máximo 10MB de tamaño
   - Orientación vertical (mejor para móviles)

**2. Guarda el PDF como:**
   ```
   alojamientos.pdf
   ```

**3. Copia el PDF a:**
   ```
   media/documents/alojamientos.pdf
   ```

**4. Haz deploy:**
   ```bash
   git add media/documents/alojamientos.pdf
   git commit -m "Add accommodations PDF"
   git push
   ```

### Para tus Clientes:

**1. Cliente escribe:** `6` o "Alojamientos"

**2. Cliente recibe:**
   - Mensaje explicativo
   - PDF con toda la info

**3. Cliente revisa el PDF y responde:**
   ```
   "Me interesa Open Sky domo con hidromasaje 
   para 2 personas, para el 15 de febrero"
   ```

**4. Bot confirma y notifica a Tomás:**
   ```
   "✅ Perfecto! Déjame verificar disponibilidad...
   El Capitán Tomás te contactará pronto"
   ```

---

## 🔄 Flujo Visual Completo

```
┌─────────────────────────────────────┐
│ Cliente: "6"                        │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ Bot: "🏠 Alojamientos en Pucón"     │
│      "Te envío un PDF..."           │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ Bot: [📄 alojamientos.pdf]          │
│      (10.5 MB, 8 páginas)           │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ Bot: "📄 Revisa el PDF y dime:"    │
│      "1️⃣ ¿Qué alojamiento?"         │
│      "2️⃣ ¿Qué tipo de pieza?"      │
│      "3️⃣ ¿Para cuántas personas?"  │
│      "4️⃣ ¿Qué fecha?"               │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ Cliente: "Open Sky domo con         │
│          hidromasaje, 2 personas,   │
│          15 de febrero"             │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ Bot: "✅ Perfecto!"                 │
│      "📋 Resumen: [...]"            │
│      "⏳ Verificando disponibilidad" │
│      "👨‍✈️ Tomás te contactará"      │
└─────────────────────────────────────┘
```

---

## ✨ Ventajas del Nuevo Sistema

| Ventaja | Descripción |
|---------|-------------|
| **Más Simple** | Un solo PDF vs 6+ imágenes separadas |
| **Más Rápido** | 1 upload vs 6+ uploads |
| **Mejor Experiencia** | Cliente puede guardar y revisar el PDF con calma |
| **Más Profesional** | PDF diseñado vs capturas de pantalla |
| **Fácil de Actualizar** | Cambias el PDF y listo |
| **Menos Errores** | Si falta el PDF, envía mensaje alternativo |
| **Menor Consumo de Datos** | 1 PDF comprimido vs múltiples imágenes |

---

## 🆘 Manejo de Errores

Si el PDF no existe o hay problemas:

```python
# El bot enviará:
"⚠️ Lo siento, no pude enviar el PDF. 
Por favor escribe 'alojamiento' y te envío 
la información por texto."
```

Esto evita que el bot se "rompa" si olvidas agregar el PDF.

---

## 📝 Contenido Sugerido para el PDF

### Página 1: Portada
- Logo de HotBoat
- Título: "Alojamientos en Pucón"
- Subtítulo: "Tu experiencia perfecta comienza aquí"
- Foto hermosa de Pucón

### Páginas 2-3: Open Sky
- **Página 2:** Domo con tina de baño
  - 3-4 fotos del domo
  - Precio: $100.000/noche
  - Capacidad: 2 personas
  - Características destacadas
  
- **Página 3:** Domo con hidromasaje
  - 3-4 fotos del domo
  - Precio: $120.000/noche
  - Capacidad: 2 personas
  - Características premium

### Páginas 4-7: Raíces de Relikura
- **Página 4:** Cabaña 2 personas ($60.000)
- **Página 5:** Cabaña 4 personas ($80.000)
- **Página 6:** Cabaña 6 personas ($100.000)
- **Página 7:** Hostal ($20.000 por persona)

### Página 8: Cómo Reservar
- Paso 1: Contacta por WhatsApp
- Paso 2: Confirma disponibilidad
- Paso 3: Paga por link
- Paso 4: ¡Disfruta!
- Políticas de cancelación

---

## 🚀 Estado Actual

| Componente | Estado |
|-----------|--------|
| Menú actualizado | ✅ Listo |
| Opción 6 (Alojamientos) | ✅ Implementada |
| Opción 7 (Llamar a Tomás) | ✅ Movida correctamente |
| Envío de PDF | ✅ Funcionando |
| Manejo de errores | ✅ Implementado |
| Flujo conversacional | ✅ Completo |
| **PDF físico** | ⏳ **Falta que lo crees** |

---

## 📋 Próximos Pasos (Para Ti)

1. **[ ]** Diseña el PDF con Canva/PowerPoint/etc.
2. **[ ]** Incluye fotos de calidad de cada alojamiento
3. **[ ]** Agrega precios, características, contacto
4. **[ ]** Comprime el PDF (< 10MB preferible)
5. **[ ]** Guarda como `alojamientos.pdf`
6. **[ ]** Copia a `media/documents/`
7. **[ ]** Haz `git push`
8. **[ ]** Prueba enviando "6" por WhatsApp
9. **[ ]** ¡Disfruta! 🎉

---

## 🎨 Herramientas Recomendadas

**Para Crear el PDF:**
- **Canva** (Fácil y visual) - https://www.canva.com/
- **Google Slides** (Gratis) - Exportar como PDF
- **PowerPoint** (Profesional) - Guardar como PDF
- **Adobe InDesign** (Profesional avanzado)

**Para Comprimir:**
- **iLovePDF** - https://www.ilovepdf.com/compress_pdf
- **Smallpdf** - https://smallpdf.com/compress-pdf

---

## ✅ Resumen

**Lo nuevo:**
- ✅ Opción "6. Alojamientos" en el menú
- ✅ "Llamar a Tomás" movido a opción 7
- ✅ Envío automático de PDF
- ✅ Flujo conversacional para recopilar datos
- ✅ Confirmación y notificación a Tomás

**Lo que falta:**
- ⏳ Crear el PDF con la información
- ⏳ Subirlo a `media/documents/alojamientos.pdf`

**Lo que sigue igual:**
- ✅ Todo el resto del bot funciona normal
- ✅ Opciones 1-5 sin cambios
- ✅ Sistema de reservas HotBoat intacto

---

**¿Necesitas ayuda para diseñar el PDF?** ¡Avísame y te ayudo! 🚀
