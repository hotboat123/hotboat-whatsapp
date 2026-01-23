# 🌍 Guía de Ambientes - HotBoat WhatsApp

Documentación completa de los ambientes de desarrollo, staging y producción.

---

## 📊 Arquitectura de Ambientes

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           GITHUB REPOSITORY                             │
│                     https://github.com/tu-user/hotboat-whatsapp        │
└─────────────────────────────────────────────────────────────────────────┘
                    │                           │
                    │                           │
            ┌───────┴────────┐          ┌───────┴────────┐
            │   main branch  │          │   beta branch  │
            │  (production)  │          │   (staging)    │
            └───────┬────────┘          └───────┬────────┘
                    │                           │
                    │ Auto Deploy               │ Auto Deploy
                    ▼                           ▼
    ┌─────────────────────────────┐  ┌─────────────────────────────┐
    │   🚀 RAILWAY PRODUCTION     │  │   🧪 RAILWAY STAGING        │
    │                             │  │                             │
    │ URL:                        │  │ URL:                        │
    │ hotboat-production.railway  │  │ hotboat-staging.railway     │
    │                             │  │                             │
    │ Bot: HotBoat Chile          │  │ Bot: HotBoat Chile [BETA]   │
    │ DB: PostgreSQL Production   │  │ DB: PostgreSQL Staging      │
    │ WhatsApp: Número Real       │  │ WhatsApp: Número Prueba     │
    └─────────────────────────────┘  └─────────────────────────────┘
            │                                   │
            │                                   │
            ▼                                   ▼
    ┌─────────────────────────────┐  ┌─────────────────────────────┐
    │   👥 CLIENTES REALES        │  │   🧑‍💻 EQUIPO + PRUEBAS      │
    │                             │  │                             │
    │ - Conversaciones reales     │  │ - Testing de features       │
    │ - Reservas reales           │  │ - Desarrollo seguro         │
    │ - ❌ NO TOCAR EN DESARROLLO │  │ - ✅ Experimentar libremente│
    └─────────────────────────────┘  └─────────────────────────────┘
```

---

## 🎯 Comparación de Ambientes

| Característica | 🚀 Production | 🧪 Staging | 💻 Local |
|----------------|---------------|------------|----------|
| **Branch Git** | `main` | `beta` | cualquiera |
| **Railway Env** | production | staging | - |
| **URL** | `*-production.railway.app` | `*-staging.railway.app` | `localhost:8000` |
| **Base de Datos** | PostgreSQL Production | PostgreSQL Staging | Local DB |
| **WhatsApp Number** | Número real de negocio | Número de prueba | Simulado |
| **Bot Name** | HotBoat Chile | HotBoat Chile [BETA] | Configurable |
| **Clientes** | Reales ✅ | Prueba solo 🧪 | Simulados |
| **Deploy** | Auto al push a `main` | Auto al push a `beta` | Manual |
| **Logs** | `INFO` | `DEBUG` | `DEBUG` |
| **¿Cuándo usar?** | Código 100% probado | Testing antes de prod | Desarrollo activo |

---

## 🔄 Flujo Completo de Desarrollo

```
┌──────────────────────────────────────────────────────────────────────┐
│ FASE 1: DESARROLLO LOCAL                                             │
│                                                                       │
│  💻 Tu Computadora                                                   │
│  git checkout -b feature/nueva-funcionalidad                         │
│  # Desarrollas, pruebas localmente                                   │
│  git commit -m "feat: nueva funcionalidad"                           │
│                                                                       │
│  ✅ Funciona en local? → FASE 2                                      │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ FASE 2: STAGING/BETA                                                 │
│                                                                       │
│  🧪 Railway Staging Environment                                      │
│  git checkout beta                                                   │
│  git merge feature/nueva-funcionalidad                               │
│  git push origin beta                                                │
│                                                                       │
│  → Railway despliega automáticamente                                 │
│  → Pruebas con datos de prueba                                       │
│  → Verificar logs                                                    │
│  → Testing completo                                                  │
│                                                                       │
│  ✅ Todo funciona en staging? → FASE 3                               │
│  ❌ Hay errores? → Volver a FASE 1                                   │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ FASE 3: PRODUCTION                                                   │
│                                                                       │
│  🚀 Railway Production Environment                                   │
│  git checkout main                                                   │
│  git merge beta                                                      │
│  git push origin main                                                │
│                                                                       │
│  → Railway despliega a producción                                    │
│  → Clientes reales usan el bot                                       │
│  → Monitorear logs de producción                                     │
│                                                                       │
│  ✅ ÉXITO! Feature en producción                                     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Setup Inicial (Una sola vez)

### ⚙️ Prerequisitos
- ✅ Cuenta Railway con tu proyecto desplegado
- ✅ GitHub repository configurado
- ✅ Número de WhatsApp Business funcionando

### 📝 Pasos

**1. Crear rama beta:**
```bash
git checkout -b beta
git push -u origin beta
git checkout main
```

