# 🚀 Configuración de Ambientes Beta/Staging

**¡Bienvenido!** Esta guía te ayudará a configurar un ambiente de pruebas (staging/beta) separado de tu ambiente de producción en Railway.

---

## 🎯 ¿Qué vas a lograr?

Después de seguir esta guía tendrás:

✅ **Dos ambientes separados:**
- 🚀 **Production** (`main` branch) - Para tus clientes reales
- 🧪 **Staging** (`beta` branch) - Para pruebas y desarrollo

✅ **Deploy automático** en ambos ambientes

✅ **Desarrollo sin estrés** - Prueba todo en staging antes de production

✅ **Cero downtime** - Clientes nunca afectados por tus pruebas

---

## ⚡ Quick Start (5 minutos)

**¿Quieres empezar ya?** → Lee **[QUICK_START_BETA.md](QUICK_START_BETA.md)**

Este archivo te lleva paso a paso en 5 minutos para tener staging funcionando.

---

## 📚 Documentación Completa

Elige según tu nivel de experiencia y necesidad:

### 1. 🏃‍♂️ Para empezar rápido
**[QUICK_START_BETA.md](QUICK_START_BETA.md)** - 5 minutos
- Comandos exactos a ejecutar
- Configuración mínima
- Primer deploy de prueba

### 2. 📖 Para entender todo
**[AMBIENTE_BETA_SETUP.md](AMBIENTE_BETA_SETUP.md)** - 15 minutos
- Explicación detallada de cada paso
- Opciones de configuración
- Base de datos separada
- Webhook de WhatsApp
- Variables de entorno completas
- Troubleshooting extenso

### 3. 🔄 Para trabajo diario
**[FLUJO_TRABAJO_BETA.md](FLUJO_TRABAJO_BETA.md)** - Referencia rápida
- Comandos git del día a día
- Cómo crear features
- Merge a staging
- Deploy a production
- Casos especiales (hotfixes, rollbacks)

### 4. 🌍 Para visión completa
**[README_AMBIENTES.md](README_AMBIENTES.md)** - Documentación completa
- Arquitectura visual de ambientes
- Comparación production vs staging
- Flujo completo de desarrollo
- Reglas de seguridad
- Checklist de deploy

---

## 🛠️ Archivos de Configuración

### **env.staging.template**
Template de variables de entorno para copiar a Railway staging.

Incluye:
- Variables de base de datos
- Configuración de WhatsApp
- Bot name con [BETA]
- Log level en DEBUG

### **setup_beta.sh / setup_beta.bat**
Scripts automatizados para crear la rama beta.

**Linux/Mac:**
```bash
chmod +x setup_beta.sh
./setup_beta.sh
```

**Windows:**
```bash
setup_beta.bat
```

---

## 🗺️ Roadmap de Lectura Recomendado

### Si eres nuevo:
```
1. START_AMBIENTES.md (este archivo) ← Estás aquí ✓
2. QUICK_START_BETA.md (setup rápido)
3. FLUJO_TRABAJO_BETA.md (comandos diarios)
4. README_AMBIENTES.md (cuando tengas dudas)
```

### Si tienes experiencia con git/Railway:
```
1. QUICK_START_BETA.md (skip al setup)
2. FLUJO_TRABAJO_BETA.md (referencia rápida)
```

### Si quieres entender todo a fondo:
```
1. README_AMBIENTES.md (arquitectura completa)
2. AMBIENTE_BETA_SETUP.md (setup detallado)
3. FLUJO_TRABAJO_BETA.md (trabajo diario)
```

---

## 🎬 Comenzar Ahora

### Paso 0: ¿Listo?

Asegúrate de tener:
- ✅ Git instalado
- ✅ Acceso a tu repositorio en GitHub
- ✅ Acceso a Railway
- ✅ Tu aplicación funcionando en production

### Paso 1: Setup Rápido

```bash
# Ejecutar script de setup
./setup_beta.sh  # Mac/Linux
# o
setup_beta.bat   # Windows
```

### Paso 2: Configurar Railway

