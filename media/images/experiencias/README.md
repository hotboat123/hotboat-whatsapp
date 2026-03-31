# Imágenes — Otras experiencias Pucón (Rafting, Cabalgata, Navegación)

El bot envía estas imágenes cuando el usuario elige **6 — Otras Experiencias Pucón** en el menú de Popeye.

## Dónde poner cada cosa

### 1. Resumen visual (recomendado)

En **esta carpeta** (`media/images/experiencias/`), sube **una** de estas (el bot usa la primera que exista):

| Archivo | Descripción |
|--------|-------------|
| `resumen-experiencias.jpg` | o `.png` / `.webp` — imagen única con las 3 experiencias |
| `01_resumen_experiencias.jpg` | alternativa al nombre anterior |

### 2. Imágenes por experiencia (subcarpetas)

Coloca fotos en:

| Carpeta | Contenido |
|---------|-----------|
| `rafting/` | Fotos rafting (primera imagen lleva caption 🚣 Rafting) |
| `cabalgata/` | Fotos cabalgata (primera con caption 🐴 Cabalgata) |
| `navegacion/` | Fotos navegación / velerismo |
| `velerismo/` | Opcional: si usas solo velerismo aquí |

Formatos: `.jpg`, `.jpeg`, `.png`, `.webp`

### 3. PDF resumen (opcional)

Si prefieres un PDF en lugar de o además del resumen:

- Archivo: **`media/documents/experiencias.pdf`**
- El bot lo envía **antes** de las imágenes, con caption descriptivo.

## Orden de envío

1. Mensaje de texto del menú  
2. PDF (`experiencias.pdf`) si existe  
3. Imagen resumen en raíz si existe  
4. Imágenes de `rafting/`, luego `cabalgata/`, luego `navegacion/` y `velerismo/`

## Nota técnica

Las imágenes PNG/WebP se suben con el MIME correcto; antes solo se usaba JPEG y podía fallar el envío.