**2. Configurar en Railway:**
- Settings → Environments → New Environment
- Name: `staging`, Branch: `beta`

**3. Configurar variables de staging:**
- Copiar de `env.staging.template`
- Importante: `ENVIRONMENT=staging`
- Importante: `BOT_NAME=HotBoat Chile [BETA]`
- Importante: `WHATSAPP_VERIFY_TOKEN` diferente

**4. Crear base de datos staging:**
- Opción A: Nuevo PostgreSQL service en Railway
- Opción B: Schema separado en DB existente

---

## 📚 Documentación Completa

| Documento | Propósito |
|-----------|-----------|
| **QUICK_START_BETA.md** | ⚡ Setup rápido en 5 minutos |
| **AMBIENTE_BETA_SETUP.md** | 📖 Guía completa y detallada |
| **FLUJO_TRABAJO_BETA.md** | 🔄 Flujo de trabajo diario |
| **env.staging.template** | 📋 Variables de entorno para staging |

---

## 🎨 ¿Cómo sé en qué ambiente estoy?

### Visual

**Production:**
```
👤 Usuario: Hola
🤖 Bot: Hola, soy Capitán HotBoat de Hot Boat Villarrica
```

**Staging:**
```
👤 Usuario: Hola  
🤖 Bot: Hola, soy Capitán HotBoat de Hot Boat Villarrica [PRUEBAS]
```

### API Health Check

```bash
# Staging
curl https://hotboat-whatsapp-staging.railway.app/health
{
  "status": "healthy",
  "environment": "staging",
  "environment_status": "🧪 STAGING",
  "bot_name": "HotBoat Chile [BETA]"
}

# Production
curl https://hotboat-whatsapp-production.railway.app/health
{
  "status": "healthy",
  "environment": "production",
  "environment_status": "🚀 PRODUCTION",
  "bot_name": "HotBoat Chile"
}
```

---

## 🚨 Reglas de Seguridad

### ❌ NUNCA en Staging:
- Usar datos de clientes reales
- Enviar mensajes a números de clientes
- Usar base de datos de producción
- Probar con pagos reales

### ✅ SIEMPRE:
- Probar en staging antes de production
- Usar datos de prueba
- Verificar logs después de cada deploy
- Hacer merge de beta a main (no al revés)

---

## 🆘 Troubleshooting

### Problema: "Los dos ambientes responden igual"

**Solución:**
```bash
# Verifica variables en Railway
# Staging debe tener:
ENVIRONMENT=staging
BOT_NAME=HotBoat Chile [BETA]
```

### Problema: "Staging está caído"

**Solución:**
1. Railway → Staging → View Logs
2. Busca errores
3. Verifica variables de entorno
4. Verifica conexión a DB

### Problema: "No puedo hacer push a beta"

**Solución:**
```bash
# Actualiza tu rama local
git checkout beta
git pull origin beta

# Si hay conflictos, resuélvelos
git merge main
```

---

## 💡 Tips Pro

1. **Usa staging generosamente** - Es tu red de seguridad
2. **Commits pequeños** - Más fácil de debugear
3. **Prueba escenarios reales** - Simula flujos completos
4. **Revisa logs siempre** - Antes y después de deploy
5. **Documenta cambios** - En commits y PRs

---

## 📞 Checklist de Deploy a Production

Antes de hacer `git merge beta` en `main`:

- [ ] ✅ Probado completamente en staging
- [ ] ✅ No hay errores en logs de staging
- [ ] ✅ Bot responde correctamente
- [ ] ✅ Disponibilidad funciona
- [ ] ✅ Imágenes se envían/reciben
- [ ] ✅ Dashboard Kia-Ai funciona
- [ ] ✅ No hay data de prueba en el código
- [ ] ✅ Variables de entorno correctas
- [ ] ✅ Equipo notificado del deploy

---

## 🎓 Recursos Adicionales

- [Railway Environments](https://docs.railway.app/deploy/environments)
- [Git Branching Strategy](https://www.atlassian.com/git/tutorials/comparing-workflows)
- [Semantic Versioning](https://semver.org/)

---

**¿Preguntas?** Lee `QUICK_START_BETA.md` para empezar rápido o `AMBIENTE_BETA_SETUP.md` para detalles técnicos.

---

## 🌟 Resumen Ejecutivo

```
DESARROLLO → STAGING → PRODUCTION
   (tu PC)  →  (beta)  →   (main)
   💻       →    🧪     →    🚀
   libre    → pruebas   →  clientes
```

**Tu proceso en 3 pasos:**
1. Desarrolla en `feature/...` → prueba local
2. Merge a `beta` → prueba en staging
3. Merge a `main` → deploy a producción

**Resultado:**
- ✅ Desarrollo sin estrés
- ✅ Cero downtime en producción
- ✅ Clientes siempre atendidos
- ✅ Testing seguro de nuevas features

🎉 **¡Ahora puedes innovar sin miedo!** 🎉
