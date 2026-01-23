# ❓ Preguntas Frecuentes - Ambientes Beta/Staging

Respuestas a las preguntas más comunes sobre la configuración y uso de ambientes.

---

## 🤔 Preguntas Generales

### ¿Qué es un ambiente staging/beta?

Es una **copia separada** de tu aplicación donde puedes probar cambios antes de llevarlos a producción. Tiene su propia base de datos, variables de entorno y URL.

### ¿Por qué necesito esto?

Para **probar cambios sin afectar a tus clientes**. Puedes experimentar, romper cosas, y arreglarlas en staging antes de que lleguen a producción.

### ¿Cuánto cuesta?

**Gratis** si usas Railway Environments. Ambos ambientes (staging y production) están en el mismo proyecto de Railway.

### ¿Cuánto tiempo toma configurarlo?

- **Setup inicial:** 15-20 minutos (una sola vez)
- **Uso diario:** 30 segundos extra por feature

---

## 🛠️ Preguntas de Setup

### ¿Necesito dos proyectos en Railway?

**No.** Railway soporta múltiples "Environments" en el mismo proyecto. Un proyecto, dos ambientes.

### ¿Necesito dos bases de datos?

**Sí, recomendado.** Puedes:
- **Opción A:** Crear un segundo PostgreSQL service en Railway (recomendado)
- **Opción B:** Usar el mismo DB pero con schemas separados

### ¿Necesito dos números de WhatsApp?

**No necesariamente:**
- **Opción A:** Usar el mismo número para ambos (más simple)
- **Opción B:** Usar el número de prueba de Meta para staging (ideal)

### ¿Qué pasa si uso el mismo número de WhatsApp?

Funciona, pero ambos ambientes recibirán los mensajes. La diferencia estará en:
- Variables de entorno diferentes
- Base de datos diferentes
- Bot name con [BETA] en staging

### ¿Cómo sé que estoy en staging y no en production?

Varias formas:
1. **URL:** `*-staging.railway.app` vs `*-production.railway.app`
2. **Health check:** Responde `"environment": "staging"`
3. **Bot name:** Incluye [BETA] en staging
4. **Git branch:** `beta` vs `main`

---

## 🔄 Preguntas de Flujo de Trabajo

### ¿Siempre debo probar en staging primero?

**Sí, siempre.** Nunca hagas commit directo a `main`. El flujo es:
```
feature → beta (staging) → main (production)
```

### ¿Qué pasa si hago push directo a main?

Se desplegará directo a producción sin pasar por staging. **No recomendado** excepto para hotfixes urgentes.

### ¿Cómo hago un hotfix urgente?

```bash
# 1. Crear rama desde main
git checkout main
git checkout -b hotfix/descripcion

# 2. Fix y commit
git commit -m "hotfix: descripción"

# 3. Merge a main (excepción)
git checkout main
git merge hotfix/descripcion
git push origin main

# 4. IMPORTANTE: Merge también a beta
git checkout beta
git merge main
git push origin beta
```

### ¿Puedo tener múltiples features en staging al mismo tiempo?

**Sí.** Puedes hacer merge de varias features a `beta` y probarlas todas juntas en staging antes de llevarlas a producción.

### ¿Cómo vuelvo atrás un cambio en staging?

```bash
# Opción 1: Revert del commit
git checkout beta
git revert <commit-hash>
git push origin beta

# Opción 2: Railway dashboard
# Deployments → Select previous version → Redeploy
```

---

## 🗄️ Preguntas de Base de Datos

### ¿Cómo sincronizo datos de production a staging?

**No deberías.** Staging debe tener **datos de prueba**, no datos reales de clientes.

Si necesitas datos similares:
```sql
-- Crear leads de prueba en staging
INSERT INTO leads (phone_number, customer_name, lead_status)
VALUES ('56912345678', 'Test User', 'potential_client');
```

### ¿Puedo usar la misma base de datos con schemas diferentes?

**Sí.** Opción válida si no quieres crear una DB separada:

```sql
-- En tu DB existente
CREATE SCHEMA staging;

-- Replicar estructura
CREATE TABLE staging.conversations (LIKE public.conversations INCLUDING ALL);
CREATE TABLE staging.leads (LIKE public.leads INCLUDING ALL);
-- etc...
```

Luego en Railway staging:
```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname?options=-c%20search_path=staging
```

### ¿Qué pasa si borro datos en staging por error?

