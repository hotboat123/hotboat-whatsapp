# 🛒 Guía del Sistema de Carrito HotBoat

## 📋 Resumen

El sistema de carrito permite a los usuarios:
- Agregar reservas (fecha, horario, número de personas)
- Agregar extras (tablas, bebidas, decoraciones, etc.)
- Ver el carrito en cualquier momento
- Eliminar items del carrito
- Confirmar la compra

## 🎯 Comandos Disponibles

### Ver Carrito
```
carrito
ver carrito
mi carrito
qué tengo
```

### Agregar Extras
```
agregar [nombre del extra]
quiero [nombre del extra]
necesito [nombre del extra]
```

**Ejemplos:**
- "agregar tabla grande"
- "quiero jugo natural"
- "necesito transporte"
- "agregar modo romántico"

### Agregar Reserva
Después de consultar disponibilidad, el usuario puede:
- Responder con la fecha y horario que quiere
- O decir "reservar [fecha] [horario] [personas]"

**Ejemplo:**
- "reservar 15 de febrero 10:00 4 personas"

### Eliminar Item
```
eliminar [número]
```

El número corresponde al item en el carrito.

### Vaciar Carrito
```
vaciar
limpiar
borrar carrito
```

### Confirmar Compra
```
confirmar
confirmo
pagar
comprar
finalizar
```

## 💰 Extras Disponibles

| Extra | Precio |
|-------|--------|
| Tabla Grande (4 personas) | $25.000 |
| Tabla Pequeña (2 personas) | $20.000 |
| Jugo Natural 1L | $10.000 |
| Lata Bebida | $2.900 |
| Agua Mineral 1.5L | $2.500 |
| Helado Individual | $3.500 |
| Modo Romántico | $25.000 |
| Velas LED Decorativas | $10.000 |
| Letras Luminosas | $15.000 |
| Pack Nocturno Completo | $20.000 |
| Video 15s | $30.000 |
| Video 60s | $40.000 |
| Transporte desde Pucón | $50.000 |
| Toalla Normal | $9.000 |
| Toalla Poncho | $10.000 |
| Chalas de Ducha | $10.000 |
| Reserva FLEX (+10%) | 10% del total |

## 🔄 Flujo de Uso

### Ejemplo 1: Reserva Básica
1. Usuario: "disponibilidad 15 de febrero"
2. Bot: Muestra horarios disponibles
3. Usuario: "reservar 15 de febrero 10:00 4 personas"
4. Bot: "✅ Reserva agregada al carrito"
5. Usuario: "confirmar"
6. Bot: Muestra confirmación y total

### Ejemplo 2: Reserva con Extras
1. Usuario: "disponibilidad"
2. Bot: Muestra disponibilidad
3. Usuario: "reservar 20 de marzo 14:00 2 personas"
4. Usuario: "agregar tabla pequeña"
5. Usuario: "agregar modo romántico"
6. Usuario: "carrito" → Ve el resumen
7. Usuario: "confirmar" → Confirma la compra

## 📊 Estructura de Datos

### Tabla: `whatsapp_carts`
```sql
- id: SERIAL PRIMARY KEY
- phone_number: VARCHAR(20) UNIQUE
- customer_name: VARCHAR(100)
- cart_data: JSONB (array de items)
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### Formato de CartItem (JSON)
```json
{
  "item_type": "reservation" | "extra" | "accommodation",
  "name": "Nombre del item",
  "price": 100000,
  "quantity": 1,
  "metadata": {
    "date": "15 de febrero",
    "time": "10:00",
    "capacity": 4
  }
}
```

## 🚀 Instalación

1. **Ejecutar migración SQL:**
```bash
python run_migrations.py
```

O manualmente:
```sql
-- Ver create_carts_table.sql
```

2. **Reiniciar el servidor**

3. **Probar con comandos:**
- "carrito" → Ver carrito vacío
- "agregar jugo" → Agregar extra
- "carrito" → Ver carrito con items

## 💡 Mejoras Futuras

- [ ] Agregar reserva directamente desde respuesta de disponibilidad
- [ ] Permitir editar cantidad de extras
- [ ] Guardar historial de carritos confirmados
- [ ] Integración con sistema de pago
- [ ] Notificaciones al Capitán Tomás cuando se confirma un carrito

## 🔍 Troubleshooting

**Problema:** "No se puede agregar al carrito"
- Verifica que la tabla `whatsapp_carts` existe
- Revisa los logs del servidor

**Problema:** "Carrito no se guarda"
- Verifica la conexión a la base de datos
- Revisa que el JSONB esté funcionando correctamente

**Problema:** "No reconoce el extra"
- Verifica que el nombre del extra esté en `EXTRAS_CATALOG`
- Los nombres son case-insensitive y pueden tener variaciones

