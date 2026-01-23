# 🧪 Configurar Ambiente BETA/STAGING

Guía para crear un ambiente de pruebas separado de producción en Railway.

---

## 📋 ¿Por qué necesitas esto?

- ✅ **Probar cambios** sin afectar clientes reales
- ✅ **Testing seguro** de nuevas funcionalidades
- ✅ **No perder conversaciones** de clientes durante pruebas
- ✅ **Desarrollo más rápido** sin miedo a romper nada

---

## 🎯 Estrategia Recomendada: Railway Environments

Railway soporta **múltiples environments** (staging/production) en el mismo proyecto.

### Ventajas
- ✅ Mismo código, diferentes configuraciones
- ✅ Mismo dashboard de Railway
- ✅ Variables de entorno separadas
- ✅ Deploy independientes
- ✅ **GRATIS** (no necesitas dos proyectos)

---

## 🚀 Opción 1: Railway Environments (RECOMENDADO)

### Paso 1: Crear Structure con Branches

```bash
# Crear rama beta
git checkout -b beta

# Push a GitHub
git push -u origin beta

# Volver a main
git checkout main
```

### Paso 2: Configurar en Railway

1. **Ve a tu proyecto en Railway**
2. Click en tu service (hotboat-whatsapp)
3. **Settings** → **Environments**
4. Verás "production" por defecto

5. **Crear nuevo environment:**
   - Click **"New Environment"**
   - Nombre: `staging` (o `beta`)
   - Branch: `beta`
   - Click **"Create"**

### Paso 3: Configurar Variables por Environment

#### **PRODUCTION** (rama `main`)
```env
# Variables normales de producción
DATABASE_URL=postgresql://...tu-db-prod...
WHATSAPP_API_TOKEN=tu_token_produccion
WHATSAPP_PHONE_NUMBER_ID=tu_numero_produccion
WHATSAPP_VERIFY_TOKEN=tu_verify_token_prod
GROQ_API_KEY=tu_key_groq
BOT_NAME=HotBoat Chile
BUSINESS_NAME=Hot Boat Villarrica
```

#### **STAGING** (rama `beta`)
```env
# OPCIÓN A: Mismo número WhatsApp pero con indicador
DATABASE_URL=postgresql://...tu-db-staging... (crear DB separada)
WHATSAPP_API_TOKEN=tu_token_produccion (puedes usar el mismo)
WHATSAPP_PHONE_NUMBER_ID=tu_numero_produccion (mismo número)
WHATSAPP_VERIFY_TOKEN=tu_verify_token_staging (DIFERENTE!)
GROQ_API_KEY=tu_key_groq
BOT_NAME=HotBoat Chile [BETA]
BUSINESS_NAME=Hot Boat Villarrica [PRUEBAS]
ENVIRONMENT=staging  # Nueva variable

# OPCIÓN B: Número de WhatsApp de prueba separado (IDEAL)
DATABASE_URL=postgresql://...tu-db-staging...
WHATSAPP_API_TOKEN=tu_token_prueba
WHATSAPP_PHONE_NUMBER_ID=tu_numero_prueba
WHATSAPP_VERIFY_TOKEN=tu_verify_token_staging
GROQ_API_KEY=tu_key_groq
BOT_NAME=HotBoat Chile [BETA]
BUSINESS_NAME=Hot Boat Villarrica [PRUEBAS]
ENVIRONMENT=staging
```

### Paso 4: URLs Diferentes

Railway te dará 2 URLs diferentes:

- **Production**: `https://hotboat-whatsapp-production.railway.app`
- **Staging**: `https://hotboat-whatsapp-staging.railway.app`

### Paso 5: Configurar Webhooks en Meta

Si usas OPCIÓN B (número separado):

1. En Meta Developers → WhatsApp
2. Crea una **segunda App** o usa un **número de prueba**
3. Webhook URL: `https://hotboat-whatsapp-staging.railway.app/webhook`
4. Verify Token: El de staging

---

## 🔄 Flujo de Trabajo Diario

### Para desarrollar nueva funcionalidad:

```bash
# 1. Crear rama desde beta
git checkout beta
git pull origin beta
git checkout -b feature/nueva-funcionalidad

# 2. Hacer cambios y commit
# ... editar código ...
git add .
git commit -m "feat: nueva funcionalidad"

# 3. Merge a beta para probar
git checkout beta
git merge feature/nueva-funcionalidad
git push origin beta

# Railway despliega automáticamente a STAGING ✨
```

