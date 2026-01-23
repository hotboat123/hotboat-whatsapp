# 🎤 Guía de Funcionalidad de Audios en WhatsApp

## 📋 Resumen

Tu bot de WhatsApp ahora puede **recibir y enviar mensajes de audio**. Esta funcionalidad está completamente integrada con el sistema existente de manejo de medios.

## ✅ Características Implementadas

### 1. **Recibir Audios** 📥

El bot puede recibir audios de los usuarios y:
- ✅ Descargar y guardar el audio localmente en `media/audio/`
- ✅ Enviar notificación por email al equipo
- ✅ Guardar el audio en la base de datos de conversaciones
- ✅ Procesar el mensaje y responder automáticamente
- ✅ Respetar la configuración de `bot_enabled` (si está deshabilitado, solo guarda sin responder)

**Formatos de audio soportados:**
- OGG (formato por defecto de WhatsApp)
- MP3
- M4A/MP4
- WAV
- AAC

### 2. **Enviar Audios** 📤

El bot puede enviar audios a los usuarios usando dos métodos:

#### Método 1: Desde archivo local
```python
# En conversation.py o cualquier handler
await self.send_audio_message(
    to="56912345678",
    audio_path="/ruta/al/audio.ogg"
)
```

#### Método 2: Desde URL pública
```python
await self.send_audio_message(
    to="56912345678",
    audio_url="https://ejemplo.com/audio.mp3"
)
```

## 🗂️ Estructura de Archivos

```
media/
├── audio/                    # 🆕 Audios recibidos
│   ├── {media_id}_{timestamp}.ogg
│   ├── {media_id}_{timestamp}.mp3
│   └── ...
├── received/                 # Imágenes recibidas
├── uploaded/                 # Archivos subidos
└── accommodations/           # Imágenes de alojamientos
```

## 🔧 Archivos Modificados

### 1. `app/utils/media_handler.py`
- ✅ Agregado directorio `AUDIO_DIR` para almacenar audios
- ✅ Actualizado `get_received_media_path()` para soportar tipo "audio"
- ✅ Nuevas funciones:
  - `get_audio_path()` - Obtener ruta para guardar audio
  - `list_audio_files()` - Listar todos los audios guardados

### 2. `app/whatsapp/client.py`
- ✅ Nuevo método `send_audio_message()` para enviar audios
- ✅ Soporta envío por `media_id` o `audio_url`
- ✅ Manejo automático de tipos MIME

### 3. `app/whatsapp/webhook.py`
- ✅ Procesamiento completo de mensajes tipo "audio"
- ✅ Descarga y almacenamiento local de audios
- ✅ Notificaciones por email
- ✅ Integración con el sistema de conversaciones
- ✅ Respeto de configuración `bot_enabled`

### 4. `app/bot/conversation.py`
- ✅ Nuevo método `send_audio_message()` en ConversationManager
- ✅ Detección automática de tipo MIME según extensión
- ✅ Subida automática a WhatsApp antes de enviar

## 📝 Ejemplos de Uso

### Ejemplo 1: Responder con audio a un mensaje específico

```python
async def process_message(self, from_number: str, message_text: str, contact_name: str, message_id: str):
    # ... tu lógica existente ...
    
    # Si el usuario pide información de horarios, responder con audio
    if "horarios" in message_text.lower():
        # Enviar audio con información
        await self.send_audio_message(
            to=from_number,
            audio_path="media/audio/horarios_info.ogg"
        )
        return None  # Ya enviamos respuesta, no enviar texto
    
    # ... resto de tu lógica ...
```

### Ejemplo 2: Enviar audio de bienvenida

```python
async def send_welcome_audio(self, phone_number: str):
    """Enviar audio de bienvenida personalizado"""
    success = await self.send_audio_message(
        to=phone_number,
        audio_path="media/audio/bienvenida_capitan_tomas.ogg"
    )
    
    if success:
        logger.info(f"✅ Audio de bienvenida enviado a {phone_number}")
    else:
        logger.error(f"❌ Error enviando audio a {phone_number}")
```

### Ejemplo 3: Manejar audio recibido con transcripción (futuro)

