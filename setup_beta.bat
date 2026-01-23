@echo off
REM 🧪 Script para configurar ambiente BETA (Windows)
REM Este script automatiza la creación de la rama beta y configuración inicial

echo 🧪 Configurando ambiente BETA para HotBoat WhatsApp...
echo.

REM 1. Verificar que estamos en main
echo 📍 Verificando rama actual...
for /f "tokens=*" %%a in ('git branch --show-current') do set CURRENT_BRANCH=%%a

if not "%CURRENT_BRANCH%"=="main" (
    echo ⚠️  No estás en la rama main. Cambiando a main...
    git checkout main
)

REM 2. Actualizar main
echo 🔄 Actualizando rama main...
git pull origin main 2>nul || echo Primera vez, continuando...

REM 3. Verificar si beta existe
git rev-parse --verify beta >nul 2>&1
if %errorlevel% equ 0 (
    echo ⚠️  La rama beta ya existe
    set /p RECREATE="¿Quieres recrearla? (y/N): "
    if /i "%RECREATE%"=="y" (
        git branch -D beta
        git checkout -b beta
    ) else (
        git checkout beta
    )
) else (
    echo 🌿 Creando rama beta...
    git checkout -b beta
)

REM 4. Push a GitHub
echo 📤 Enviando rama beta a GitHub...
git push -u origin beta 2>nul || git push origin beta

REM 5. Volver a main
echo 🔙 Volviendo a rama main...
git checkout main

echo.
echo ✅ ¡Rama beta configurada exitosamente!
echo.
echo 📋 PRÓXIMOS PASOS:
echo.
echo 1. Ve a Railway: https://railway.app
echo 2. Selecciona tu proyecto hotboat-whatsapp
echo 3. Click en tu service -^> Settings -^> Environments
echo 4. Click 'New Environment':
echo    - Name: staging
echo    - Branch: beta
echo 5. Configura las variables de entorno para staging
echo 6. ¡Listo! Ahora tienes dos ambientes:
echo    - main -^> production
echo    - beta -^> staging
echo.
echo 📖 Lee AMBIENTE_BETA_SETUP.md para más detalles
echo.
pause
