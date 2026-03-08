# Sistema de Prioridades para Conversaciones

## 📋 Descripción

Se ha implementado un sistema de prioridades para marcar y organizar las conversaciones de WhatsApp. Esto permite separar y priorizar los chats según su urgencia o estado.

## ✨ Características

### Niveles de Prioridad

- **0 (Sin prioridad)**: Estado por defecto, no se muestra ningún badge
- **1 (Alta - Rojo)**: Para clientes que ya compraron o requieren atención inmediata
- **2 (Media - Naranja)**: Para clientes que están a punto de comprar
- **3 (Baja - Amarillo)**: Para clientes ya atendidos o consultas de seguimiento

### Ubicación en la Interfaz

#### 1. **Lista de Conversaciones**
- Los badges de prioridad aparecen al lado del nombre del contacto
- Se muestran justo antes del indicador de mensajes no leídos
- Colores distintivos para identificación rápida:
  - Rojo (#ff4444) para prioridad 1
  - Naranja (#ff9800) para prioridad 2
  - Amarillo (#ffd700) para prioridad 3

#### 2. **Área de Entrada de Mensajes**
- Los botones de prioridad están ubicados en la parte inferior del área de chat
- Se encuentran entre el contador de caracteres y el toggle del bot
- 4 botones disponibles: ➖ (sin prioridad), 1, 2, 3
- El botón activo se resalta con el color correspondiente

## 🚀 Instalación

### 1. Ejecutar la Migración de Base de Datos

```bash
# Asegúrate de que DATABASE_URL esté configurado en tu .env
python run_migration_009.py
```

La migración:
- Agrega el campo `priority` a la tabla `whatsapp_leads`
- Crea un índice para mejorar el rendimiento de las consultas
- Establece el valor por defecto en 0 (sin prioridad)

### 2. Reiniciar el Servidor

```bash
# Detén el servidor actual (Ctrl+C)
# Luego reinicia
python -m uvicorn app.main:app --reload
```

## 📱 Uso

### Asignar Prioridad a una Conversación

1. Abre cualquier conversación haciendo clic en ella
2. En la parte inferior del chat, verás los botones de prioridad
3. Haz clic en el botón correspondiente:
   - **➖**: Sin prioridad
   - **1**: Alta (rojo) - Ya compraron
   - **2**: Media (naranja) - A punto de comprar
   - **3**: Baja (amarillo) - Ya atendidos
4. El cambio se guarda inmediatamente
5. El badge aparecerá en la lista de conversaciones

### Ver Prioridades

- Los badges de prioridad son visibles en la lista de conversaciones
- Aparecen como números circulares con colores distintivos
- No se muestra ningún badge si la conversación no tiene prioridad asignada

## 🔧 Detalles Técnicos

### Backend

**Archivos modificados:**
- `app/db/leads.py`: Funciones para gestionar prioridades
- `app/db/queries.py`: Incluye prioridad en las consultas
- `app/main.py`: Nuevo endpoint `/api/conversations/{phone_number}/priority`

**Nuevo endpoint:**
```
PUT /api/conversations/{phone_number}/priority
Body: { "priority": 1 }  // 0, 1, 2, o 3
```

### Frontend

**Archivos modificados:**
- `app/static/app.js`: Funciones para actualizar y mostrar prioridades
- `app/static/index.html`: Botones de prioridad en el área de entrada
- `app/static/styles.css`: Estilos para badges y botones

**Funciones nuevas en JavaScript:**
- `updatePriority(priority)`: Actualiza la prioridad de la conversación actual
- `updatePriorityUI(priority)`: Actualiza el estado visual de los botones

### Base de Datos

**Nueva columna:**
```sql
ALTER TABLE whatsapp_leads
ADD COLUMN priority INTEGER DEFAULT 0;

CREATE INDEX idx_whatsapp_leads_priority ON whatsapp_leads(priority);
```

## 💡 Casos de Uso

### Ejemplo 1: Cliente que realizó una compra
1. Abrir conversación del cliente
2. Marcar con prioridad 1 (roja)
3. El badge rojo aparecerá en la lista para identificación rápida

### Ejemplo 2: Cliente interesado próximo a comprar
1. Durante la conversación, detectas interés alto
2. Marcar con prioridad 2 (naranja)
3. Facilita seguimiento prioritario del equipo de ventas

### Ejemplo 3: Cliente ya atendido
1. Después de resolver su consulta
2. Marcar con prioridad 3 (amarilla)
3. Mantiene registro sin ocupar espacio visual prioritario

## 📊 Beneficios

- ✅ **Organización visual**: Identifica rápidamente conversaciones importantes
- ✅ **Separación de estados**: Diferencia entre compradores, prospectos y atendidos
- ✅ **Mejora workflow**: Prioriza atención según urgencia
- ✅ **Persistencia**: Las prioridades se guardan en la base de datos
- ✅ **Responsive**: Funciona perfectamente en móvil y escritorio

## 🎨 Diseño Responsive

### Desktop
- Botones compactos en línea horizontal
- Ubicados junto al toggle del bot y botón de envío

### Mobile
- Sección de prioridad en su propia fila
- Botones más grandes (36px) para facilitar el toque
- Fondo destacado para mejor visualización
- Orden: Prioridad → Bot Toggle → Enviar → Contador

## 🔄 Actualizaciones Futuras Posibles

- Filtrado de conversaciones por prioridad
- Ordenamiento automático por prioridad
- Notificaciones para prioridades altas
- Estadísticas de conversiones por prioridad
- Recordatorios automáticos para seguimiento

## 🐛 Solución de Problemas

### Los badges no aparecen en la lista
- Verifica que la migración se haya ejecutado correctamente
- Revisa la consola del navegador para errores JavaScript
- Limpia el caché del navegador (Ctrl+Shift+R)

### Los botones no responden
- Asegúrate de que el servidor esté ejecutándose
- Verifica la conexión a la base de datos
- Revisa los logs del servidor para errores

### Errores de base de datos
- Confirma que `DATABASE_URL` esté configurado
- Verifica que tengas permisos de escritura en la base de datos
- Ejecuta nuevamente la migración si es necesario

## 📝 Notas

- La prioridad es independiente del toggle del bot
- Cada conversación puede tener solo una prioridad a la vez
- Cambiar la prioridad no afecta el historial de mensajes
- Las prioridades son visibles para todos los usuarios de Kia-Ai