### Cuando está probado y funciona:

```bash
# 4. Merge a main para producción
git checkout main
git pull origin main
git merge beta
git push origin main

# Railway despliega automáticamente a PRODUCTION ✨
```

---

## 🗄️ Base de Datos Separada (IMPORTANTE)

### Opción A: Base de Datos Completamente Separada (RECOMENDADO)

```bash
# En Railway:
# 1. Agregar nuevo PostgreSQL service
# 2. Llamarlo "PostgreSQL-Staging"
# 3. Conectar solo al environment "staging"
```

**Ventajas:**
- ✅ Datos de prueba totalmente separados
- ✅ No afectas datos reales nunca
- ✅ Puedes resetear staging sin miedo

### Opción B: Mismo DB, Schema Diferente

```sql
-- Crear schema separado en tu DB existente
CREATE SCHEMA staging;

-- Replicar tablas en staging
CREATE TABLE staging.conversations (LIKE public.conversations INCLUDING ALL);
CREATE TABLE staging.carts (LIKE public.carts INCLUDING ALL);
CREATE TABLE staging.leads (LIKE public.leads INCLUDING ALL);
-- etc...
```

Modificar `DATABASE_URL` en staging:
```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname?options=-c%20search_path=staging
```

---

## 🧪 Probar tu Ambiente Beta

### 1. Verificar que staging está corriendo

```bash
curl https://hotboat-whatsapp-staging.railway.app/health
```

### 2. Enviar mensaje de prueba

- Si tienes número separado: envía WhatsApp al número de prueba
- Si usas mismo número: identifica mensajes por `BOT_NAME`

### 3. Ver logs en Railway

Railway → Staging Environment → View Logs

---

## 📊 Comparación de Opciones

| Feature | Railway Environments | Proyecto Separado |
|---------|---------------------|-------------------|
| Costo | Gratis | Gratis |
| Setup | Fácil | Medio |
| Gestión | Simple (1 dashboard) | Complejo (2 dashboards) |
| Variables | Separadas automático | Manual |
| URLs | 2 URLs en mismo proyecto | 2 proyectos diferentes |
| **Recomendación** | ✅ **USAR ESTO** | Solo si necesitas separación total |

---

## 🔐 Tips de Seguridad

1. **Nunca uses datos reales en staging**
2. **Crea leads de prueba** con emails falsos
3. **Documenta qué es beta** en los mensajes del bot
4. **No envíes notificaciones a clientes** desde staging

---

## 🎨 Identificar Visualmente el Ambiente

Modifica `app/main.py` para mostrar el ambiente:

```python
import os
from fastapi import FastAPI

app = FastAPI()

ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

@app.get("/")
async def root():
    return {
        "app": "HotBoat WhatsApp Bot",
        "environment": ENVIRONMENT,
        "status": "🧪 TESTING MODE" if ENVIRONMENT == "staging" else "🚀 PRODUCTION"
    }
```

---

## 🚨 Troubleshooting

### "No veo el botón de New Environment"
- Asegúrate de estar en el plan de Railway que soporta múltiples environments
- Prueba refrescar la página

### "Los dos environments usan las mismas variables"
- Debes configurar variables **POR ENVIRONMENT**
- Railway → Service → Settings → Variables → Selecciona el environment

### "Staging no se despliega automáticamente"
- Verifica que la rama `beta` esté conectada al environment staging
- Railway → Settings → Environments → Staging → Branch: beta

---

## 📚 Recursos

- [Railway Environments Docs](https://docs.railway.app/deploy/environments)
- [Git Branching Strategy](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow)

---

## ✅ Checklist Final

- [ ] Rama `beta` creada y pusheada a GitHub
- [ ] Environment "staging" creado en Railway
- [ ] Variables de entorno configuradas por environment
- [ ] Base de datos separada o schema diferente
- [ ] Webhook configurado (si usas número separado)
- [ ] Primer deploy de prueba exitoso
- [ ] Mensaje de prueba enviado y respondido
- [ ] Logs verificados en Railway

---

**¡Listo! Ahora puedes desarrollar en `beta` sin miedo a romper producción 🎉**

Para cualquier cambio:
1. Desarrolla en rama `feature/...`
2. Merge a `beta` → se despliega a staging
3. Prueba en staging
4. Si funciona → merge a `main` → se despliega a producción

¡Desarrollo seguro y sin estrés! 🚀
