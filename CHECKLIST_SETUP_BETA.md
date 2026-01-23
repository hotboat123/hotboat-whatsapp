# ✅ Checklist: Setup Ambiente Beta/Staging

Usa este checklist para asegurarte de completar todos los pasos correctamente.

---

## 📋 Pre-requisitos

Antes de empezar, verifica que tienes:

- [ ] Git instalado y configurado
- [ ] Acceso a tu repositorio en GitHub
- [ ] Acceso a Railway dashboard con permisos de admin
- [ ] Tu aplicación funcionando en production actualmente
- [ ] 15-20 minutos de tiempo disponible
- [ ] Acceso a las credenciales de WhatsApp Business API

---

## 🚀 Fase 1: Configuración Local (5 minutos)

### Paso 1.1: Crear Rama Beta

- [ ] Abrir terminal en el directorio del proyecto
- [ ] Verificar que estás en rama `main`: `git branch --show-current`
- [ ] Actualizar main: `git pull origin main`
- [ ] Crear rama beta: `git checkout -b beta`
- [ ] Push a GitHub: `git push -u origin beta`
- [ ] Volver a main: `git checkout main`

**Comando rápido (Windows):**
```bash
./setup_beta.bat
```

**Comando rápido (Mac/Linux):**
```bash
chmod +x setup_beta.sh
./setup_beta.sh
```

### Paso 1.2: Verificar en GitHub

- [ ] Ir a tu repositorio en GitHub
- [ ] Verificar que aparece la rama `beta` en el selector de branches
- [ ] Confirmar que `beta` tiene el mismo código que `main`

---

## ☁️ Fase 2: Configuración en Railway (5 minutos)

### Paso 2.1: Crear Environment

