#!/bin/bash
# Quick start script for Kia-Ai on Linux/Mac

echo "========================================"
echo "   Starting Kia-Ai WhatsApp Interface"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.9+ first"
    exit 1
fi

echo "[1/3] Installing dependencies..."
pip3 install -r requirements.txt

echo ""
echo "[2/3] Starting FastAPI server..."
echo ""
echo "Kia-Ai will be available at: http://localhost:8000"
echo "Press Ctrl+C to stop the server"
echo ""

python3 -m app.main

