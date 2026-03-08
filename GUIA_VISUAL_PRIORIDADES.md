# 🎨 Sistema de Prioridades - Guía Visual

## 📱 Interfaz Antes vs Después

### ANTES (sin prioridades)
```
┌─────────────────────────────────────┐
│ 💬 Conversaciones                   │
├─────────────────────────────────────┤
│                                     │
│ Juan Pérez        (3)      10:30   │ ← Solo mensajes no leídos
│ Último mensaje aquí...              │
│                                     │
│ María García               09:15   │
│ Hola, necesito info...              │
│                                     │
│ Pedro López       (1)      08:45   │
│ Gracias por la atención             │
│                                     │
└─────────────────────────────────────┘
```

### DESPUÉS (con prioridades)
```
┌─────────────────────────────────────┐
│ 💬 Conversaciones                   │
├─────────────────────────────────────┤
│                                     │
│ Juan Pérez    [1] (3)      10:30   │ ← Badge rojo + no leídos
│ Último mensaje aquí...              │
│                                     │
│ María García  [2]          09:15   │ ← Badge naranja
│ Hola, necesito info...              │
│                                     │
│ Pedro López   [3] (1)      08:45   │ ← Badge amarillo + no leídos
│ Gracias por la atención             │
│                                     │
└─────────────────────────────────────┘
```

---

## 🖱️ Área de Entrada de Mensajes

### Desktop
```
┌──────────────────────────────────────────────────────┐
│ Chat con: Juan Pérez                                 │
├──────────────────────────────────────────────────────┤
│                                                      │
│ [Mensajes del chat aquí...]                         │
│                                                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│ [📎] [🎤] [Escribe tu mensaje aquí...]              │
│                                                      │
│ ┌──────────────────────────────────────────────────┐│
│ │ 0/4096  │  Prioridad: [➖] [1] [2] [3]  │        ││ ← Botones aquí
│ │         │            activo  ↑           │        ││
│ │         │  ☑ 🤖 Bot Activo  │  [Send 📤] │        ││
│ └──────────────────────────────────────────────────┘│
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Mobile (Pantalla más estrecha)
```
┌────────────────────────────┐
│ ← Conversaciones           │
├────────────────────────────┤
│                            │
│ Chat con: Juan Pérez       │
│                            │
│ [Mensajes...]              │
│                            │
├────────────────────────────┤
│                            │
│ [📎] [🎤]                  │
│ [Escribe mensaje...]       │
│                            │
│ ┌────────────────────────┐ │
│ │ Prioridad:             │ │
│ │  [➖] [1] [2] [3]      │ │ ← Fila dedicada
│ │       activo ↑         │ │
│ └────────────────────────┘ │
│                            │
│ ┌────────────────────────┐ │
│ │ ☑ 🤖 Bot Activo        │ │
│ └────────────────────────┘ │
│                            │
│ [     Send 📤       ]      │
│                            │
│ 0/4096                     │
│                            │
└────────────────────────────┘
```

---

## 🎯 Estados de los Botones

### Sin Prioridad (Estado inicial)
```
Prioridad: [➖] [1] [2] [3]
           ^^^^
           Gris - Activo
```

### Prioridad Alta (1)
```
Prioridad: [➖] [1] [2] [3]
                ^^^
              Rojo - Activo
```

### Prioridad Media (2)
```
Prioridad: [➖] [1] [2] [3]
                    ^^^
                Naranja - Activo
```

### Prioridad Baja (3)
```
Prioridad: [➖] [1] [2] [3]
                        ^^^
                    Amarillo - Activo
