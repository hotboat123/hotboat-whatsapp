# 📸 Imágenes Necesarias - Resumen Ejecutivo

## 🎯 ¿Qué necesitas preparar?

### 1️⃣ Imagen General de Packs (Opcional pero Recomendado)
**No existe actualmente** - Sería ideal tener una imagen que se muestre cuando entran a "Alojamientos y Packs Pucón" (opción 7).

📍 **Ubicación sugerida:** `media/images/packs/intro.jpg` o similar
📝 **Contenido sugerido:**
- Título: "Paquetes HotBoat + Alojamiento"
- Vista general de qué incluyen los packs
- Beneficios de reservar un paquete completo
- Call-to-action para elegir 1, 2 o 3 noches

---

### 2️⃣ Imágenes de cada Pack Individual

#### 📦 Pack 1 Noche
**📁 Carpeta:** `media/images/packs/pack_1_noche/`
**🔢 Cantidad:** 2-4 imágenes recomendadas

**Incluye:**
- 🏠 Alojamiento (1 noche)
- 🚤 HotBoat

**Contenido sugerido para las imágenes:**
1. **Imagen 1 (Portada):** Título "Pack 1 Noche", foto atractiva del HotBoat + alojamiento
2. **Imagen 2 (Itinerario):** 
   - Día 1: Check-in → HotBoat (horario) → Cena → Descanso
   - Día 2: Desayuno → Check-out
3. **Imagen 3 (Precios):**
   - Precio por persona según alojamiento elegido
   - Qué incluye / No incluye
4. **Imagen 4 (Extra - Opcional):** Condiciones, reservas, contacto

---

#### 📦 Pack 2 Noches
**📁 Carpeta:** `media/images/packs/pack_2_noches/`
**🔢 Cantidad:** 2-4 imágenes recomendadas

**Incluye:**
- 🏠 Alojamiento (2 noches)
- 🚤 HotBoat
- 🚣 Rafting

**Contenido sugerido para las imágenes:**
1. **Imagen 1 (Portada):** Título "Pack 2 Noches", collage HotBoat + Rafting + alojamiento
2. **Imagen 2 (Itinerario):**
   - Día 1: Check-in → HotBoat → Cena
   - Día 2: Desayuno → Rafting → Libre → Cena
   - Día 3: Desayuno → Check-out
3. **Imagen 3 (Precios):**
   - Precio por persona según alojamiento
   - Qué incluye / No incluye
4. **Imagen 4 (Extra - Opcional):** Fotos de las actividades, testimonios

---

#### 📦 Pack 3 Noches
**📁 Carpeta:** `media/images/packs/pack_3_noches/`
**🔢 Cantidad:** 3-5 imágenes recomendadas

**Incluye:**
- 🏠 Alojamiento (3 noches)
- 🚤 HotBoat
- 🚣 Rafting
- 🐴 Cabalgata

**Contenido sugerido para las imágenes:**
1. **Imagen 1 (Portada):** Título "Pack 3 Noches - Experiencia Completa"
2. **Imagen 2 (Itinerario):**
   - Día 1: Check-in → HotBoat → Cena
   - Día 2: Desayuno → Rafting → Libre → Cena
   - Día 3: Desayuno → Cabalgata → Libre → Cena
   - Día 4: Desayuno → Check-out
3. **Imagen 3 (Precios):**
   - Precio por persona según alojamiento
   - Qué incluye / No incluye
4. **Imagen 4 (Actividades):** Detalles de cada experiencia
5. **Imagen 5 (Extra - Opcional):** Por qué elegir el pack completo, valor agregado

---

## 📊 Resumen de Carpetas

```
media/images/packs/
├── pack_1_noche/      ← 2-4 imágenes (.jpg)
├── pack_2_noches/     ← 2-4 imágenes (.jpg)
└── pack_3_noches/     ← 3-5 imágenes (.jpg)
```

---

## 🎨 Especificaciones Técnicas

### Formato
- **Extensión:** `.jpg` (recomendado), también `.png`, `.jpeg`, `.webp`
- **Ancho:** 1080px máximo (WhatsApp optimiza automáticamente)
- **Peso:** Menos de 500KB por imagen
- **Orientación:** Vertical preferiblemente (más natural en móviles)

### Nombres de Archivos
- Usar números para ordenar: `01-portada.jpg`, `02-itinerario.jpg`, `03-precios.jpg`
- El sistema envía en orden alfabético
- El nombre específico no importa, solo el orden

### Diseño
- ✅ Texto GRANDE y legible
- ✅ Colores de marca HotBoat (azul/celeste)
- ✅ Emojis para hacer visual (🏠 🚤 🚣 🐴 💰 📅)
- ✅ Información clara y concisa
- ✅ Precios destacados
- ❌ Evitar párrafos largos de texto

---

## 🚀 ¿Cuándo se muestran?

1. Usuario escribe "7" (Alojamientos y Packs)
2. Usuario elige "Paquetes Completos" del submenú
3. Bot muestra opciones: 1, 2 o 3 noches
4. **Usuario escribe "1"** → Se envían TODAS las imágenes de `pack_1_noche/`
5. **Usuario escribe "2"** → Se envían TODAS las imágenes de `pack_2_noches/`
6. **Usuario escribe "3"** → Se envían TODAS las imágenes de `pack_3_noches/`

---

## 📝 Checklist

- [ ] Crear imágenes para Pack 1 Noche (2-4 imágenes)
- [ ] Crear imágenes para Pack 2 Noches (2-4 imágenes)
- [ ] Crear imágenes para Pack 3 Noches (3-5 imágenes)
- [ ] Subir imágenes a las carpetas correspondientes
- [ ] Verificar que los nombres estén en orden (01-, 02-, 03-...)
- [ ] Probar en WhatsApp que se vean correctamente

---

## 💡 Tip Pro

**No tienes que crear todo de una vez.** Puedes:
1. Empezar con el pack más popular (probablemente Pack 2 Noches)
2. Subir esas imágenes y probar
3. Luego crear los otros dos packs

Las carpetas vacías no causarán error, el bot simplemente mostrará un mensaje de que no hay imágenes disponibles.
