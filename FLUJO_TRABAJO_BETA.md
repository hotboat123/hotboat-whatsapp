# 🔄 Flujo de Trabajo con Ambiente BETA

Guía rápida para trabajar con los ambientes staging y production.

---

## 📋 Estructura de Branches

```
main (production) ──────────────────►  Railway Production
                                       https://hotboat-whatsapp-production.railway.app
  │
  ├── beta (staging) ────────────►  Railway Staging
  │                                  https://hotboat-whatsapp-staging.railway.app
  │
  └── feature/nueva-funcionalidad
```

---

## 🚀 Flujo Diario de Desarrollo

### 1️⃣ Crear nueva funcionalidad

```bash
# Asegúrate de estar en beta actualizada
git checkout beta
git pull origin beta

# Crea una rama para tu feature
git checkout -b feature/descripcion-corta

# Ejemplo:
git checkout -b feature/agregar-pagos
git checkout -b fix/corregir-disponibilidad
```

### 2️⃣ Desarrollar y probar localmente

```bash
# Activa tu entorno virtual
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# Corre el servidor local
python -m uvicorn app.main:app --reload --port 8000

# Haz tus cambios...
# Prueba localmente...
```

### 3️⃣ Commit y push de tu feature

```bash
git add .
git commit -m "feat: descripción del cambio"
git push origin feature/descripcion-corta

# Opcional: Crea Pull Request en GitHub para revisión
```

### 4️⃣ Merge a BETA para probar en staging

```bash
# Vuelve a beta
git checkout beta

# Merge tu feature
git merge feature/descripcion-corta

# Push a GitHub
git push origin beta

# ✨ Railway despliega AUTOMÁTICAMENTE a staging
```

### 5️⃣ Probar en Staging

```bash
# Revisa logs en Railway dashboard
# Envía mensajes de prueba al bot en staging
# Verifica que todo funciona correctamente

# Accede a tu app:
# https://hotboat-whatsapp-staging.railway.app/health
```

### 6️⃣ Si funciona → Deploy a PRODUCTION

```bash
# IMPORTANTE: Solo haz esto cuando estés 100% seguro

git checkout main
git pull origin main

# Merge desde beta (trae todos los cambios probados)
git merge beta

# Push a producción
git push origin main

# ✨ Railway despliega AUTOMÁTICAMENTE a production
```

---

## 🛡️ Reglas de Oro

### ❌ NUNCA hagas:

1. **Commit directo a `main`**
   ```bash
   # ❌ MAL
   git checkout main
   git add .
   git commit -m "fix rápido"
   git push
   ```

2. **Merge de feature directo a `main`**
   ```bash
   # ❌ MAL
   git checkout main
   git merge feature/nueva-cosa
   ```

3. **Saltarte staging**
   - Siempre prueba en beta/staging primero
   - Nunca asumas que "es un cambio pequeño"

### ✅ SIEMPRE:

1. **Desarrolla en ramas feature**
2. **Merge a `beta` primero**
3. **Prueba en staging**
4. **Luego merge a `main`**

---

## 🔥 Casos Especiales

### Hotfix Urgente en Producción

```bash
# 1. Crea rama desde main
git checkout main
git pull origin main
git checkout -b hotfix/descripcion

# 2. Haz el fix
# ... edita código ...

# 3. Commit
git add .
git commit -m "hotfix: descripción urgente"

# 4. Merge directo a main (excepción!)
git checkout main
git merge hotfix/descripcion
git push origin main

# 5. IMPORTANTE: Merge también a beta para mantener sincronía
git checkout beta
git merge main
git push origin beta

# 6. Limpia la rama hotfix
git branch -d hotfix/descripcion
```

### Rollback si algo sale mal en Production

```bash
# Opción 1: Revert del commit problemático
git checkout main
git revert <commit-hash>
git push origin main

# Opción 2: Railway dashboard
# Railway → Production → Deployments → Redeploy versión anterior
```

### Sincronizar Beta con Main

Si main tiene cambios que beta no tiene (después de un hotfix):

```bash
git checkout beta
git pull origin beta
git merge main
git push origin beta
```

---

## 📊 Verificar en qué ambiente estás

### Localmente (git)
```bash
git branch --show-current
```

### En Railway (API)
```bash
# Staging
curl https://hotboat-whatsapp-staging.railway.app/health

# Production
curl https://hotboat-whatsapp-production.railway.app/health
```

Respuesta incluye:
```json
{
  "status": "healthy",
  "environment": "staging",
  "environment_status": "🧪 STAGING",
  "bot_name": "HotBoat Chile [BETA]"
}
```

---

## 🧪 Testing Checklist

Antes de merge a `main`, verifica en staging:

- [ ] El bot responde mensajes correctamente
- [ ] Las consultas de disponibilidad funcionan
- [ ] El carrito de compras funciona (si aplica)
- [ ] Las imágenes se envían/reciben correctamente
- [ ] No hay errores en los logs de Railway
- [ ] Las notificaciones automáticas funcionan
- [ ] El dashboard Kia-Ai carga correctamente

---

## 🎨 Identificar Visualmente el Ambiente

### En el bot
- **Production**: "Hola, soy Capitán HotBoat"
- **Staging**: "Hola, soy Capitán HotBoat [BETA]"

### En la URL
- **Production**: `hotboat-whatsapp-production.railway.app`
- **Staging**: `hotboat-whatsapp-staging.railway.app`

### En los logs
```
[PRODUCTION] Mensaje recibido de +56912345678
[STAGING] Mensaje recibido de +56912345678
```

---

## 📈 Flujo Completo Visual

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Desarrollo Local                                          │
│    feature/nueva-funcionalidad                               │
│    ↓ test local, commit                                      │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Staging/Beta Environment                                  │
│    beta branch → Railway Staging                             │
│    ↓ test en staging, verificar                              │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Production                                                │
│    main branch → Railway Production                          │
│    ✅ Todo funciona, clientes felices                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 💡 Tips

1. **Desarrolla con confianza** - staging es tu red de seguridad
2. **Commitea frecuentemente** - commits pequeños son mejores
3. **Mensajes de commit claros**:
   - `feat: nueva funcionalidad`
   - `fix: corrección de bug`
   - `refactor: mejora de código`
   - `docs: actualización de documentación`

4. **Prueba escenarios reales** en staging antes de production

5. **Revisa logs en Railway** después de cada deploy

---

## 📚 Comandos Útiles

```bash
# Ver en qué rama estás
git branch --show-current

# Ver estado de cambios
git status

# Ver historial de commits
git log --oneline --graph --all

# Ver diferencias entre beta y main
git diff beta..main

# Ver qué cambios hay en remote
git fetch
git log --oneline origin/beta..beta

# Limpiar ramas feature viejas
git branch -d feature/nombre-viejo
```

---

**¿Preguntas o dudas?** Revisa `AMBIENTE_BETA_SETUP.md` para más detalles técnicos.
