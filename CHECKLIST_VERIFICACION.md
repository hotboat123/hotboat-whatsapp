# ✅ Checklist de Verificación - Sistema de Prioridades

## 🔍 Antes de Comenzar

- [ ] Tengo acceso a la base de datos (DATABASE_URL configurado)
- [ ] El servidor está corriendo
- [ ] Tengo permisos para ejecutar migraciones
- [ ] He hecho backup de la base de datos (recomendado)

---

## 📦 Paso 1: Instalación

### 1.1 Ejecutar Migración
```bash
python run_migration_009.py
```

**Verificar:**
- [ ] Mensaje: "✅ Migration 009 completed successfully!"
- [ ] No hay errores en la salida
- [ ] Se menciona la columna 'priority' agregada

### 1.2 Verificar Base de Datos (Opcional)
Conecta a tu base de datos y ejecuta:
```sql
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'whatsapp_leads' 
AND column_name = 'priority';
```

**Debe mostrar:**
- [ ] column_name: priority
- [ ] data_type: integer
- [ ] column_default: 0

---

## 🔄 Paso 2: Reiniciar Servidor

### 2.1 Detener Servidor Actual
```bash
# Presiona Ctrl+C en la terminal donde corre el servidor
```

**Verificar:**
- [ ] El servidor se detuvo correctamente
- [ ] No hay procesos colgados

### 2.2 Iniciar Servidor
```bash
python -m uvicorn app.main:app --reload
```

**Verificar:**
- [ ] Mensaje: "Uvicorn running on http://..."
- [ ] No hay errores de importación
- [ ] El servidor responde

---

## 🌐 Paso 3: Verificar en el Navegador

### 3.1 Limpiar Caché
```
Ctrl + Shift + R (Chrome/Firefox)
Cmd + Shift + R (Mac)
```

**Verificar:**
- [ ] Los archivos CSS/JS se recargaron
- [ ] La versión es la correcta (v=20260308priority)

### 3.2 Abrir la Aplicación
Navega a tu URL (ej: `http://localhost:8000`)

**Verificar:**
- [ ] La página carga sin errores
- [ ] No hay errores en la consola (F12)
- [ ] La interfaz se ve correctamente

---

## 🎨 Paso 4: Verificar Interfaz

### 4.1 Lista de Conversaciones
Abre la lista de conversaciones

**Verificar:**
- [ ] Las conversaciones se cargan normalmente
- [ ] Los badges de prioridad NO aparecen aún (normal, no hay prioridades asignadas)
- [ ] El contador de no leídos funciona correctamente

### 4.2 Área de Chat
Abre cualquier conversación

**Verificar:**
- [ ] Los mensajes se cargan correctamente
- [ ] Aparecen los botones de prioridad en la parte inferior
- [ ] Los botones son: **➖ 1 2 3**
- [ ] El botón **➖** está activo (resaltado)
- [ ] Los botones están junto al toggle del bot

### 4.3 Responsive (Mobile)
Reduce el tamaño de la ventana o usa modo móvil (F12 > Toggle device toolbar)

**Verificar:**
- [ ] Los botones de prioridad aparecen en su propia fila
- [ ] Los botones son más grandes (36px)
- [ ] El layout se ve bien en móvil
- [ ] Todo es táctil y fácil de usar

---

## 🧪 Paso 5: Pruebas Funcionales

### 5.1 Asignar Prioridad Alta (1)
1. Abre una conversación
2. Haz clic en el botón **[1]** (rojo)

**Verificar:**
- [ ] Aparece toast: "✅ Prioridad 1"
- [ ] El botón [1] se marca como activo (rojo)
- [ ] No hay errores en consola
- [ ] La interfaz responde inmediatamente

### 5.2 Verificar en Lista
Regresa a la lista de conversaciones

