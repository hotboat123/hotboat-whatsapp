# 🚀 Instrucciones Rápidas - Sistema de Prioridades

## ⚡ Inicio Rápido (3 pasos)

### 1️⃣ Ejecutar Migración de Base de Datos
```bash
python run_migration_009.py
```
**¿Qué hace?** Agrega el campo de prioridad a tu base de datos.

### 2️⃣ Reiniciar el Servidor
```bash
# Presiona Ctrl+C para detener el servidor
# Luego ejecuta:
python -m uvicorn app.main:app --reload
```

### 3️⃣ Refrescar el Navegador
```
Presiona Ctrl + Shift + R
```
**¿Qué hace?** Limpia el caché y carga los nuevos estilos.

---

## 💡 Cómo Usar

### Marcar una Conversación

1. **Abre cualquier conversación** haciendo clic en ella
2. **Ve a la parte inferior** del área de chat
3. **Haz clic en el botón de prioridad** que desees:
   - **➖** = Sin prioridad
   - **1** = Alta (Rojo) - Ya compraron
   - **2** = Media (Naranja) - A punto de comprar  
   - **3** = Baja (Amarillo) - Ya atendidos

4. **Verás un mensaje de confirmación** ✅
5. **El badge aparece automáticamente** en la lista de conversaciones

### Ver las Prioridades

- Las prioridades aparecen como **números circulares de colores** 
- Se ubican **al lado del nombre** en la lista de conversaciones
- Están **antes del contador** de mensajes no leídos

---

## 🎨 Colores de Prioridades

| Prioridad | Color | Uso Sugerido |
|-----------|-------|--------------|
| **1** 🔴 | Rojo | Clientes que ya compraron |
| **2** 🟠 | Naranja | Clientes a punto de comprar |
| **3** 🟡 | Amarillo | Clientes ya atendidos |
| **➖** ⚪ | Sin color | Sin prioridad asignada |

---

## 📱 En Móvil

Los botones de prioridad aparecen en **su propia fila** para facilitar el uso:

```
┌─────────────────────┐
│ Prioridad:          │
│  [➖] [1] [2] [3]   │ ← Fila dedicada
└─────────────────────┘
```

---

## ✅ Verificar que Funciona

1. Abre una conversación cualquiera
2. Marca con prioridad 1 (botón rojo)
3. Regresa a la lista de conversaciones
4. Deberías ver un **círculo rojo con "1"** junto al nombre

---

## 🐛 Problemas Comunes

### No veo los botones de prioridad
- ✅ Refresca con **Ctrl + Shift + R**
- ✅ Verifica que el servidor esté corriendo
- ✅ Revisa la consola del navegador (F12)

### Los badges no aparecen en la lista
- ✅ Ejecuta `python run_migration_009.py`
- ✅ Reinicia el servidor
- ✅ Refresca el navegador

### Error al hacer clic en los botones
- ✅ Verifica tu conexión a internet
- ✅ Revisa los logs del servidor
- ✅ Asegúrate de que DATABASE_URL esté configurado

---

## 📞 Soporte

Si tienes problemas:
1. Lee **SISTEMA_PRIORIDADES.md** para documentación completa
2. Ejecuta `python test_priority_system.py` para probar el sistema
3. Revisa los logs del servidor para errores

---

## 🎉 ¡Listo!

Ahora puedes organizar tus conversaciones de WhatsApp con el sistema de prioridades.

**Recuerda:**
- 🔴 Prioridad 1 = Clientes que ya compraron
- 🟠 Prioridad 2 = Clientes a punto de comprar
- 🟡 Prioridad 3 = Clientes ya atendidos
