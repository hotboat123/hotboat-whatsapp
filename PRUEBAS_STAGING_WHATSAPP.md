# 📱 Cómo Probar Staging con WhatsApp Real

Guía para probar cambios en staging respondiendo a tu WhatsApp personal antes de llevarlos a production.

---

## 🎯 Objetivo

Poder hacer cambios en la interacción del bot (respuestas, flujos de conversación, etc.) y probarlos en staging con tu WhatsApp personal, sin afectar a clientes en production.

---

## 🔧 Setup Inicial (Una Sola Vez)

### Paso 1: Configurar Tu Número como Tester

1. Ve a [Meta Developers](https://developers.facebook.com/)
2. Tu App → **WhatsApp** → **API Setup**
3. En la sección **"To"**, click **"Manage phone number list"**
4. Click **"Add phone number"**
5. Ingresa tu número personal: `+56977577307`
6. Recibirás un código de verificación en WhatsApp
7. Ingresa el código
8. ✅ Ahora puedes recibir mensajes del número de prueba de Meta

### Paso 2: Configurar Variables en Railway Staging

1. Railway → Tu proyecto → Selecciona **"staging"** environment
2. Ve a **Variables**
3. Asegúrate de tener:

```env
ENVIRONMENT=staging
BOT_NAME=HotBoat Chile [BETA]
BUSINESS_NAME=Hot Boat Villarrica [PRUEBAS]

# El resto pueden ser iguales a production
WHATSAPP_API_TOKEN=tu_token_actual
WHATSAPP_PHONE_NUMBER_ID=tu_numero_id
WHATSAPP_BUSINESS_ACCOUNT_ID=tu_account_id
WHATSAPP_VERIFY_TOKEN=tu_verify_token

# DB separada si tienes
DATABASE_URL=tu_db_staging (o la misma si no tienes separada)
```

---

## 🧪 Flujo de Pruebas (Cada Vez que Quieras Probar)

### Opción A: Cambiar Webhook Manualmente (Simple)

#### 1. Activar Staging

1. Ve a [Meta Developers](https://developers.facebook.com/)
2. Tu App → **WhatsApp** → **Configuration**
3. En **Webhook**, click **"Edit"**
4. Cambia la URL a:
   ```
   https://hotboat-whatsapp-staging-tom.up.railway.app/webhook
   ```
5. **Verify Token:** El mismo que tienes en production (o uno diferente si configuraste uno para staging)
6. Click **"Verify and Save"**

#### 2. Probar

1. Desde tu WhatsApp personal, envía un mensaje a tu número de negocio
2. ✅ Staging recibirá el mensaje y responderá
3. Prueba todas las interacciones que necesites
4. Revisa los logs en Railway → Staging para debug

#### 3. Volver a Production

**IMPORTANTE:** Cuando termines de probar:

1. Ve a Meta Developers → WhatsApp → Configuration
2. Cambia el webhook de vuelta a:
   ```
   https://kia-ai.hotboatchile.com/webhook
   ```
3. Click **"Verify and Save"**
4. ✅ Production vuelve a responder a clientes

⚠️ **CRÍTICO:** Si olvidas este paso, los mensajes de clientes reales irán a staging!

---

### Opción B: Usar Dos Números (Ideal pero Requiere Setup)

Si prefieres tener ambos ambientes funcionando simultáneamente:

#### Setup de Segundo Número:

1. En Meta, solicita un segundo número de WhatsApp Business
2. Configura webhook del número 1 → Production
3. Configura webhook del número 2 → Staging
4. Usa número 1 para clientes, número 2 para pruebas

**Ventaja:** Ambos ambientes funcionan en paralelo
**Desventaja:** Requiere aprobar un segundo número con Meta (puede tardar)

---

## 📋 Checklist de Prueba

Cuando estés probando en staging:

- [ ] Webhook cambiado a staging en Meta
- [ ] Enviar mensaje de prueba desde tu WhatsApp
- [ ] Verificar que staging responde (no production)
- [ ] Probar flujo completo de conversación
- [ ] Revisar logs en Railway → Staging
- [ ] Verificar cambios específicos que hiciste
- [ ] Todo funciona correctamente

**Antes de terminar:**
- [ ] ⚠️ Cambiar webhook de vuelta a production
- [ ] Verificar que production responde normalmente
- [ ] Si todo OK → Merge cambios de beta a main

---

## 🔄 Flujo Completo de Desarrollo

```bash
# 1. Hacer cambios en beta
git checkout beta
# ... editar código ...
git add .
git commit -m "feat: mejorar interacción del bot"
git push origin beta

# 2. Staging se despliega automáticamente (1-2 min)

# 3. Cambiar webhook a staging en Meta

# 4. Probar desde tu WhatsApp personal
# - Enviar mensajes
# - Ver respuestas
# - Verificar logs

# 5. Si funciona bien:
#    a. Cambiar webhook de vuelta a production
#    b. Merge a main
git checkout main
git merge beta
git push origin main

# 6. Production se despliega con los cambios
```

---

## 💡 Tips y Mejores Prácticas

### 1. Usa un Script de Recordatorio

Crea un archivo `WEBHOOK_STATUS.txt` local:

```bash
# Windows
echo PRODUCTION > WEBHOOK_STATUS.txt

# Cuando cambies a staging
echo STAGING > WEBHOOK_STATUS.txt

# Revisa siempre antes de cerrar
type WEBHOOK_STATUS.txt
```

### 2. Identifica Visualmente el Ambiente

El bot en staging responde con `[BETA]` en el nombre, así sabes que estás en staging:

**Production:** "Hola, soy Capitán HotBoat"
**Staging:** "Hola, soy HotBoat Chile [BETA]"

### 3. Webhook Reminder

Puedes crear un recordatorio en tu calendario:
```
Al final del día: Verificar webhook de WhatsApp
```

### 4. Verificación Rápida

Para saber qué ambiente está activo:

**Ver en Meta:**
- Meta Developers → WhatsApp → Configuration → Webhook URL

**URL termina en:**
- `.com/webhook` = Production ✅
- `.railway.app/webhook` = Staging 🧪

---

## 🆘 Troubleshooting

### "No recibo respuesta en staging"

1. Verifica que el webhook está en staging
2. Revisa logs de Railway → Staging
3. Verifica que tu número está en la lista de testers
4. Confirma que staging está desplegado y funcionando

### "Los clientes reportan que el bot no responde"

⚠️ **Posiblemente el webhook está en staging**
1. Ve inmediatamente a Meta Developers
2. Cambia webhook a production
3. Verifica que funciona

### "Staging responde pero con datos viejos"

- El deploy puede tardar 2-3 minutos
- Verifica que hiciste push a `beta`
- Revisa logs de Railway → Staging → Deployments

---

## 📞 URLs de Referencia

**Meta Developers:**
https://developers.facebook.com/

**Railway Dashboard:**
https://railway.app/

**Staging:**
https://hotboat-whatsapp-staging-tom.up.railway.app/

**Production:**
https://kia-ai.hotboatchile.com/

---

## ✅ Resumen

Para probar en staging:

1. **Cambiar webhook** a staging en Meta
2. **Enviar mensajes** desde tu WhatsApp
3. **Probar** todo lo que necesites
4. **IMPORTANTE:** Cambiar webhook de vuelta a production
5. Si todo OK → merge beta a main

**¡Nunca olvides volver el webhook a production!** ⚠️

---

*Guía actualizada: 2026-01-23*
