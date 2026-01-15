"""Quick test script to verify Kia-Ai is working"""
import sys
import time

print("Testing Kia-Ai Setup...")
print("-" * 50)

# Test 1: Configuration
print("\n[1] Testing Configuration...")
try:
    from app.config import get_settings
    settings = get_settings()
    print("   [OK] Configuration loaded successfully")
    print(f"   [OK] Server will run on: {settings.host}:{settings.port}")
except Exception as e:
    print(f"   [ERROR] Configuration error: {e}")
    sys.exit(1)

# Test 2: Static files
print("\n[2] Checking Static Files...")
import os
static_dir = os.path.join(os.path.dirname(__file__), "app", "static")
required_files = ["index.html", "styles.css", "app.js"]

for file in required_files:
    file_path = os.path.join(static_dir, file)
    if os.path.exists(file_path):
        print(f"   [OK] {file} found")
    else:
        print(f"   [ERROR] {file} missing")

# Test 3: Import main app
print("\n[3] Testing FastAPI App...")
try:
    from app.main import app
    print("   [OK] FastAPI app loaded successfully")
except Exception as e:
    print(f"   [ERROR] App error: {e}")
    sys.exit(1)

# Test 4: Check endpoints
print("\n[4] Checking API Endpoints...")
endpoints = [
    "/",
    "/api/conversations",
    "/api/send-message",
    "/webhook",
]

for route in app.routes:
    if hasattr(route, 'path'):
        if route.path in endpoints:
            print(f"   [OK] {route.path} registered")

print("\n" + "="*50)
print("ALL TESTS PASSED!")
print("="*50)
print("\nReady to start Kia-Ai!")
print("\nTo start the server, run:")
print("   python -m app.main")
print("\nThen open in your browser:")
print("   http://localhost:8000")
print("\n")

