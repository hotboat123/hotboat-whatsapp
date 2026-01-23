# 📝 Resumen: Ambiente Beta/Staging Configurado

## 🎯 Lo que acabas de recibir

Se ha creado una **guía completa** para configurar un ambiente de pruebas (staging/beta) separado de tu ambiente de producción en Railway.

---

## 📚 Archivos Creados

### 🚀 Para Empezar
1. **START_AMBIENTES.md** - Punto de entrada, índice completo
2. **QUICK_START_BETA.md** - Setup rápido en 5 minutos

### 📖 Documentación Detallada
3. **AMBIENTE_BETA_SETUP.md** - Guía completa paso a paso
4. **FLUJO_TRABAJO_BETA.md** - Comandos y flujo de trabajo diario
5. **README_AMBIENTES.md** - Arquitectura y visión completa

### 🛠️ Configuración
6. **env.staging.template** - Variables de entorno para staging
7. **setup_beta.sh** - Script automatizado (Linux/Mac)
8. **setup_beta.bat** - Script automatizado (Windows)

### 📝 Resumen
9. **RESUMEN_AMBIENTES.md** - Este archivo

---

## 🎬 Cómo Empezar

### Opción 1: Setup Rápido (5 min)
```bash
# 1. Lee la guía rápida
Abre: QUICK_START_BETA.md

# 2. Ejecuta el script
./setup_beta.bat  # Windows
./setup_beta.sh   # Mac/Linux

# 3. Configura en Railway
- Settings → Environments → New Environment
- Name: staging, Branch: beta

# 4. Copia variables de env.staging.template
```

### Opción 2: Lectura Completa (20 min)
```bash
# 1. Lee el índice
Abre: START_AMBIENTES.md

# 2. Sigue el roadmap recomendado
- QUICK_START_BETA.md
- FLUJO_TRABAJO_BETA.md
- README_AMBIENTES.md (referencia)
```

---

## 🌟 Beneficios Inmediatos

Una vez configurado tendrás:

### ✅ Dos Ambientes Separados
- **🚀 Production** (rama `main`) - Clientes reales
- **🧪 Staging** (rama `beta`) - Pruebas y desarrollo

### ✅ Deploy Automático
- Push a `beta` → Railway despliega a staging
- Push a `main` → Railway despliega a production

### ✅ Desarrollo Sin Estrés
- Prueba todo en staging primero
- Cero riesgo para clientes
- Experimenta libremente

### ✅ Flujo Profesional
```
Desarrollo → Staging → Production
   (local)  →  (beta)  →   (main)
     💻     →    🧪     →    🚀
```

---

## 🔄 Flujo de Trabajo Diario

```bash
# 1. Crear feature
git checkout beta
git checkout -b feature/mi-cambio

# 2. Desarrollar y commit
git add .
git commit -m "feat: nueva funcionalidad"

# 3. Probar en staging
git checkout beta
git merge feature/mi-cambio
git push origin beta
# ✨ Railway auto-deploy a staging

# 4. Si funciona → Production
git checkout main
git merge beta
git push origin main
# ✨ Railway auto-deploy a production
```

---

## 📊 Comparación Rápida

| | 🚀 Production | 🧪 Staging |
|---|---|---|
| **Branch** | `main` | `beta` |
| **URL** | `*-production.railway.app` | `*-staging.railway.app` |
| **Bot Name** | HotBoat Chile | HotBoat Chile [BETA] |
| **Clientes** | Reales | Prueba |
| **Deploy** | Auto al push a main | Auto al push a beta |

---

## 🛠️ Configuración Técnica

### Variables Clave en Staging

```env
ENVIRONMENT=staging
BOT_NAME=HotBoat Chile [BETA]
BUSINESS_NAME=Hot Boat Villarrica [PRUEBAS]
WHATSAPP_VERIFY_TOKEN=staging_token_DIFERENTE
DATABASE_URL=postgresql://...staging...
LOG_LEVEL=DEBUG
```

