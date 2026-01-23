# 🎤 Audio en WhatsApp - HotBoat Bot

## ⚡ TL;DR (Resumen Ultra Rápido)

Tu bot ahora puede **enviar y recibir audios**. Ya funciona automáticamente para recibir. Para enviar:

```python
await conversation_manager.send_audio_message(
    to="56912345678",
    audio_path="media/audio/mi_audio.ogg"
)
```

---

## 📚 Documentación

| Documento | Para Qué | Tiempo |
|-----------|----------|--------|
| **[AUDIO_QUICKSTART.md](AUDIO_QUICKSTART.md)** | Empezar rápido | 5 min |
| **[AUDIO_GUIDE.md](AUDIO_GUIDE.md)** | Guía completa | 20 min |
| **[EJEMPLOS_AUDIOS_SUGERIDOS.md](EJEMPLOS_AUDIOS_SUGERIDOS.md)** | Guiones para grabar | 15 min |
| **[CHANGELOG_AUDIO.md](CHANGELOG_AUDIO.md)** | Cambios técnicos | 10 min |
| **[RESUMEN_IMPLEMENTACION_AUDIO.md](RESUMEN_IMPLEMENTACION_AUDIO.md)** | Resumen completo | 10 min |

---

## 🚀 Inicio Rápido (3 Pasos)

### 1. Probar Recepción
```
Envía un audio al bot desde WhatsApp
→ El bot responde automáticamente
→ Audio guardado en media/audio/
```

### 2. Probar Envío
```bash
python test_audio.py
# Opción 1: Enviar audio
```

### 3. Integrar en tu Bot
```python
# En conversation.py
if "ubicación" in message.lower():
    await self.send_audio_message(
        to=from_number,
        audio_path="media/audio/ubicacion.ogg"
    )
```

---

## ✅ Lo que Ya Funciona

- ✅ Recibir audios (automático)
- ✅ Descargar y guardar audios
- ✅ Notificaciones por email
- ✅ Guardar en base de datos
- ✅ Enviar audios desde archivo local
- ✅ Enviar audios desde URL
- ✅ Múltiples formatos (OGG, MP3, M4A, WAV, AAC)

---

## 🎯 Casos de Uso

1. **Bienvenida personalizada** - Audio del Capitán Tomás
2. **Instrucciones de ubicación** - Cómo llegar
3. **Confirmación de reserva** - Detalles de la reserva
4. **FAQ en audio** - Horarios, precios, etc.
5. **Promociones** - Ofertas especiales

---

## 📂 Archivos

```
media/audio/          # Tus audios aquí
test_audio.py         # Script de prueba
AUDIO_QUICKSTART.md   # Empieza aquí ⭐
AUDIO_GUIDE.md        # Guía completa
```

---

## 🆘 Ayuda Rápida

**Ver audios recibidos:**
```bash
python test_audio.py
# Opción 3
```

**Ver logs:**
```bash
tail -f logs/app.log | grep -i audio
```

**Problema común:**
- ❌ "No existe el archivo" → Verifica la ruta en `media/audio/`
- ❌ "Error de formato" → Usa OGG, MP3, o M4A
- ❌ "No se envía" → Verifica credenciales de WhatsApp API

---

## 🎤 Siguiente Paso

1. Lee [AUDIO_QUICKSTART.md](AUDIO_QUICKSTART.md) (5 minutos)
2. Graba 2-3 audios usando [EJEMPLOS_AUDIOS_SUGERIDOS.md](EJEMPLOS_AUDIOS_SUGERIDOS.md)
3. Prueba con `python test_audio.py`
4. ¡Disfruta! 🎉

---

**¡Tu bot ahora puede hablar! 🚤⚓**
