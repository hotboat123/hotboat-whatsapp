# 🚤 HotBoat WhatsApp Bot

Bot de WhatsApp con IA para Hot Boat Chile - Automatiza consultas, disponibilidad y reservas.

## 🌟 Características

- ✅ **Respuestas automáticas 24/7** con Claude AI
- ✅ **FAQ instantáneo** - Precios, ubicación, horarios
- ✅ **Consulta de disponibilidad** en tiempo real
- ✅ **Base de datos PostgreSQL** - Lee datos de Booknetic
- ✅ **Webhook de WhatsApp** - Recibe y envía mensajes
- ✅ **FastAPI** - API rápida y moderna
- ✅ **Deploy fácil en Railway**

---

## 📋 Requisitos Previos

1. **Cuenta de WhatsApp Business API** (Meta)
2. **API Key de Anthropic** (Claude)
3. **PostgreSQL** (puedes usar el mismo de `hotboat-etl`)
4. **Cuenta de Railway** (para deploy)

---

## 🚀 Setup Local

### 1. Clonar y configurar

```bash
git clone https://github.com/tu-usuario/hotboat-whatsapp.git
cd hotboat-whatsapp
```

### 2. Crear entorno virtual

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Copia `env.example` a `.env`:

```bash
cp env.example .env
```

Edita `.env` con tus credenciales:

```env
# Database (mismo de hotboat-etl)
DATABASE_URL=postgresql://user:password@host:port/dbname

# WhatsApp Business API
WHATSAPP_API_TOKEN=tu_token_aqui
WHATSAPP_PHONE_NUMBER_ID=tu_phone_id
WHATSAPP_BUSINESS_ACCOUNT_ID=tu_account_id
WHATSAPP_VERIFY_TOKEN=tu_token_personalizado

# Anthropic Claude
ANTHROPIC_API_KEY=tu_api_key_aqui
```

### 5. Ejecutar localmente

```bash
python -m uvicorn app.main:app --reload --port 8000
```

El servidor estará en: `http://localhost:8000`

---

## 🔧 Configurar WhatsApp Business API

### Paso 1: Crear App en Meta for Developers

1. Ve a: https://developers.facebook.com/
2. **My Apps** → **Create App**
3. Tipo: **Business**
4. Nombre: `HotBoat WhatsApp Bot`
5. Agrega **WhatsApp** product

### Paso 2: Configurar Webhook

En la configuración de WhatsApp:

1. **Webhook URL**: `https://tu-app.railway.app/webhook`
2. **Verify Token**: El que pusiste en `WHATSAPP_VERIFY_TOKEN`
3. **Webhook fields**: Selecciona `messages`

### Paso 3: Obtener credenciales

1. **Access Token**: En WhatsApp → API Setup
2. **Phone Number ID**: En la misma página
3. **Business Account ID**: En Settings → Business Info

### Paso 4: Probar

Envía un mensaje de WhatsApp a tu número de prueba.

---

## ☁️ Deploy en Railway

### Opción 1: Desde GitHub (Recomendado)

1. Push tu código a GitHub
2. En Railway: **New Project** → **Deploy from GitHub**
3. Selecciona el repo `hotboat-whatsapp`
4. Railway detectará automáticamente FastAPI

### Opción 2: Railway CLI

```bash
# Instalar Railway CLI
npm install -g @railway/cli

# Login
railway login

# Inicializar proyecto
railway init

# Deploy
railway up
```

### Configurar variables en Railway

En Railway → Variables, agrega:

```env
DATABASE_URL=postgresql://... (copiar del service PostgreSQL)
WHATSAPP_API_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_BUSINESS_ACCOUNT_ID=...
WHATSAPP_VERIFY_TOKEN=...
ANTHROPIC_API_KEY=...
PORT=8000
```

### Obtener URL pública

Railway te dará una URL como: `https://hotboat-whatsapp-production.up.railway.app`

Usa esta URL para configurar el webhook en Meta.

---

## 📊 Estructura del Proyecto

```
hotboat-whatsapp/
├── app/
│   ├── main.py              # FastAPI app principal
│   ├── config.py            # Configuración
│   │
│   ├── whatsapp/            # WhatsApp API
│   │   ├── client.py        # Cliente API
│   │   └── webhook.py       # Webhook handler
│   │
│   ├── bot/                 # Lógica del bot
│   │   ├── conversation.py  # Gestor de conversaciones
│   │   ├── ai_handler.py    # Claude AI
│   │   ├── availability.py  # Consulta disponibilidad
│   │   └── faq.py           # Preguntas frecuentes
│   │
│   ├── db/                  # Base de datos
│   │   ├── connection.py    # Conexión PostgreSQL
│   │   └── queries.py       # Queries
│   │
│   └── utils/               # Utilidades
│       └── logger.py        # Logging
│
├── requirements.txt
├── Procfile                 # Railway/Heroku
├── railway.toml             # Config Railway
└── README.md
```

---

## 🧪 Testing

### Test Health Check

```bash
curl http://localhost:8000/health
```

### Test Webhook Verification

```bash
curl "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=tu_token&hub.challenge=test123"
```

### Simular mensaje de WhatsApp

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "56912345678",
            "id": "wamid.test123",
            "timestamp": "1234567890",
            "type": "text",
            "text": {"body": "Hola"}
          }],
          "contacts": [{
            "profile": {"name": "Test User"}
          }]
        }
      }]
    }]
  }'
```

---

## 🤖 Funcionalidades del Bot

### 1. FAQ Automático

Responde instantáneamente a:
- ¿Cuánto cuesta?
- ¿Dónde están ubicados?
- ¿Qué debo traer?
- ¿Cuánto dura?
- Política de cancelación

### 2. Consulta de Disponibilidad

```
Usuario: "¿Tienen disponibilidad para mañana?"
Bot: Consulta la DB y responde con horarios disponibles
```

### 3. Conversación con IA

Para cualquier otra pregunta, Claude AI genera respuestas naturales y contextuales.

---

## 📈 Próximas Mejoras

- [ ] Sistema de reservas completo
- [ ] Pagos por WhatsApp
- [ ] Recordatorios automáticos
- [ ] Dashboard de admin
- [ ] Analytics de conversaciones
- [ ] Multi-idioma (inglés)
- [ ] Integración con calendario

---

## 🔒 Seguridad

- ✅ Tokens en variables de entorno
- ✅ Verificación de webhook
- ✅ Connection pooling para DB
- ✅ Rate limiting (TODO)
- ✅ Logging de todas las interacciones

---

## 📞 Soporte

**Desarrollado para Hot Boat Chile**

- 🌐 Website: https://hotboatchile.com
- 📧 Email: info@hotboatchile.com
- 📱 WhatsApp: +56 9 1234 5678

---

## 📄 Licencia

Propietario - Hot Boat Chile © 2025