**No pasa nada.** Staging tiene datos de prueba, puedes borrar todo y recrearlo sin consecuencias.

---

## 🚀 Preguntas de Deploy

### ¿Cómo funciona el deploy automático?

Railway detecta cuando haces push a una rama:
- Push a `beta` → Deploy automático a staging
- Push a `main` → Deploy automático a production

### ¿Puedo desactivar el deploy automático?

**Sí,** en Railway → Settings → Environments → Selecciona environment → Desactiva auto-deploy.

Pero **no es recomendado**, el deploy automático es una de las ventajas principales.

### ¿Cuánto tarda un deploy?

Típicamente 1-3 minutos dependiendo del tamaño de tu aplicación.

### ¿Cómo veo el progreso del deploy?

Railway → Selecciona environment → **View Logs** o **Deployments**

### ¿Puedo hacer rollback de un deploy?

**Sí:**
1. Railway → Deployments
2. Selecciona versión anterior
3. Click **"Redeploy"**

---

## 🔐 Preguntas de Seguridad

### ¿Es seguro tener dos ambientes?

**Sí,** siempre que:
- Uses variables de entorno diferentes
- No compartas datos de clientes en staging
- Mantengas `WHATSAPP_VERIFY_TOKEN` diferente

### ¿Puedo compartir la URL de staging con mi equipo?

**Sí,** pero asegúrate de que entiendan que es un ambiente de pruebas.

### ¿Qué pasa si alguien envía un mensaje al número de staging?

Si usas número separado: solo afecta staging.
Si usas mismo número: ambos ambientes lo reciben, pero responden según su configuración.

---

## 💰 Preguntas de Costos

### ¿Staging consume recursos adicionales?

**Sí,** pero Railway ofrece un plan gratuito generoso. Dos ambientes pequeños caben en el plan gratuito.

### ¿Cuánto cuesta Railway con dos ambientes?

- **Plan Hobby (Gratis):** $5 de crédito mensual
- **Plan Pro:** $20/mes con $20 de crédito incluido

Típicamente dos ambientes pequeños cuestan ~$10-15/mes en total.

### ¿Puedo apagar staging cuando no lo uso?

**Sí,** pero no es necesario. Railway cobra por uso, no por tiempo activo.

---

## 🧪 Preguntas de Testing

### ¿Cómo pruebo el bot en staging?

1. Envía mensaje al número de staging (si es separado)
2. O envía mensaje y verifica logs de staging
3. Verifica que responde con [BETA] o [PRUEBAS]

### ¿Puedo probar pagos en staging?

**Sí,** pero usa el modo sandbox/test de tu proveedor de pagos. Nunca uses tarjetas reales en staging.

### ¿Cómo simulo diferentes escenarios en staging?

Crea leads de prueba con diferentes estados:
```sql
INSERT INTO leads (phone_number, customer_name, lead_status)
VALUES 
  ('56911111111', 'Cliente Potencial', 'potential_client'),
  ('56922222222', 'Cliente Real', 'customer'),
  ('56933333333', 'Lead Malo', 'bad_lead');
```

---

## 🔧 Preguntas Técnicas

### ¿Puedo usar diferentes versiones de Python en cada ambiente?

**Sí,** pero no es recomendado. Mantén la misma versión para evitar problemas de compatibilidad.

### ¿Cómo actualizo las variables de entorno en staging?

Railway → Selecciona "staging" environment → Variables → Edita

### ¿Las variables de production afectan staging?

**No.** Cada environment tiene sus propias variables completamente separadas.

### ¿Puedo tener diferentes dependencias en staging?

**Técnicamente sí,** pero no es recomendado. Mantén el mismo `requirements.txt` para ambos.

---

## 🆘 Preguntas de Troubleshooting

### "No veo el botón de New Environment en Railway"

**Posibles causas:**
- No tienes permisos de admin en el proyecto
- Tu plan de Railway no soporta múltiples environments
- Necesitas refrescar la página

**Solución:** Verifica tu plan y permisos.

### "Staging y production responden exactamente igual"

**Causa:** Variables de entorno no configuradas correctamente.

**Solución:**
1. Verifica que seleccionaste "staging" al configurar variables
2. Confirma `ENVIRONMENT=staging` en staging
3. Confirma `BOT_NAME` incluye [BETA]
4. Redeploy staging

### "Error de conexión a base de datos en staging"

**Causa:** `DATABASE_URL` incorrecto o DB no existe.

