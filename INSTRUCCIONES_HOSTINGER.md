# 📁 Cómo Subir Imágenes en Hostinger - Paso a Paso

## 🎯 Acceso al File Manager

### Paso 1: Accede al File Manager
1. En tu hPanel de Hostinger, en el menú lateral izquierdo
2. Busca y haz click en **"File Manager"** o **"Administrador de Archivos"**
   - Está en la sección de "Files" o "Archivos"
   - O usa el buscador del panel

### Paso 2: Navegar a la carpeta correcta
1. Una vez en File Manager, verás la estructura de carpetas
2. Busca la carpeta **`public_html`** (esta es la raíz de tu sitio web)
   - Si tienes múltiples dominios, puede haber carpetas como `public_html/hotboatchile.com/`
   - O simplemente `public_html/` si es un solo dominio

### Paso 3: Crear la estructura de carpetas
1. Dentro de `public_html/`, crea la carpeta `images/`
   - Click derecho → "New Folder" → nombre: `images`
2. Dentro de `images/`, crea la carpeta `accommodations/`
   - Entra a `images/` → Click derecho → "New Folder" → nombre: `accommodations`

### Paso 4: Subir las imágenes
1. Entra a la carpeta `public_html/images/accommodations/`
2. Click en el botón **"Upload"** o **"Subir"**
3. Arrastra las 6 imágenes o selecciónalas desde tu computadora:
   - `open-sky-domo-bath.jpg`
   - `open-sky-domo-hydromassage.jpg`
   - `relikura-cabin-2.jpg`
   - `relikura-cabin-4.jpg`
   - `relikura-cabin-6.jpg`
   - `relikura-hostel.jpg`
4. Espera a que terminen de subir

### Paso 5: Obtener las URLs
Una vez subidas, las URLs serán:
- `https://hotboatchile.com/images/accommodations/open-sky-domo-bath.jpg`
- `https://hotboatchile.com/images/accommodations/open-sky-domo-hydromassage.jpg`
- `https://hotboatchile.com/images/accommodations/relikura-cabin-2.jpg`
- `https://hotboatchile.com/images/accommodations/relikura-cabin-4.jpg`
- `https://hotboatchile.com/images/accommodations/relikura-cabin-6.jpg`
- `https://hotboatchile.com/images/accommodations/relikura-hostel.jpg`

**Para verificar:** Click derecho en cada imagen → "Copy URL" o simplemente abre la URL en tu navegador

### Paso 6: Verificar que funcionan
Abre cada URL en tu navegador para asegurarte de que:
- ✅ La imagen se carga
- ✅ Es HTTPS (no HTTP)
- ✅ No pide contraseña

---

## 🔍 Si no encuentras File Manager

### Alternativa: Acceso por FTP
Si no ves File Manager en el panel:
1. Busca "FTP" o "FTP Accounts" en el menú
2. Crea una cuenta FTP o usa la existente
3. Conecta con un cliente FTP como FileZilla (gratis)
4. Sube las imágenes a la misma ruta: `public_html/images/accommodations/`

---

## 📝 Estructura Final

Tu estructura debería verse así:
```
public_html/
└── images/
    └── accommodations/
        ├── open-sky-domo-bath.jpg
        ├── open-sky-domo-hydromassage.jpg
        ├── relikura-cabin-2.jpg
        ├── relikura-cabin-4.jpg
        ├── relikura-cabin-6.jpg
        └── relikura-hostel.jpg
```

---

## ✅ Después de subir

1. Copia las 6 URLs
2. Actualiza `app/config/accommodations_config.py` con esas URLs
3. Reinicia el servidor
4. Prueba escribiendo "alojamientos" en WhatsApp

¡Listo! 🎉

