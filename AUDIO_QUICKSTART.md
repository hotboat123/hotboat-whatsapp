# 🎤 Audio QuickStart - HotBoat WhatsApp Bot

## ⚡ Inicio Rápido

Tu bot ahora puede **enviar y recibir audios**. Aquí está todo lo que necesitas saber en 5 minutos.

---

## 📥 Recibir Audios (Ya funciona automáticamente)

✅ **Ya está configurado** - No necesitas hacer nada.

Cuando un usuario envía un audio:
1. Se descarga automáticamente a `media/audio/`
2. Se envía notificación por email
3. Se guarda en la base de datos
4. El bot responde automáticamente

---

## 📤 Enviar Audios

### Opción 1: Desde archivo local

```python
# En conversation.py o cualquier handler
await self.send_audio_message(
    to="56912345678",
    audio_path="media/audio/mi_audio.ogg"
)
```

### Opción 2: Desde URL pública

```python
await self.send_audio_message(
    to="56912345678",
    audio_url="https://ejemplo.com/audio.mp3"
)
```

---

## 🧪 Probar Ahora

### 1. Probar Recepción
```
1. Abre WhatsApp
2. Envía un audio al bot
3. Verifica que responde
4. Revisa media/audio/ para ver el archivo
```

### 2. Probar Envío
```bash
# Ejecutar script de prueba
python test_audio.py

# Seleccionar opción 1
# (Primero coloca un audio en media/audio/test.ogg)
```

---

## 📁 Formatos Soportados

- ✅ OGG (recomendado para WhatsApp)
- ✅ MP3
- ✅ M4A
- ✅ WAV
- ✅ AAC

---

## 💡 Ejemplos de Uso

### Ejemplo 1: Audio de Bienvenida
```python
async def send_welcome(self, phone: str):
    await self.send_audio_message(
        to=phone,
        audio_path="media/audio/bienvenida.ogg"
    )
```

### Ejemplo 2: Instrucciones de Ubicación
```python
if "ubicación" in message.lower():
    await self.send_audio_message(
        to=from_number,
        audio_path="media/audio/instrucciones_ubicacion.ogg"
    )
```

### Ejemplo 3: Confirmación de Reserva
```python
async def confirm_booking(self, phone: str, booking_details: dict):
    # Enviar audio personalizado
    await self.send_audio_message(
        to=phone,
        audio_path="media/audio/confirmacion_reserva.ogg"
    )
```

---

## 📂 Dónde se Guardan los Audios

```
media/
└── audio/
    ├── {media_id}_{timestamp}.ogg    # Audios recibidos
    ├── bienvenida.ogg                # Tus audios personalizados
    └── instrucciones.mp3             # Más audios
```

---

## 🎯 Casos de Uso Sugeridos

1. **Bienvenida Personalizada** 🎉
   - Audio del Capitán Tomás dando la bienvenida

2. **Instrucciones de Ubicación** 📍
   - Cómo llegar al punto de encuentro

3. **Confirmación de Reserva** ✅
   - Confirmación con detalles de la reserva

4. **Promociones Especiales** 🎁
   - Ofertas especiales en audio

5. **FAQ en Audio** ❓
   - Respuestas pregrabadas a preguntas frecuentes

---

## 📖 Documentación Completa

Para más detalles, consulta:
- **[AUDIO_GUIDE.md](AUDIO_GUIDE.md)** - Guía completa con todos los detalles
- **[CHANGELOG_AUDIO.md](CHANGELOG_AUDIO.md)** - Lista de cambios técnicos

---

## ❓ FAQ Rápido

**P: ¿Qué formato usar?**
R: OGG para mejor compatibilidad con WhatsApp.

**P: ¿Límite de tamaño?**
R: WhatsApp permite hasta 16 MB.

**P: ¿Se transcriben los audios?**
R: No automáticamente, pero puedes integrar Whisper API.

**P: ¿Dónde veo los audios recibidos?**
R: En `media/audio/` o ejecuta `python test_audio.py` (opción 3).

---

## 🚀 Próximos Pasos

1. ✅ Graba audios personalizados para tu negocio
2. ✅ Colócalos en `media/audio/`
3. ✅ Úsalos en tu bot con `send_audio_message()`
4. ✅ Prueba enviando audios desde WhatsApp

---

## 🎤 ¡Listo para usar!

Tu bot ya puede manejar audios. Empieza a experimentar y mejora la experiencia de tus clientes.

**¿Necesitas ayuda?** Revisa [AUDIO_GUIDE.md](AUDIO_GUIDE.md) para documentación completa.

---

**HotBoat WhatsApp Bot** 🚤⚓