### Railway Environments

```
Railway Project
├── Service: hotboat-whatsapp
    ├── Environment: production (main)
    │   └── Variables: production values
    └── Environment: staging (beta)
        └── Variables: staging values
```

---

## 🎯 Próximos Pasos

### Inmediato (Hoy)
1. ✅ Lee **START_AMBIENTES.md**
2. ✅ Ejecuta **setup_beta.bat/sh**
3. ✅ Configura Railway environment
4. ✅ Copia variables de **env.staging.template**
5. ✅ Verifica con health check

### Corto Plazo (Esta Semana)
1. Practica el flujo de trabajo
2. Haz un cambio de prueba en staging
3. Verifica logs en Railway
4. Familiarízate con los comandos

### Mediano Plazo (Próximas Semanas)
1. Usa staging para todas las features nuevas
2. Solo merge a main cuando funcione perfecto
3. Documenta tus propios procesos
4. Comparte el flujo con tu equipo

---

## 💡 Tips Importantes

### ✅ Hacer Siempre
- Probar en staging antes de production
- Verificar logs después de cada deploy
- Usar datos de prueba en staging
- Hacer commits descriptivos

### ❌ Nunca Hacer
- Commit directo a `main`
- Saltarte staging
- Usar datos de clientes en staging
- Merge sin probar

---

## 🆘 Ayuda Rápida

### ¿Cómo sé en qué ambiente estoy?

```bash
# Git
git branch --show-current

# API
curl https://tu-app-staging.railway.app/health
# Respuesta incluye "environment": "staging"
```

### ¿Cómo veo los logs?

```
Railway Dashboard → Service → Select Environment → View Logs
```

### ¿Cómo hago rollback?

```
Railway Dashboard → Deployments → Select previous version → Redeploy
```

---

## 📞 Documentación de Referencia

| Archivo | Cuándo Usarlo |
|---------|---------------|
| **START_AMBIENTES.md** | Primera vez, índice general |
| **QUICK_START_BETA.md** | Setup inicial rápido |
| **AMBIENTE_BETA_SETUP.md** | Configuración detallada |
| **FLUJO_TRABAJO_BETA.md** | Día a día, comandos git |
| **README_AMBIENTES.md** | Arquitectura, troubleshooting |
| **env.staging.template** | Variables de entorno |

---

## 🎉 ¡Éxito!

Con esta configuración podrás:

- ✅ Desarrollar nuevas features sin miedo
- ✅ Probar exhaustivamente antes de production
- ✅ Mantener clientes siempre atendidos
- ✅ Iterar rápidamente con confianza
- ✅ Rollback fácil si algo falla

---

## 🚀 Comienza Ahora

**Siguiente paso:**

→ Abre **[START_AMBIENTES.md](START_AMBIENTES.md)** y sigue la guía

---

## 📈 Mejoras al Código

También se hicieron mejoras al código para soportar múltiples ambientes:

### `app/config.py`
```python
# Nuevas propiedades
@property
def is_production(self) -> bool:
    return self.environment.lower() == "production"

@property
def is_staging(self) -> bool:
    return self.environment.lower() in ["staging", "beta"]
```

### `app/main.py`
```python
# Health check ahora muestra el ambiente
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "environment": settings.environment,
        "environment_status": "🚀 PRODUCTION" if settings.is_production else "🧪 STAGING",
        "bot_name": settings.bot_name
    }
```

---

## ✅ Checklist Final

Antes de empezar, asegúrate de tener:

- [ ] Git instalado y configurado
- [ ] Acceso a GitHub repository
- [ ] Acceso a Railway dashboard
- [ ] Aplicación funcionando en production
- [ ] 15 minutos de tiempo disponible

---

**¡Todo listo! Comienza con START_AMBIENTES.md** 🚀

---

*Documentación creada: 2026-01-19*
*Versión: 1.0*