```python
# En webhook.py, cuando se recibe un audio
elif message_type == "audio":
    # ... código existente de descarga ...
    
    # Futuro: Transcribir audio usando Whisper API o similar
    # transcription = await transcribe_audio(local_audio_path)
    # response = await conversation_manager.process_message(
    #     from_number=from_number,
    #     message_text=transcription,
    #     contact_name=contact_name,
    #     message_id=message_id
    # )
```

## 🎯 Casos de Uso Sugeridos

### 1. **Mensajes de Bienvenida Personalizados**
Envía un audio del Capitán Tomás dando la bienvenida a nuevos clientes.

### 2. **Instrucciones de Navegación**
Envía audios con instrucciones de cómo llegar al punto de encuentro.

### 3. **Confirmaciones de Reserva**
Audio personalizado confirmando la reserva con todos los detalles.

### 4. **Promociones Especiales**
Mensajes de voz promocionando ofertas especiales o eventos.

### 5. **Respuestas a Preguntas Frecuentes**
Audios pregrabados para respuestas comunes (horarios, precios, etc.).

## 🔐 Seguridad y Privacidad

- ✅ Los audios se descargan con autenticación Bearer token
- ✅ Se almacenan localmente en `media/audio/` (no accesibles públicamente)
- ✅ Los nombres de archivo incluyen timestamp para evitar colisiones
- ✅ Se respeta la configuración de `bot_enabled` para privacidad del usuario

## 📊 Base de Datos

Los audios se guardan en la tabla `conversations` con:
- `message_type`: "audio"
- `message_text`: "[Audio recibido]"
- `response_text`: URL o path del audio (si es respuesta)
- `direction`: "incoming" o "outgoing"

## 🚀 Próximos Pasos (Opcional)

### Transcripción de Audio
Integrar con OpenAI Whisper API para transcribir audios recibidos:

```python
import openai

async def transcribe_audio(audio_path: str) -> str:
    """Transcribir audio usando Whisper API"""
    with open(audio_path, "rb") as audio_file:
        transcript = await openai.Audio.atranscribe(
            model="whisper-1",
            file=audio_file
        )
    return transcript["text"]
```

### Síntesis de Voz (Text-to-Speech)
Convertir respuestas de texto a audio automáticamente:

```python
from gtts import gTTS

async def text_to_audio(text: str, output_path: str):
    """Convertir texto a audio"""
    tts = gTTS(text=text, lang='es', slow=False)
    tts.save(output_path)
```

## 🧪 Cómo Probar

1. **Recibir Audio:**
   - Abre WhatsApp en tu teléfono
   - Envía un mensaje de audio al número del bot
   - Verifica que el bot responde
   - Revisa `media/audio/` para ver el archivo descargado

2. **Enviar Audio:**
   - Coloca un archivo de audio en `media/audio/test.ogg`
   - Llama al método desde tu código:
     ```python
     await conversation_manager.send_audio_message(
         to="56912345678",
         audio_path="media/audio/test.ogg"
     )
     ```
   - Verifica que el audio llega al usuario

## ❓ Preguntas Frecuentes

**P: ¿Qué formato de audio debo usar?**
R: WhatsApp recomienda OGG Opus, pero también soporta MP3, M4A, WAV y AAC.

**P: ¿Hay límite de tamaño para los audios?**
R: WhatsApp tiene un límite de 16 MB para archivos multimedia.

**P: ¿Puedo enviar audios largos?**
R: Sí, pero considera que audios muy largos pueden ser molestos. Recomendamos máximo 1-2 minutos.

**P: ¿Los audios se transcriben automáticamente?**
R: No por ahora, pero puedes integrar Whisper API para transcripción automática.

**P: ¿Dónde se guardan los audios recibidos?**
R: En `media/audio/` con el formato `{media_id}_{timestamp}.{extension}`

## 📞 Soporte

Si tienes problemas con la funcionalidad de audios, revisa los logs:
```bash
# Ver logs en tiempo real
tail -f logs/app.log | grep -i audio

# Buscar errores de audio
grep "Error.*audio" logs/app.log
```

---

**¡Ahora tu bot puede hablar! 🎤⚓**

*Creado para HotBoat WhatsApp Bot - Capitán Tomás*
