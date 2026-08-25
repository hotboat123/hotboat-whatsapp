# Personas por número

Para que un número de WhatsApp tenga su propio asistente de IA (en vez del
bot de ventas de HotBoat), crea un archivo de texto plano en esta carpeta
llamado `<numero>.txt`, usando solo dígitos (sin "+", espacios ni guiones),
por ejemplo `56912345678.txt`.

El contenido del archivo es el prompt completo que va a seguir la IA para
ese número — nada de la información de HotBoat ni de las reglas de reserva
se agrega automáticamente. Escribe ahí quién es el asistente, qué sabe
responder y cómo debe hablar.

Los cambios se aplican al siguiente mensaje, sin reiniciar el servidor.

Ejemplo (`56912345678.txt`):

```
Eres un asistente técnico que ayuda al equipo de HotBoat a resolver
problemas de mantención del bote y del equipo (calefón, motor eléctrico,
bombas, etc). Responde de forma clara, práctica y directa, en español
chileno. Si el problema suena peligroso (gas, electricidad expuesta),
recomienda cortar el sistema y llamar a un técnico antes de seguir.
```
