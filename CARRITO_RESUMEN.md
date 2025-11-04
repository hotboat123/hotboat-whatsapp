# 🛒 Sistema de Carrito - Resumen Rápido

## ✅ Funcionalidades Implementadas

1. **Agregar Extras** - Usuario puede agregar cualquier extra escribiendo "agregar [nombre]"
2. **Agregar Reserva** - Usuario puede agregar reserva con fecha, horario y personas
3. **Ver Carrito** - Comando "carrito" muestra todos los items y total
4. **Eliminar Items** - "eliminar [número]" para quitar items
5. **Vaciar Carrito** - "vaciar" para limpiar todo
6. **Confirmar Compra** - "confirmar" para finalizar la reserva

## 🚀 Cómo Usar

### Paso 1: Ejecutar Migración
```bash
python run_migrations.py
```

Esto creará la tabla `whatsapp_carts` en la base de datos.

### Paso 2: Reiniciar Servidor
```bash
# Reinicia tu servidor para cargar los nuevos módulos
```

### Paso 3: Probar
1. Escribe "carrito" → Ver carrito vacío
2. Escribe "agregar jugo" → Agregar extra
3. Escribe "carrito" → Ver carrito con items
4. Escribe "confirmar" → Confirmar compra

## 📝 Ejemplo de Flujo Completo

```
Usuario: disponibilidad 15 de febrero
Bot: [Muestra horarios disponibles]

Usuario: reservar 15 de febrero 10:00 4 personas
Bot: ✅ Reserva agregada al carrito

Usuario: agregar tabla grande
Bot: ✅ Tabla de Picoteo Grande agregada al carrito

Usuario: agregar modo romántico
Bot: ✅ Modo Romántico agregado al carrito

Usuario: carrito
Bot: [Muestra resumen completo con total]

Usuario: confirmar
Bot: ✅ Reserva Confirmada [con todos los detalles]
```

## 🎯 Próximas Mejoras Sugeridas

1. **Integración automática con disponibilidad** - Cuando el usuario consulta disponibilidad y dice "quiero ese", agregar automáticamente al carrito
2. **Editar cantidad** - Permitir cambiar cantidad de extras
3. **Notificación al admin** - Enviar notificación cuando se confirma un carrito
4. **Link de pago** - Integrar con pasarela de pago

## ⚠️ Notas Importantes

- El carrito se guarda en la base de datos (persistente)
- Solo se puede tener UNA reserva por carrito (si agregas otra, reemplaza la anterior)
- La reserva FLEX se calcula como 10% del subtotal
- El carrito se limpia automáticamente después de confirmar

