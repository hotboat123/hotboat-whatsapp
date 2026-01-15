#!/bin/bash
# Automated Cloudflare Tunnel Setup Script

echo "============================================"
echo "  Cloudflare Tunnel Setup for Kia-Ai"
echo "============================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo -e "${RED}cloudflared is not installed${NC}"
    echo ""
    echo "Please install it first:"
    echo ""
    echo "Linux:"
    echo "  wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb"
    echo "  sudo dpkg -i cloudflared-linux-amd64.deb"
    echo ""
    echo "macOS:"
    echo "  brew install cloudflare/cloudflare/cloudflared"
    echo ""
    echo "Windows:"
    echo "  winget install --id Cloudflare.cloudflared"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ cloudflared is installed${NC}"
echo ""

# Step 1: Login
echo "Step 1: Login to Cloudflare"
echo "This will open your browser to authenticate..."
echo ""
read -p "Press Enter to continue..."
cloudflared tunnel login

if [ $? -ne 0 ]; then
    echo -e "${RED}Login failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Login successful${NC}"
echo ""

# Step 2: Create tunnel
echo "Step 2: Create tunnel"
TUNNEL_NAME="kia-ai"
echo "Creating tunnel: $TUNNEL_NAME"
echo ""

cloudflared tunnel create $TUNNEL_NAME

if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Tunnel may already exist. Continuing...${NC}"
fi

echo ""

# Step 3: Get tunnel info
echo "Step 3: Getting tunnel information..."
TUNNEL_INFO=$(cloudflared tunnel info $TUNNEL_NAME 2>/dev/null)

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to get tunnel info${NC}"
    echo "Please run manually: cloudflared tunnel info kia-ai"
    exit 1
fi

echo -e "${GREEN}✓ Tunnel created${NC}"
echo ""
echo "Tunnel information:"
echo "$TUNNEL_INFO"
echo ""

# Step 4: Configure DNS
echo "Step 4: Configure DNS"
read -p "Enter your domain (e.g., kia-ai.yourdomain.com): " DOMAIN

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}Domain is required${NC}"
    exit 1
fi

echo "Creating DNS record for: $DOMAIN"
cloudflared tunnel route dns $TUNNEL_NAME $DOMAIN

if [ $? -ne 0 ]; then
    echo -e "${YELLOW}DNS record may already exist. Continuing...${NC}"
fi

echo -e "${GREEN}✓ DNS configured${NC}"
echo ""

# Step 5: Update config file
echo "Step 5: Updating configuration file..."

# Extract tunnel ID from info
TUNNEL_ID=$(echo "$TUNNEL_INFO" | grep -oP 'id:\s+\K[a-f0-9-]+' | head -1)

if [ -z "$TUNNEL_ID" ]; then
    echo -e "${YELLOW}Could not extract tunnel ID automatically${NC}"
    echo "Please update cloudflared-config.yml manually"
else
    # Update config file
    sed -i.bak "s/YOUR_TUNNEL_ID/$TUNNEL_ID/g" cloudflared-config.yml
    sed -i.bak "s/YOUR_DOMAIN.com/$DOMAIN/g" cloudflared-config.yml
    
    # Update credentials path (Linux default)
    CREDS_PATH="$HOME/.cloudflared/$TUNNEL_ID.json"
    sed -i.bak "s|/root/.cloudflared/YOUR_TUNNEL_ID.json|$CREDS_PATH|g" cloudflared-config.yml
    
    echo -e "${GREEN}✓ Configuration updated${NC}"
    echo ""
    echo "Config file: cloudflared-config.yml"
    echo "Credentials: $CREDS_PATH"
fi

echo ""
echo "============================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "============================================"
echo ""
echo "To start the tunnel:"
echo "  cloudflared tunnel --config cloudflared-config.yml run $TUNNEL_NAME"
echo ""
echo "To install as a service:"
echo "  sudo cloudflared service install"
echo "  sudo systemctl start cloudflared"
echo ""
echo "Your Kia-Ai interface will be available at:"
echo -e "${GREEN}https://$DOMAIN${NC}"
echo ""
echo "Don't forget to start your FastAPI server:"
echo "  python3 -m app.main"
echo ""