- [ ] Ir a [Railway](https://railway.app)
- [ ] Abrir tu proyecto `hotboat-whatsapp`
- [ ] Click en tu service
- [ ] Ir a **Settings** → **Environments**
- [ ] Click en **"New Environment"**
- [ ] Configurar:
  - [ ] Name: `staging`
  - [ ] Branch: `beta`
- [ ] Click **"Create"**

### Paso 2.2: Verificar Environment Creado

- [ ] Ver que aparece "staging" en la lista de environments
- [ ] Verificar que está conectado a branch `beta`
- [ ] Confirmar que tiene su propia sección de variables

---

## 🔐 Fase 3: Variables de Entorno (5 minutos)

### Paso 3.1: Copiar Template

- [ ] Abrir archivo `env.staging.template` en tu proyecto
- [ ] Copiar todo el contenido

### Paso 3.2: Configurar en Railway Staging

- [ ] En Railway, seleccionar environment **"staging"** (arriba)
- [ ] Ir a **Variables**
- [ ] Agregar cada variable:

**Variables Críticas (DEBEN ser diferentes):**
- [ ] `ENVIRONMENT=staging`
- [ ] `BOT_NAME=HotBoat Chile [BETA]`
- [ ] `BUSINESS_NAME=Hot Boat Villarrica [PRUEBAS]`
- [ ] `WHATSAPP_VERIFY_TOKEN=staging_token_DIFERENTE_de_production`
- [ ] `DATABASE_URL=postgresql://...staging...` (DB separada)
- [ ] `LOG_LEVEL=DEBUG`

**Variables que pueden ser iguales:**
- [ ] `GROQ_API_KEY` (puedes usar la misma)
- [ ] `WHATSAPP_API_TOKEN` (si usas mismo número)
- [ ] `WHATSAPP_PHONE_NUMBER_ID` (si usas mismo número)
- [ ] `WHATSAPP_BUSINESS_ACCOUNT_ID` (si usas mismo número)
- [ ] `PORT=8000`

**Variables opcionales:**
- [ ] `AUTOMATION_PHONE_NUMBERS` (tu número personal para pruebas)
- [ ] `EMAIL_ENABLED=false`
- [ ] `RESEND_API_KEY` (si usas email)

### Paso 3.3: Verificar Variables

- [ ] Revisar que todas las variables estén configuradas
- [ ] Confirmar que `ENVIRONMENT=staging`
- [ ] Confirmar que `WHATSAPP_VERIFY_TOKEN` es diferente de production

---

## 🗄️ Fase 4: Base de Datos (5 minutos)

### Opción A: Base de Datos Separada (RECOMENDADO)

- [ ] En Railway, agregar nuevo service **"PostgreSQL"**
- [ ] Nombrarlo `PostgreSQL-Staging`
- [ ] Conectarlo solo al environment `staging`
- [ ] Copiar `DATABASE_URL` a las variables de staging
- [ ] Ejecutar migraciones en staging (si aplica)

### Opción B: Schema Separado (Alternativa)

- [ ] Conectar a tu DB existente
- [ ] Crear schema: `CREATE SCHEMA staging;`
- [ ] Replicar tablas en schema staging
- [ ] Modificar `DATABASE_URL` para usar schema staging:
  ```
  postgresql://user:pass@host:5432/dbname?options=-c%20search_path=staging
  ```

### Verificación de DB

- [ ] Confirmar que staging tiene su propia base de datos o schema
- [ ] Verificar que no comparte datos con production
- [ ] Probar conexión desde Railway logs

---

## 🌐 Fase 5: Verificación (3 minutos)

### Paso 5.1: Verificar Deploy

- [ ] Railway debería haber desplegado automáticamente staging
- [ ] Ir a Railway → Staging environment → **View Logs**
- [ ] Verificar que no hay errores en el deploy
- [ ] Confirmar que el servicio está corriendo

### Paso 5.2: Health Check

- [ ] Copiar la URL de staging desde Railway
- [ ] Abrir en navegador: `https://tu-app-staging.railway.app/health`
- [ ] Verificar respuesta:
  ```json
  {
    "status": "healthy",
    "environment": "staging",
    "environment_status": "🧪 STAGING",
    "bot_name": "HotBoat Chile [BETA]"
  }
  ```

### Paso 5.3: Comparar con Production

- [ ] Abrir production: `https://tu-app-production.railway.app/health`
- [ ] Verificar que responde diferente:
  ```json
  {
    "status": "healthy",
    "environment": "production",
    "environment_status": "🚀 PRODUCTION",
    "bot_name": "HotBoat Chile"
  }
  ```

---

## 🧪 Fase 6: Primer Test (5 minutos)

### Paso 6.1: Hacer Cambio de Prueba

- [ ] Crear archivo de prueba:
  ```bash
  git checkout beta
  echo "# Test de staging" > TEST_STAGING.md
  git add TEST_STAGING.md
  git commit -m "test: verificar deploy a staging"
  git push origin beta
  ```

### Paso 6.2: Verificar Deploy Automático

- [ ] Ir a Railway → Staging → **Deployments**
- [ ] Verificar que aparece nuevo deployment
- [ ] Esperar a que termine (1-2 minutos)
- [ ] Verificar que el deploy fue exitoso (✅)

### Paso 6.3: Verificar Cambio

- [ ] Refrescar health check de staging
- [ ] Verificar que el servicio sigue funcionando
- [ ] Revisar logs para confirmar que no hay errores

---

## 📱 Fase 7: Test de WhatsApp (Opcional, 5 minutos)

### Si tienes número de prueba separado:

- [ ] Configurar webhook en Meta para staging:
  - Webhook URL: `https://tu-app-staging.railway.app/webhook`
  - Verify Token: El token de staging
- [ ] Enviar mensaje de prueba al número de staging
- [ ] Verificar que el bot responde con "[BETA]" o "[PRUEBAS]"
- [ ] Revisar logs en Railway staging

### Si usas el mismo número:

- [ ] Enviar mensaje de prueba
- [ ] Verificar en logs de staging que recibe el mensaje
- [ ] Confirmar que responde correctamente

---

## 📚 Fase 8: Documentación (2 minutos)

### Leer Documentación Esencial

- [ ] Leer **[QUICK_START_BETA.md](QUICK_START_BETA.md)** completo
- [ ] Revisar **[FLUJO_TRABAJO_BETA.md](FLUJO_TRABAJO_BETA.md)** sección de comandos
- [ ] Guardar **[DIAGRAMA_AMBIENTES.md](DIAGRAMA_AMBIENTES.md)** como referencia

### Compartir con el Equipo

- [ ] Informar al equipo sobre el nuevo flujo
- [ ] Compartir documentación relevante
- [ ] Explicar cuándo usar staging vs production

---

## ✅ Verificación Final

### Checklist de Confirmación

- [ ] ✅ Rama `beta` existe en GitHub
- [ ] ✅ Environment `staging` existe en Railway
- [ ] ✅ Variables de entorno configuradas correctamente en staging
- [ ] ✅ `ENVIRONMENT=staging` en variables de staging
- [ ] ✅ `BOT_NAME` incluye [BETA] en staging
- [ ] ✅ Base de datos separada o schema diferente
- [ ] ✅ Health check de staging responde correctamente
- [ ] ✅ Health check de production responde diferente
- [ ] ✅ Deploy automático funciona (probado con commit de prueba)
- [ ] ✅ Logs de staging sin errores
- [ ] ✅ URLs diferentes para staging y production
- [ ] ✅ Documentación leída y entendida

---

## 🎉 ¡Setup Completo!

Si marcaste todas las casillas, ¡felicitaciones! Tu ambiente beta/staging está listo.

### Próximos Pasos

1. **Practica el flujo de trabajo:**
   ```bash
   git checkout beta
   git checkout -b feature/test
   # Hacer cambios...
   git commit -m "feat: test"
   git checkout beta
   git merge feature/test
   git push origin beta
   # Ver deploy en Railway staging
   ```

2. **Desarrolla tu primera feature en staging**
3. **Cuando funcione, merge a production**

---

## 🆘 Troubleshooting

### ❌ "No veo el environment staging en Railway"

**Solución:**
- Refresca la página
- Verifica permisos de admin en el proyecto
- Intenta crear el environment nuevamente

### ❌ "Staging y production responden igual"

**Solución:**
- Verifica que seleccionaste "staging" al configurar variables
- Confirma `ENVIRONMENT=staging` en variables de staging
- Redeploy staging después de cambiar variables

### ❌ "Error de conexión a base de datos en staging"

**Solución:**
- Verifica `DATABASE_URL` en variables de staging
- Confirma que la DB staging existe
- Revisa logs de Railway para ver el error exacto

### ❌ "Deploy no se activa automáticamente"

**Solución:**
- Verifica que el environment staging está conectado a branch `beta`
- Confirma que hiciste push a `beta` (no a otra rama)
- Revisa Railway → Settings → Environments

---

## 📞 Recursos Adicionales

- **[START_AMBIENTES.md](START_AMBIENTES.md)** - Índice completo
- **[AMBIENTE_BETA_SETUP.md](AMBIENTE_BETA_SETUP.md)** - Guía detallada
- **[FLUJO_TRABAJO_BETA.md](FLUJO_TRABAJO_BETA.md)** - Comandos diarios
- **[README_AMBIENTES.md](README_AMBIENTES.md)** - Arquitectura completa

---

## 💾 Guardar este Checklist

Guarda este archivo para futuras referencias o para configurar staging en otros proyectos.

**¡Éxito con tu desarrollo!** 🚀