**Solución:**
1. Verifica `DATABASE_URL` en variables de staging
2. Confirma que la DB staging existe
3. Prueba conexión desde Railway logs

### "Deploy no se activa automáticamente"

**Causa:** Environment no conectado a la rama correcta.

**Solución:**
1. Railway → Settings → Environments
2. Verifica que staging está conectado a `beta`
3. Confirma que hiciste push a `beta` (no a otra rama)

### "Recibo mensajes duplicados en WhatsApp"

**Causa:** Ambos ambientes usando el mismo número y webhook.

**Solución:**
- **Opción A:** Usa número de prueba separado para staging
- **Opción B:** Desactiva webhook en uno de los ambientes
- **Opción C:** Usa `WHATSAPP_VERIFY_TOKEN` diferente

---

## 📱 Preguntas de WhatsApp

### ¿Cómo obtengo un número de prueba de WhatsApp?

1. Meta Developers → Tu App → WhatsApp
2. En "API Setup" verás un número de prueba
3. Puedes agregar hasta 5 números para recibir mensajes de prueba

### ¿Puedo usar el mismo token de WhatsApp en ambos ambientes?

**Sí,** `WHATSAPP_API_TOKEN` puede ser el mismo.

**Pero** `WHATSAPP_VERIFY_TOKEN` **debe ser diferente** para cada ambiente.

### ¿Cómo configuro el webhook para staging?

1. Meta Developers → WhatsApp → Configuration
2. Webhook URL: `https://tu-app-staging.railway.app/webhook`
3. Verify Token: El token de staging (diferente de production)

---

## 🎓 Preguntas de Aprendizaje

### ¿Dónde aprendo más sobre git branching?

- [Git Branching Model](https://nvie.com/posts/a-successful-git-branching-model/)
- [Atlassian Git Tutorial](https://www.atlassian.com/git/tutorials)

### ¿Dónde aprendo más sobre Railway?

- [Railway Docs](https://docs.railway.app)
- [Railway Environments](https://docs.railway.app/deploy/environments)

### ¿Hay videos tutoriales?

Busca en YouTube:
- "Railway environments tutorial"
- "Git branching strategy"
- "Staging vs production"

---

## 💡 Preguntas de Mejores Prácticas

### ¿Cuándo debo hacer merge de beta a main?

Cuando:
- ✅ Todo funciona en staging
- ✅ No hay errores en logs
- ✅ Testing completo realizado
- ✅ Equipo aprueba los cambios

### ¿Debo hacer backup antes de deploy a production?

Railway hace backups automáticos, pero es buena práctica:
1. Verificar que staging funciona perfecto
2. Tener plan de rollback
3. Monitorear logs después del deploy

### ¿Cómo organizo mis commits?

Usa [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` Nueva funcionalidad
- `fix:` Corrección de bug
- `refactor:` Mejora de código
- `docs:` Documentación
- `test:` Tests

Ejemplo:
```bash
git commit -m "feat: agregar sistema de pagos"
git commit -m "fix: corregir cálculo de disponibilidad"
```

---

## 🔮 Preguntas Avanzadas

### ¿Puedo tener más de dos ambientes?

**Sí.** Puedes crear:
- `production` (main)
- `staging` (beta)
- `development` (dev)
- `qa` (qa)

Pero para la mayoría de proyectos, staging y production son suficientes.

### ¿Puedo automatizar tests antes del deploy?

**Sí,** usando GitHub Actions o Railway Plugins. Ejemplo:

```yaml
# .github/workflows/test.yml
name: Tests
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: python -m pytest
```

### ¿Puedo usar diferentes dominios para cada ambiente?

**Sí:**
- Production: `bot.tudominio.com`
- Staging: `beta.tudominio.com`

Configura en Railway → Settings → Domains

---

## 📞 ¿Más Preguntas?

Si tu pregunta no está aquí:

1. **Lee la documentación:**
   - [AMBIENTE_BETA_SETUP.md](AMBIENTE_BETA_SETUP.md)
   - [README_AMBIENTES.md](README_AMBIENTES.md)

2. **Revisa troubleshooting:**
   - [README_AMBIENTES.md](README_AMBIENTES.md) sección troubleshooting

3. **Consulta Railway Docs:**
   - [docs.railway.app](https://docs.railway.app)

---

**¿Encontraste la respuesta?** ¡Genial! Ahora puedes configurar tu ambiente staging con confianza 🚀