1. Ve a [Railway](https://railway.app)
2. Abre tu proyecto
3. Settings → Environments → New Environment
4. Name: `staging`, Branch: `beta`

### Paso 3: Variables de Entorno

Copia variables de **env.staging.template** a Railway Staging.

Importante cambiar:
```env
ENVIRONMENT=staging
BOT_NAME=HotBoat Chile [BETA]
WHATSAPP_VERIFY_TOKEN=staging_token_diferente
```

### Paso 4: Verificar

```bash
curl https://tu-app-staging.railway.app/health
```

Deberías ver:
```json
{
  "environment": "staging",
  "environment_status": "🧪 STAGING",
  "bot_name": "HotBoat Chile [BETA]"
}
```

---

## 📊 Arquitectura Visual Rápida

```
TU COMPUTADORA (desarrollo)
        ↓
    git push to beta
        ↓
🧪 STAGING (Railway)
    - URL: *-staging.railway.app
    - Branch: beta
    - Bot: HotBoat Chile [BETA]
    - DB: PostgreSQL Staging
    ↓
  ¿Funciona? ✅
    ↓
    git merge to main
        ↓
🚀 PRODUCTION (Railway)
    - URL: *-production.railway.app
    - Branch: main
    - Bot: HotBoat Chile
    - DB: PostgreSQL Production
```

---

## 🔥 Flujo de Trabajo Diario (Resumen)

```bash
# 1. Crear feature
git checkout beta
git checkout -b feature/mi-cambio

# 2. Desarrollar
# ... hacer cambios ...
git commit -m "feat: descripción"

# 3. Probar en staging
git checkout beta
git merge feature/mi-cambio
git push origin beta
# Railway auto-deploy a staging ✨

# 4. Deploy a production (cuando esté listo)
git checkout main
git merge beta
git push origin main
# Railway auto-deploy a production ✨
```

---

## 💡 Beneficios Inmediatos

Después del setup tendrás:

1. **Desarrollo sin miedo**
   - Prueba features nuevas sin afectar clientes
   - Experimenta libremente en staging

2. **Testing realista**
   - Ambiente idéntico a producción
   - Base de datos separada para pruebas

3. **Deploy confiable**
   - Siempre pruebas en staging primero
   - Merge a main solo cuando funciona

4. **Rollback fácil**
   - Si algo falla, Railway tiene historial
   - Redeploy versión anterior en 1 click

5. **Equipo más eficiente**
   - QA puede probar en staging
   - Desarrollo y producción separados

---

## 🆘 ¿Necesitas Ayuda?

### Problemas Comunes

**"No puedo crear la rama beta"**
→ Lee [QUICK_START_BETA.md](QUICK_START_BETA.md) sección troubleshooting

**"Railway no muestra el nuevo environment"**
→ Lee [AMBIENTE_BETA_SETUP.md](AMBIENTE_BETA_SETUP.md) sección troubleshooting

**"Los dos ambientes responden igual"**
→ Verifica variables de entorno en Railway por environment

**"¿Cómo hago un hotfix urgente?"**
→ Lee [FLUJO_TRABAJO_BETA.md](FLUJO_TRABAJO_BETA.md) sección "Casos Especiales"

---

## 📈 Próximos Pasos

Después de configurar staging:

1. **Día 1-2: Familiarízate**
   - Practica el flujo de trabajo
   - Haz cambios de prueba en staging
   - Verifica logs en Railway

2. **Día 3-5: Usa regularmente**
   - Desarrolla features nuevas en staging
   - Solo merge a main cuando funcione perfecto

3. **Semana 2+: Automatiza más**
   - Considera tests automáticos
   - CI/CD pipelines
   - Notificaciones de deploy

---

## 🎓 Recursos Adicionales

- [Railway Docs - Environments](https://docs.railway.app/deploy/environments)
- [Git Branching Model](https://nvie.com/posts/a-successful-git-branching-model/)
- [WhatsApp Business API Docs](https://developers.facebook.com/docs/whatsapp)

---

## ✅ Checklist de Setup Completo

Marca cuando completes cada paso:

- [ ] Script setup_beta ejecutado
- [ ] Rama `beta` creada en GitHub
- [ ] Environment "staging" creado en Railway
- [ ] Variables de entorno configuradas en staging
- [ ] Base de datos staging configurada
- [ ] Health check de staging responde correctamente
- [ ] Primer deploy de prueba exitoso
- [ ] Mensaje de WhatsApp de prueba enviado a staging
- [ ] Equipo informado del nuevo flujo de trabajo
- [ ] Documentación leída y entendida

---

## 🎉 ¡Listo para Empezar!

**Siguiente paso:**

→ Abre [QUICK_START_BETA.md](QUICK_START_BETA.md) y configura staging en 5 minutos.

---

**¿Preguntas?** Revisa la documentación en el orden recomendado o busca en troubleshooting.

**¡Éxito con tu desarrollo!** 🚀
