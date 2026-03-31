# Experiencias PDF

Este directorio debe contener el archivo PDF de experiencias para el flujo de "Experiencias y Actividades".

## Archivo Requerido

### `experiencias.pdf`

**Archivo principal de experiencias que se envía al usuario cuando selecciona la opción 4 del menú principal.**

Este PDF debe contener información detallada sobre:

#### 🚣 Rafting
- **Rafting Bajo** (Nivel principiante)
  - Precio: $30.000 por persona
  - Duración: 2-3 horas
  - Dificultad: Baja (ideal para familias)

- **Rafting Alto** (Nivel avanzado)
  - Precio: $40.000 por persona
  - Duración: 3-4 horas
  - Dificultad: Alta (más adrenalina)

#### 🐴 Cabalgata
- **Cabalgata Parque Ojos del Caburguá**
  - Precio: $50.000 por persona
  - Duración: 3-4 horas
  - Incluye: Guía, equipo completo y snack

#### ⛵ Navegación

**Travesías de 30 minutos:**
- 2 personas: $300.000
- 4 personas: $340.000
- 6 personas: $360.000
- 8 personas: $380.000
- 10 personas: $400.000

**Yave a vela Akimbo (1.5 horas):**
- 2 personas: $120.000
- 3 personas: $130.000
- 4 personas: $140.000
- 5 personas: $150.000 - $160.000

## Cómo Agregar el PDF

1. Crea tu PDF con la información de experiencias y actividades
2. Nómbralo exactamente como: `experiencias.pdf`
3. Colócalo en este directorio: `media/documents/`
4. El bot lo enviará automáticamente cuando el usuario seleccione **6 — Otras Experiencias Pucón** (antes de las imágenes de detalle).

## Imágenes (rafting, cabalgata, navegación)

Las fotos por experiencia y el resumen visual van en **`media/images/experiencias/`** (subcarpetas `rafting/`, `cabalgata/`, `navegacion/`, etc.).  
Ver `media/images/experiencias/README.md` en el repositorio.

## Formato Recomendado del PDF

- **Título principal:** HOTBOAT CHILE - EXPERIENCIAS Y ACTIVIDADES
- **Subtítulo:** Explora las mejores aventuras en Pucón!
- Incluir fotos de calidad de cada experiencia
- Usar iconos para facilitar la lectura
- Incluir detalles de seguridad y requisitos
- Agregar información de contacto y redes sociales
- Logo de HotBoat Chile

## Nota Importante

Si el archivo `experiencias.pdf` no existe, el bot mostrará un mensaje de error al usuario y le pedirá que escriba "experiencias" para obtener la información por texto.

## Diseño Sugerido

Puedes usar herramientas como:
- Canva (plantillas profesionales)
- Adobe InDesign
- Microsoft Word (exportar a PDF)
- Google Docs (exportar a PDF)

Asegúrate de que el PDF sea:
- Visualmente atractivo
- Fácil de leer en móviles
- No muy pesado (máximo 5MB)
- Con imágenes optimizadas