```

---

## 🔴 Ejemplo: Cliente que Ya Compró (Prioridad 1)

### Antes de Marcar
```
┌─────────────────────────────┐
│ Carlos Martínez    10:45    │
│ Ya hice la transferencia    │
└─────────────────────────────┘
```

### Después de Marcar con Prioridad 1
```
┌─────────────────────────────┐
│ Carlos Martínez [1] 10:45   │ ← Badge rojo
│ Ya hice la transferencia    │
└─────────────────────────────┘
```

**Flujo:**
1. Abres el chat de Carlos
2. Ves su mensaje sobre la transferencia
3. Haces clic en el botón **[1]** (rojo)
4. ✅ Aparece: "Prioridad 1"
5. Badge rojo [1] aparece en la lista

---

## 🟠 Ejemplo: Cliente Interesado (Prioridad 2)

### Antes de Marcar
```
┌─────────────────────────────┐
│ Ana Rodríguez      09:30    │
│ ¿Cuánto cuesta el tour?     │
└─────────────────────────────┘
```

### Después de Marcar con Prioridad 2
```
┌─────────────────────────────┐
│ Ana Rodríguez  [2] 09:30    │ ← Badge naranja
│ ¿Cuánto cuesta el tour?     │
└─────────────────────────────┘
```

**Flujo:**
1. Ana pregunta por precios (buen prospecto)
2. Respondes con la información
3. Marcas con prioridad **[2]** (naranja)
4. ✅ Aparece: "Prioridad 2"
5. Badge naranja [2] para seguimiento

---

## 🟡 Ejemplo: Cliente Ya Atendido (Prioridad 3)

### Antes de Marcar
```
┌─────────────────────────────┐
│ Luis Torres        08:15    │
│ Muchas gracias por todo!    │
└─────────────────────────────┘
```

### Después de Marcar con Prioridad 3
```
┌─────────────────────────────┐
│ Luis Torres    [3] 08:15    │ ← Badge amarillo
│ Muchas gracias por todo!    │
└─────────────────────────────┘
```

**Flujo:**
1. Ya resolviste su consulta
2. Cliente satisfecho
3. Marcas con prioridad **[3]** (amarillo)
4. ✅ Aparece: "Prioridad 3"
5. Badge amarillo [3] para archivo

---

## 💫 Interacción con Mensajes No Leídos

### Prioridad + No Leídos
```
┌───────────────────────────────────┐
│ María Silva   [1] (5)    11:20   │
│                ↑   ↑              │
│            Prioridad   No leídos  │
│ Necesito hablar urgente...        │
└───────────────────────────────────┘
```

### Solo Prioridad (Ya Leído)
```
┌───────────────────────────────────┐
│ Jorge Vega    [2]        10:00   │
│                ↑                  │
│            Prioridad              │
│ Estoy interesado en...            │
└───────────────────────────────────┘
```

### Solo No Leídos (Sin Prioridad)
```
┌───────────────────────────────────┐
│ Sandra López      (2)    09:45   │
│                    ↑              │
│                No leídos          │
│ Hola, buenas tardes               │
└───────────────────────────────────┘
```

---

## 🎬 Animación de Cambio

### Cuando Haces Clic en un Botón

```
[Antes]
Prioridad: [➖] [1] [2] [3]
           ^^^^
           
[Haciendo clic en 1...]

[Después]
Prioridad: [➖] [1] [2] [3]
                ^^^
                ⬆️
          ✅ Prioridad 1
          (Toast notification)
```

---

## 📊 Vista Completa del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Kia-Ai - WhatsApp Management                             │
│ ● Connected                                                  │
├──────────────────┬──────────────────────────┬────────────────┤
│                  │                          │                │
│ 💬 Conversaciones│    Chat Principal        │ 👤 Lead Info   │
│                  │                          │                │
│ [🔄] [✕]        │  Juan Pérez              │  Phone: +56... │
│                  │  56912345678             │  Name: Juan... │
│ [🔍 Buscar...]   │                          │  Status: 🟢    │
│                  │  [← Conversaciones]      │                │
│ ┌──────────────┐ │  [➕ New Message]        │                │
│ │Juan P. [1](3)│ │                          │                │
│ │Hola...       │ │ ┌──────────────────────┐ │                │
│ │        10:30 │ │ │ [Mensajes...]        │ │                │
│ ├──────────────┤ │ │                      │ │                │
│ │Ana R.  [2]   │ │ │                      │ │                │
│ │¿Cuánto...    │ │ └──────────────────────┘ │                │
│ │        09:15 │ │                          │                │
│ ├──────────────┤ │ [📎] [🎤] [Mensaje...]  │                │
│ │Luis T. [3](1)│ │                          │                │
│ │Gracias       │ │ 0/4096                   │                │
│ │        08:45 │ │ Prioridad: [➖][1][2][3] │                │
│ └──────────────┘ │           activo ↑       │                │
│                  │ ☑ 🤖 Bot  [Send 📤]     │                │
│                  │                          │                │
└──────────────────┴──────────────────────────┴────────────────┘
```

---

## ✨ Resumen Visual

### Badges en Lista
- 🔴 **[1]** = Alta - Ya compraron
- 🟠 **[2]** = Media - A punto de comprar
- 🟡 **[3]** = Baja - Ya atendidos
- ⚪ Sin badge = Sin prioridad

### Botones de Selección
```
[➖] = Sin prioridad (gris)
[1]  = Alta (rojo)
[2]  = Media (naranja)
[3]  = Baja (amarillo)
```

### Ubicaciones
1. **Badges**: Al lado del nombre en la lista
2. **Botones**: Parte inferior del área de chat
3. **Desktop**: En línea con bot toggle
4. **Mobile**: Fila dedicada propia

---

¡Disfruta organizando tus conversaciones con el nuevo sistema de prioridades! 🎉
