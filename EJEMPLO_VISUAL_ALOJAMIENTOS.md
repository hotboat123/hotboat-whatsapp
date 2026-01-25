# 📱 Ejemplo Visual: Cómo se Ven los Alojamientos en WhatsApp

Este archivo muestra exactamente cómo se verán los mensajes de alojamientos en WhatsApp cuando un cliente los solicite.

---

## 🔔 Trigger: Cliente Pregunta por Alojamientos

**Cliente escribe cualquiera de estos mensajes:**

```
"Necesito alojamiento en Pucón"
"¿Tienen hotel o cabaña?"
"Dónde me puedo quedar?"
"Quiero domo + hotboat"
"Opciones de hospedaje?"
```

El bot detecta automáticamente y responde...

---

## 📤 Respuesta del Bot (Secuencia Completa)

### **Mensaje 1: Introducción (Solo Texto)**

```
🌊🔥 *HotBoat + Alojamiento en Pucón*

Arma tu experiencia a tu medida con HotBoat 
y nuestros alojamientos recomendados.

⭐ *Open Sky* – Para parejas románticas
Domos transparentes con vista a las estrellas 🌌
```

---

### **Mensaje 2: Domo con Tina (Imagen + Caption)**

```
┌─────────────────────────────┐
│                             │
│   [IMAGEN DEL DOMO CON      │
│    TINA DE BAÑO, VISTA      │
│    INTERIOR, TRANSPARENTE,  │
│    ROMÁNTICO]               │
│                             │
└─────────────────────────────┘

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

### **Mensaje 3: Domo con Hidromasaje (Imagen + Caption)**

```
┌─────────────────────────────┐
│                             │
│   [IMAGEN DEL DOMO CON      │
│    HIDROMASAJE INTERIOR,    │
│    LUCES, AMBIENTE          │
│    PREMIUM]                 │
│                             │
└─────────────────────────────┘

*Open Sky - Domo con Hidromasaje*

Domo transparente con hidromasaje interior, 
la experiencia más exclusiva 🌟

💰 $120.000 / noche (2 pers.)

• Domo transparente
• Hidromasaje interior
• Vista a las estrellas
• Experiencia premium
```

---

### **Mensaje 4: Header Relikura (Solo Texto)**

```
🌿 *Raíces de Relikura* – Familiar con actividades
Hostal y cabañas junto al río, con tinaja 
y entorno natural 🍃
```

---

### **Mensaje 5: Cabaña 2 Personas (Imagen + Caption)**

```
┌─────────────────────────────┐
│                             │
│   [IMAGEN DE CABAÑA         │
│    PEQUEÑA, JUNTO AL RÍO,   │
│    TINAJA VISIBLE,          │
│    NATURALEZA]              │
│                             │
└─────────────────────────────┘

*Raíces de Relikura - Cabaña 2 personas*

Cabaña junto al río, con tinaja y entorno 
natural perfecto para parejas 🌿

💰 $60.000 / noche (2 pers.)

• Cabaña junto al río
• Tinaja exterior
• Entorno natural
• Ideal para parejas
```

---

### **Mensaje 6: Cabaña 4 Personas (Imagen + Caption)**

```
┌─────────────────────────────┐
│                             │
│   [IMAGEN DE CABAÑA         │
│    MEDIANA, ESPACIOSA,      │
│    FAMILIAR, RÍO AL FONDO]  │
│                             │
└─────────────────────────────┘

*Raíces de Relikura - Cabaña 4 personas*

Cabaña espaciosa junto al río, ideal para 
familias pequeñas 🏡

💰 $80.000 / noche (4 pers.)

• Cabaña junto al río
• Tinaja exterior
• Entorno natural
• Ideal para familias
```

---

### **Mensaje 7: Cabaña 6 Personas (Imagen + Caption)**

```
┌─────────────────────────────┐
│                             │
│   [IMAGEN DE CABAÑA GRANDE, │
│    VARIOS DORMITORIOS,      │
│    GRUPO FAMILIAR,          │
│    RÍO Y ÁRBOLES]           │
│                             │
└─────────────────────────────┘

*Raíces de Relikura - Cabaña 6 personas*

Cabaña grande junto al río, perfecta para 
grupos y familias grandes 👨‍👩‍👧‍👦

💰 $100.000 / noche (6 pers.)

• Cabaña junto al río
• Tinaja exterior
• Entorno natural
• Ideal para grupos
```

---

### **Mensaje 8: Hostal (Imagen + Caption)**

```
┌─────────────────────────────┐
│                             │
│   [IMAGEN DEL HOSTAL,       │
│    AMBIENTE SOCIAL,         │
│    ECONÓMICO, TINAJA        │
│    COMPARTIDA]              │
│                             │
└─────────────────────────────┘

*Raíces de Relikura - Hostal*

Hostal económico junto al río, con tinaja 
y actividades 🎒

💰 $20.000 / noche por persona

• Hostal económico
• Tinaja compartida
• Entorno natural
• Actividades disponibles
```

---

### **Mensaje 9: Cierre con CTA (Solo Texto)**

```
📌 *Cómo funciona:*
1. Me dices la fecha y la opción de alojamiento
2. Te confirmo disponibilidad
3. Pagas todo en un solo link y quedas reservado

