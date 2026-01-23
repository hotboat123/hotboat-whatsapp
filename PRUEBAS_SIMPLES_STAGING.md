# 🎯 Pruebas Simples en Staging (Sin Cambiar Webhooks)

La forma más simple de probar cambios en staging sin tocar configuración de Facebook.

---

## 💡 Cómo Funciona

```
1. Tu WhatsApp → Webhook → Production (recibe, guarda, NO responde)
                                ↓
                        Base de Datos (compartida)
                                ↓
2. Abres Kia-Ai Staging → Ves el mensaje
3. Staging responde (con código nuevo) → Cliente recibe respuesta
```

**Ventaja:** No necesitas cambiar NADA en Facebook. Todo se maneja por variables de Railway.

---

## ⚡ Setup Rápido (2 minutos)

### En Railway Production

1. Railway → Tu proyecto → Selecciona **"production"**
2. **Variables** → Agregar nueva variable:
   ```env
   ENABLE_AUTO_RESPONSES=false
   ```
3. Guarda → Railway redespliega (1-2 min)

### En Railway Staging

1. Railway → Tu proyecto → Selecciona **"staging"**
2. **Variables** → Agregar nueva variable:
   ```env
   ENABLE_AUTO_RESPONSES=true
   ```
3. Guarda → Railway redespliega (1-2 min)

---

## 🧪 Cómo Usar

### 1. Hacer Cambios en Staging

```bash
git checkout beta
# Edita código (respuestas del bot, flujos, etc.)
git add .
git commit -m "feat: mejorar respuestas del bot"
git push origin beta
# Railway despliega staging automáticamente (2-3 min)
```

### 2. Probar

1. **Desde tu WhatsApp personal**, envía un mensaje a tu número de negocio:
   ```
   "Hola, ¿tienen disponibilidad para mañana?"
   ```

2. **Production** recibe el mensaje pero **NO responde** (porque `ENABLE_AUTO_RESPONSES=false`)
   
3. **Abre Kia-Ai de Staging:**
   ```
   https://hotboat-whatsapp-staging-tom.up.railway.app/
   ```

4. **Verás el mensaje** en la lista de conversaciones (comparten la misma DB)

5. **Responde desde Kia-Ai de Staging:**
   - Click en la conversación
   - El bot generará una respuesta usando el código de staging
   - Click "Send"
   - ✅ Tu WhatsApp recibirá la respuesta

6. **Prueba el flujo completo:**
   - Sigue enviando mensajes desde tu WhatsApp
   - Production los recibe y guarda (pero no responde)
   - Tú respondes desde Kia-Ai de staging
   - Pruebas todas las interacciones que necesites

### 3. Cuando Termines de Probar

Si los cambios funcionan bien:

```bash
# Llevar cambios a production
git checkout main
git merge beta
git push origin main

# Reactivar respuestas automáticas en production
# Railway → Production → Variables:
ENABLE_AUTO_RESPONSES=true
```

---

## 📊 Estados del Sistema

### Modo Normal (Production Activa)

```
PRODUCTION: ENABLE_AUTO_RESPONSES=true
   ↓
WhatsApp → Production → Bot responde automáticamente ✅
```

### Modo Testing (Staging Activa)

```
PRODUCTION: ENABLE_AUTO_RESPONSES=false
STAGING: ENABLE_AUTO_RESPONSES=true
   ↓
WhatsApp → Production → Guarda mensaje, NO responde ❌
         → Staging (Kia-Ai) → Tú respondes manualmente con código nuevo ✅
```

---

## 💡 Ventajas de Este Método

### ✅ Simple
- No cambias webhooks
- No configuras números adicionales
- Solo cambias una variable en Railway

### ✅ Seguro
- Production sigue recibiendo mensajes
- Los mensajes se guardan en la DB
- No pierdes ningún mensaje de clientes

### ✅ Realista
- Pruebas con conversaciones reales
- Misma base de datos
- Mismo flujo de trabajo

### ✅ Rápido
- Toggle on/off en segundos
- No esperas aprobaciones de Meta
- Desarrollas más rápido

---

## 🔄 Flujo Completo de Desarrollo

```bash
# 1. Desactivar auto-respuestas en production
Railway → Production → ENABLE_AUTO_RESPONSES=false

# 2. Hacer cambios en beta
git checkout beta
# ... editar código ...
git commit -m "feat: nuevo flujo de conversación"
git push origin beta

# 3. Probar en staging
- Enviar mensajes desde tu WhatsApp
- Responder desde Kia-Ai de staging
- Verificar que todo funciona

# 4. Si funciona bien:
# a. Merge a production
git checkout main
git merge beta
git push origin main

# b. Reactivar auto-respuestas
Railway → Production → ENABLE_AUTO_RESPONSES=true

# 5. ✅ Production ahora tiene el código nuevo
```

---

## 📝 Checklist de Prueba

- [ ] ENABLE_AUTO_RESPONSES=false en production
- [ ] ENABLE_AUTO_RESPONSES=true en staging
- [ ] Cambios commiteados y pusheados a beta
- [ ] Staging desplegado (verificar en Railway)
- [ ] Mensaje enviado desde WhatsApp personal
- [ ] Mensaje visible en Kia-Ai de staging
- [ ] Respuesta enviada desde staging funciona
- [ ] Flujo completo probado
- [ ] Todo funciona correctamente
- [ ] Merge a main realizado
- [ ] ENABLE_AUTO_RESPONSES=true restaurado en production

---

## 🆘 Troubleshooting

### "No veo el mensaje en Kia-Ai de staging"

**Posible causa:** Staging y production usan bases de datos diferentes.

**Solución:** Verifica que ambos usen la misma `DATABASE_URL`, o al menos que staging tenga acceso a la DB de production.

### "Staging no responde cuando envío mensaje"

**Esto es correcto.** Staging no recibe el webhook. Debes responder **manualmente** desde la interfaz Kia-Ai de staging.

### "Los clientes no reciben respuestas"

**Correcto.** Mientras `ENABLE_AUTO_RESPONSES=false` en production, los clientes no recibirán respuestas automáticas. Esto es temporal para testing.

**IMPORTANTE:** Recuerda reactivarlo cuando termines de probar:
```env
ENABLE_AUTO_RESPONSES=true
```

---

## ⚠️ Recordatorios Importantes

1. **No dejes production desactivada** mucho tiempo
   - Los clientes no recibirán respuestas automáticas
   - Solo desactiva mientras estás probando activamente

2. **Avisa a tu equipo** cuando desactives production
   - Alguien debe estar respondiendo manualmente
   - O hazlo en horarios de baja demanda

3. **Reactiva production** cuando termines
   - No olvides volver `ENABLE_AUTO_RESPONSES=true`
   - Verifica que el bot responde normalmente

---

## ✅ Resumen

**Para probar cambios sin cambiar webhooks:**

1. **Desactivar** auto-respuestas en production
   ```
   ENABLE_AUTO_RESPONSES=false
   ```

2. **Activar** auto-respuestas en staging
   ```
   ENABLE_AUTO_RESPONSES=true
   ```

3. **Probar** desde Kia-Ai de staging

4. **Reactivar** production cuando termines
   ```
   ENABLE_AUTO_RESPONSES=true
   ```

**¡Es así de simple!** 🎉

---

*Método actualizado: 2026-01-23*
*Sin configuraciones adicionales en Facebook*
