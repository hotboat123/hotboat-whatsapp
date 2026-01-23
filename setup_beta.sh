#!/bin/bash

# 🧪 Script para configurar ambiente BETA
# Este script automatiza la creación de la rama beta y configuración inicial

set -e

echo "🧪 Configurando ambiente BETA para HotBoat WhatsApp..."
echo ""

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Verificar que estamos en main
echo "📍 Verificando rama actual..."
CURRENT_BRANCH=$(git branch --show-current)

if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "${YELLOW}⚠️  No estás en la rama main. Cambiando a main...${NC}"
    git checkout main
fi

# 2. Actualizar main
echo "🔄 Actualizando rama main..."
git pull origin main || echo "Primera vez, continuando..."

# 3. Crear rama beta
echo "🌿 Creando rama beta..."
if git rev-parse --verify beta >/dev/null 2>&1; then
    echo "${YELLOW}⚠️  La rama beta ya existe${NC}"
    read -p "¿Quieres recrearla? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git branch -D beta
        git checkout -b beta
    else
        git checkout beta
    fi
else
    git checkout -b beta
fi

# 4. Push a GitHub
echo "📤 Enviando rama beta a GitHub..."
git push -u origin beta || git push origin beta

# 5. Volver a main
echo "🔙 Volviendo a rama main..."
git checkout main

echo ""
echo "${GREEN}✅ ¡Rama beta configurada exitosamente!${NC}"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo ""
echo "1. Ve a Railway: https://railway.app"
echo "2. Selecciona tu proyecto hotboat-whatsapp"
echo "3. Click en tu service → Settings → Environments"
echo "4. Click 'New Environment':"
echo "   - Name: staging"
echo "   - Branch: beta"
echo "5. Configura las variables de entorno para staging"
echo "6. ¡Listo! Ahora tienes dos ambientes:"
echo "   - main → production"
echo "   - beta → staging"
echo ""
echo "📖 Lee AMBIENTE_BETA_SETUP.md para más detalles"
echo ""