📲 Responde este mensaje con la fecha y 
alojamiento que prefieras
```

---

## 📊 Resumen del Envío

**Total de mensajes:** 9
- **3 mensajes de texto puro** (headers y cierre)
- **6 mensajes con imagen** (cada alojamiento)

**Tiempo total de envío:** ~10-15 segundos
- Delay de 0.5s entre textos
- Delay de 1s entre imágenes (para evitar spam)

**Orden de envío:**
1. Intro general
2. Open Sky header
3. 🖼️ Domo tina
4. 🖼️ Domo hidromasaje
5. Relikura header
6. 🖼️ Cabaña 2 pers
7. 🖼️ Cabaña 4 pers
8. 🖼️ Cabaña 6 pers
9. 🖼️ Hostal
10. Cierre con CTA

---

## 🎯 Experiencia del Cliente

### Desde el punto de vista del cliente:

1. **Hace una pregunta simple:**
   ```
   "Necesito alojamiento"
   ```

2. **Recibe una presentación profesional:**
   - Contexto (HotBoat + Alojamiento)
   - Categorías claras (Romántico vs Familiar)

3. **Ve imágenes hermosas de cada opción:**
   - Fotos de calidad profesional
   - Captions descriptivos
   - Precios claros
   - Características destacadas

4. **Tiene información clara para decidir:**
   - Precios comparables
   - Capacidades visibles
   - Características únicas de cada uno

5. **Sabe exactamente qué hacer:**
   - "Responde con fecha y alojamiento"
   - Proceso simple de 3 pasos

---

## 💬 Conversación Completa Ejemplo

```
👤 Cliente:
Hola! Estamos planificando ir a Pucón.
¿Tienen opciones de alojamiento?

🤖 Bot:
🌊🔥 *HotBoat + Alojamiento en Pucón*
Arma tu experiencia a tu medida...
[continúa con todos los mensajes]

[Cliente recibe 6 hermosas imágenes]

👤 Cliente:
Me interesa el domo con hidromasaje 
para el 15 de febrero

🤖 Bot:
¡Excelente elección! 🌟
Déjame verificar disponibilidad 
del domo con hidromasaje para el 15/02...

[Conversación continúa normalmente]
```

---

## 🎨 Tips de Fotografía para Cada Alojamiento

### Open Sky - Domo con Tina
**Qué capturar:**
- ✅ Interior del domo (estructura transparente visible)
- ✅ Tina de baño como protagonista
- ✅ Si es posible: foto nocturna con estrellas
- ✅ Ambiente romántico (velas, luces suaves)
- ✅ Cama visible al fondo

**Ángulo:** Wide shot desde dentro, mostrando techo transparente

### Open Sky - Domo con Hidromasaje
**Qué capturar:**
- ✅ Hidromasaje burbujeante (con luces si tiene)
- ✅ Domo transparente visible
- ✅ Ambiente más lujoso que el anterior
- ✅ Detalles premium (champagne, pétalos, etc)

**Ángulo:** Enfoque en el hidromasaje, pero mostrando también el techo

### Relikura - Cabaña 2 Personas
**Qué capturar:**
- ✅ Exterior de la cabaña (pequeña, acogedora)
- ✅ Río visible en el fondo o al lado
- ✅ Tinaja en el jardín
- ✅ Naturaleza abundante (árboles, verde)

**Ángulo:** Exterior frontal, mostrando cabaña completa + entorno

### Relikura - Cabaña 4 Personas
**Qué capturar:**
- ✅ Cabaña más grande que la anterior
- ✅ Entrada espaciosa
- ✅ Río y naturaleza
- ✅ Área de estar exterior si tiene

**Ángulo:** Exterior con perspectiva que muestre tamaño

### Relikura - Cabaña 6 Personas
**Qué capturar:**
- ✅ La cabaña más grande
- ✅ Multi-niveles si los tiene
- ✅ Amplio jardín/terraza
- ✅ Río y entorno natural

**Ángulo:** Wide shot mostrando toda la propiedad

### Relikura - Hostal
**Qué capturar:**
- ✅ Área común (social, juvenil, backpacker)
- ✅ Dormitorios compartidos o privados
- ✅ Tinaja compartida
- ✅ Ambiente acogedor pero económico

**Ángulo:** Interior o exterior mostrando zona común

---

## 🚀 Para Implementar

1. **Toma/consigue las 6 fotos** siguiendo los tips arriba
2. **Edita si es necesario** (luz, recorte, compresión)
3. **Renombra exactamente:**
   ```
   open_sky_domo_bath.jpg
   open_sky_domo_hydromassage.jpg
   relikura_cabin_2.jpg
   relikura_cabin_4.jpg
   relikura_cabin_6.jpg
   relikura_hostel.jpg
   ```
4. **Copia a:** `media/accommodations/`
5. **Verifica:** `python check_accommodation_images.py`
6. **Prueba:** `python test_accommodations_whatsapp.py TU_NUMERO`
7. **Deploy:** `git push`

---

## ✨ Resultado Final

Un cliente que pregunta por alojamientos recibirá:
- ✅ Información completa y organizada
- ✅ 6 hermosas imágenes profesionales
- ✅ Precios claros y comparables
- ✅ CTA claro para continuar
- ✅ Experiencia de nivel booking.com/airbnb

**Todo automático** sin que tengas que hacer nada. 🎉

---

**Lee también:**
- `QUICKSTART_ALOJAMIENTOS.md` - Guía paso a paso
- `GUIA_IMAGENES_ALOJAMIENTOS.md` - Guía completa técnica
- `RESUMEN_SISTEMA_ALOJAMIENTOS.md` - Overview del sistema
