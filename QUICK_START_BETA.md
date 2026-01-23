# 🚀 Quick Start - Ambiente BETA

Configuración rápida en 5 minutos.

---

## ⚡ Paso a Paso

### 1. Crear rama beta (1 minuto)

**Windows:**
```bash
./setup_beta.bat
```

**Mac/Linux:**
```bash
chmod +x setup_beta.sh
./setup_beta.sh
```

O manualmente:
```bash
git checkout -b beta
git push -u origin beta
git checkout main
```

---

### 2. Configurar en Railway (2 minutos)

1. Ve a [Railway](https://railway.app)
2. Abre tu proyecto `hotboat-whatsapp`
3. Click en tu service → **Settings** → **Environments**
4. Click **"New Environment"**:
   - Name: `staging`
   - Branch: `beta`
   - Click **Create**

---

### 3. Variables de Entorno (2 minutos)

En Railway → Staging Environment → Variables:

**Copia de `env.staging.template`:**

```env
ENVIRONMENT=staging
DATABASE_URL=postgresql://...staging...
WHATSAPP_API_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_BUSINESS_ACCOUNT_ID=...
WHATSAPP_VERIFY_TOKEN=staging_token_DIFERENTE
GROQ_API_KEY=...
BOT_NAME=HotBoat Chile [BETA]
BUSINESS_NAME=Hot Boat Villarrica [PRUEBAS]
PORT=8000
LOG_LEVEL=DEBUG
```

**Importante:**
- `ENVIRONMENT=staging` - identifica el ambiente
- `BOT_NAME` con [BETA] - para saber que es prueba
- `WHATSAPP_VERIFY_TOKEN` - DEBE ser diferente de production

---

### 4. Verificar (30 segundos)

```bash
# Staging
curl https://hotboat-whatsapp-staging.railway.app/health

# Debería responder:
{
  "status": "healthy",
  "environment": "staging",
  "environment_status": "🧪 STAGING",
  "bot_name": "HotBoat Chile [BETA]"
}
```

---

### 5. Primer Test (30 segundos)

```bash
# Hacer un cambio de prueba
git checkout beta
echo "# Test" >> TEST.md
git add TEST.md
git commit -m "test: primer deploy a staging"
git push origin beta

# Railway despliega automáticamente
# Revisa logs en Railway dashboard
```

---

## 🎯 Flujo de Trabajo Diario

```bash
# 1. Crear feature
git checkout beta
git checkout -b feature/mi-cambio

# 2. Hacer cambios...
git add .
git commit -m "feat: descripción"

# 3. Probar en staging
git checkout beta
git merge feature/mi-cambio
git push origin beta
# → Railway despliega a staging

# 4. Si funciona → producción
git checkout main
git merge beta
git push origin main
# → Railway despliega a production
```

---

## 📊 URLs Importantes

| Ambiente | URL | Branch |
|----------|-----|--------|
| 🧪 Staging | `https://hotboat-whatsapp-staging.railway.app` | `beta` |
| 🚀 Production | `https://hotboat-whatsapp-production.railway.app` | `main` |

---

## 🆘 Problemas Comunes

### "No veo staging en Railway"
- Refresca la página
- Verifica que tengas permisos de admin

### "Staging usa las mismas variables que production"
- Las variables son POR ENVIRONMENT
- Ve a Variables → Selecciona "staging" arriba

### "Los dos ambientes responden igual"
- Verifica `ENVIRONMENT=staging` en variables de staging
- Verifica `BOT_NAME` incluye [BETA]

---

## 📚 Más Info

- **Configuración completa**: `AMBIENTE_BETA_SETUP.md`
- **Flujo de trabajo**: `FLUJO_TRABAJO_BETA.md`
- **Railway Docs**: https://docs.railway.app/deploy/environments

---

**¡Listo! Ahora puedes desarrollar sin miedo 🎉**