**Verificar:**
- [ ] Aparece un badge rojo **[1]** junto al nombre
- [ ] El badge está ANTES del contador de no leídos
- [ ] El badge es visible y legible
- [ ] El color es rojo (#ff4444)

### 5.3 Asignar Prioridad Media (2)
1. Abre otra conversación
2. Haz clic en el botón **[2]** (naranja)

**Verificar:**
- [ ] Aparece toast: "✅ Prioridad 2"
- [ ] El botón [2] se marca como activo (naranja)
- [ ] Badge naranja [2] aparece en lista
- [ ] Color naranja (#ff9800) correcto

### 5.4 Asignar Prioridad Baja (3)
1. Abre otra conversación
2. Haz clic en el botón **[3]** (amarillo)

**Verificar:**
- [ ] Aparece toast: "✅ Prioridad 3"
- [ ] El botón [3] se marca como activo (amarillo)
- [ ] Badge amarillo [3] aparece en lista
- [ ] Color amarillo (#ffd700) correcto

### 5.5 Quitar Prioridad
1. Abre una conversación con prioridad
2. Haz clic en el botón **[➖]**

**Verificar:**
- [ ] Aparece toast: "✅ Sin prioridad"
- [ ] El botón [➖] se marca como activo
- [ ] El badge desaparece de la lista
- [ ] Todo funciona normalmente

---

## 🔄 Paso 6: Persistencia

### 6.1 Recargar Página
Con algunas conversaciones marcadas con prioridades:
1. Recarga la página (F5)

**Verificar:**
- [ ] Los badges de prioridad siguen apareciendo
- [ ] Los colores son correctos
- [ ] Las prioridades no se perdieron

### 6.2 Abrir Conversación
Abre una conversación que tenga prioridad asignada

**Verificar:**
- [ ] El botón correcto está activo
- [ ] La prioridad se cargó desde la base de datos
- [ ] Todo funciona como esperado

---

## 🔌 Paso 7: Verificar API (Opcional)

### 7.1 Test con cURL
Actualiza la prioridad de una conversación vía API:

```bash
curl -X PUT http://localhost:8000/api/conversations/56912345678/priority \
  -H "Content-Type: application/json" \
  -d '{"priority": 1}'
```

**Verificar:**
- [ ] Respuesta 200 OK
- [ ] JSON: `{"status": "success", "priority": 1, ...}`
- [ ] No hay errores

### 7.2 Test Script (Recomendado)
```bash
python test_priority_system.py
```

**Verificar:**
- [ ] Todos los tests pasan ✅
- [ ] No hay errores ❌
- [ ] Mensaje final: "✨ Test completed!"

---

## 🎯 Paso 8: Casos de Uso Reales

### 8.1 Workflow Completo
Simula un caso de uso real:

1. Cliente envía mensaje
2. Respondes y detectas interés alto
3. Marcas con prioridad 2 (naranja)
4. Cliente confirma compra
5. Cambias a prioridad 1 (rojo)
6. Procesas el pedido
7. Cierras con prioridad 3 (amarillo)

**Verificar:**
- [ ] Los cambios son instantáneos
- [ ] Los badges se actualizan correctamente
- [ ] La experiencia es fluida
- [ ] No hay errores ni lags

---

## 🐛 Paso 9: Verificación de Errores

### 9.1 Consola del Navegador
Abre DevTools (F12) > Console

**Verificar:**
- [ ] No hay errores en rojo
- [ ] Solo logs informativos (si los hay)
- [ ] No hay warnings críticos

### 9.2 Logs del Servidor
Revisa la terminal donde corre el servidor

**Verificar:**
- [ ] No hay tracebacks de Python
- [ ] Solo logs INFO y DEBUG
- [ ] No hay errores de base de datos

### 9.3 Network Tab
En DevTools > Network, haz un cambio de prioridad

**Verificar:**
- [ ] Request a `/api/conversations/.../priority`
- [ ] Status code: 200
- [ ] Response time < 500ms
- [ ] JSON válido en respuesta

---

## 📊 Paso 10: Verificación Final

### 10.1 Todas las Conversaciones
Ve a la lista y verifica que:

**Desktop:**
- [ ] Badges visibles y bien posicionados
- [ ] Colores correctos (rojo/naranja/amarillo)
- [ ] No sobreponen otros elementos
- [ ] Legibles y del tamaño correcto

**Mobile:**
- [ ] Badges visibles en pantalla pequeña
- [ ] Botones táctiles y grandes
- [ ] Layout responsive funciona
- [ ] Todo es usable con el dedo

### 10.2 Diferentes Navegadores (Opcional)
Prueba en diferentes navegadores:

**Chrome:**
- [ ] Funciona correctamente
- [ ] Badges se ven bien
- [ ] Botones responden

**Firefox:**
- [ ] Funciona correctamente
- [ ] Badges se ven bien
- [ ] Botones responden

**Safari (si aplica):**
- [ ] Funciona correctamente
- [ ] Badges se ven bien
- [ ] Botones responden

---

## ✅ Checklist Final

### Instalación y Configuración
- [ ] Migración ejecutada exitosamente
- [ ] Servidor reiniciado
- [ ] Caché del navegador limpiado

### Funcionalidad
- [ ] Botones de prioridad visibles
- [ ] Asignación de prioridades funciona
- [ ] Badges aparecen en lista
- [ ] Colores correctos
- [ ] Persistencia funciona

### UI/UX
- [ ] Diseño responsive
- [ ] Botones táctiles en móvil
- [ ] Toasts de confirmación
- [ ] Sin errores visuales

### Integración
- [ ] Compatible con toggle de bot
- [ ] Compatible con contador de no leídos
- [ ] No rompe funcionalidades existentes
- [ ] Performance aceptable

### Testing
- [ ] Tests automáticos pasan
- [ ] Pruebas manuales completas
- [ ] Sin errores en consola
- [ ] Sin errores en servidor

---

## 🎉 Si Todos los Checks Están Marcados

**¡FELICITACIONES! 🎊**

El sistema de prioridades está:
- ✅ Correctamente instalado
- ✅ Totalmente funcional
- ✅ Listo para uso en producción

---

## 🆘 Si Algo Falla

### Problema: Botones no aparecen
**Solución:**
1. Limpia caché: Ctrl+Shift+R
2. Verifica que el servidor esté corriendo
3. Revisa consola del navegador (F12)

### Problema: Badges no aparecen en lista
**Solución:**
1. Ejecuta: `python run_migration_009.py`
2. Reinicia el servidor
3. Refresca el navegador

### Problema: Error al hacer clic
**Solución:**
1. Verifica conexión a internet
2. Revisa logs del servidor
3. Comprueba que DATABASE_URL esté configurado

### Problema: Prioridades no se guardan
**Solución:**
1. Verifica que la migración se ejecutó
2. Comprueba permisos de base de datos
3. Ejecuta: `python test_priority_system.py`

---

## 📚 Documentación de Referencia

Para más información, consulta:
- `QUICKSTART_PRIORIDADES.md` - Inicio rápido
- `SISTEMA_PRIORIDADES.md` - Documentación completa
- `GUIA_VISUAL_PRIORIDADES.md` - Ejemplos visuales
- `IMPLEMENTACION_COMPLETA.md` - Resumen técnico

---

**Última actualización:** 8 de Marzo, 2026
**Versión del sistema:** 1.0.0
