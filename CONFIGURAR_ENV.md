# 🔧 Cómo Configurar el archivo .env

## 📋 Paso a Paso

### 1. Abre el archivo `.env` en tu editor

El archivo está en la raíz del proyecto: `C:\Users\cuent\Desktop\hotboat-whatsapp\.env`

### 2. Obtén tu DATABASE_URL

#### Opción A: Desde Railway (Recomendado)

1. Ve a: https://railway.app
2. Selecciona tu proyecto (probablemente `hotboat-etl` o similar)
3. Ve a la sección **PostgreSQL** o **Database**
4. Click en **Variables** o **Connect**
5. Busca `DATABASE_URL` o `POSTGRES_URL`
6. Copia el valor completo (debe verse así):
   ```
   postgresql://postgres:password@host.railway.app:5432/railway
   ```

#### Opción B: Si ya tienes la URL en otro lugar

Si ya tienes configurada la base de datos en otro proyecto, copia esa misma `DATABASE_URL`.

### 3. Actualiza el archivo .env

Reemplaza esta línea:
```env
DATABASE_URL=postgresql://user:password@host:port/dbname
```

Por tu DATABASE_URL real:
```env
DATABASE_URL=postgresql://postgres:xxxxx@xxxx.railway.app:5432/railway
```

### 4. Configura las demás variables

También necesitas configurar:
- `WHATSAPP_API_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_BUSINESS_ACCOUNT_ID`
- `WHATSAPP_VERIFY_TOKEN`
- `GROQ_API_KEY`

### 5. Guarda el archivo

⚠️ **IMPORTANTE**: Asegúrate de que el archivo `.env` esté en `.gitignore` para no subir tus credenciales a GitHub.

### 6. Prueba la conexión

```bash
python run_migrations.py
```

Si todo está bien, deberías ver:
```
✅ Migrations completed successfully!
```

## 🔒 Seguridad

- ✅ El archivo `.env` NO debe estar en GitHub
- ✅ Ya está en `.gitignore` (verifica que esté ahí)
- ✅ Nunca compartas tu `.env` con nadie
- ✅ Usa diferentes tokens para desarrollo y producción

## 🆘 Si no tienes acceso a Railway

Si no tienes acceso a Railway o no tienes una base de datos configurada:

1. **Crea una base de datos PostgreSQL** en Railway:
   - New Project → New Database → PostgreSQL
   - Railway te dará el `DATABASE_URL` automáticamente

2. **O usa una base de datos local** (para desarrollo):
   - Instala PostgreSQL localmente
   - Crea una base de datos
   - Usa: `postgresql://postgres:password@localhost:5432/hotboat`

