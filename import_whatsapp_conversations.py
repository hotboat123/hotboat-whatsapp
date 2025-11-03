"""
Script to import WhatsApp conversations from export or existing data

Usage examples:
1. Import from CSV
2. Import from JSON file
3. Import from manual input

This script helps migrate existing WhatsApp Business conversations to the bot system.

Environment variables required:
- DATABASE_URL: PostgreSQL connection string (automatically loaded from .env or Railway)
"""
import os
import sys
import json
import csv
import asyncio
from datetime import datetime
from typing import List, Dict

# Load environment variables from .env file if it exists
from dotenv import load_dotenv
load_dotenv()

# Verify that DATABASE_URL is set
if not os.getenv('DATABASE_URL'):
    print("❌ Error: DATABASE_URL environment variable is not set")
    print("   Please set it in your .env file or Railway environment variables")
    sys.exit(1)

async def import_from_json(file_path: str):
    """
    Import conversations from a JSON file
    
    Expected JSON format:
    [
        {
            "phone_number": "56912345678",
            "customer_name": "John Doe",
            "conversations": [
                {
                    "message": "Hola",
                    "response": "Hola, ¿en qué puedo ayudarte?",
                    "timestamp": "2025-01-01T10:00:00Z",
                    "direction": "incoming",
                    "message_id": "optional_id"
                },
                ...
            ]
        },
        ...
    ]
    """
    try:
        from app.db.leads import import_conversation_batch
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total_imported = 0
        for contact_data in data:
            phone_number = contact_data.get('phone_number')
            customer_name = contact_data.get('customer_name', '')
            conversations = contact_data.get('conversations', [])
            
            if not phone_number:
                print(f"⚠️  Skipping entry without phone_number")
                continue
            
            imported = await import_conversation_batch(
                conversations=conversations,
                phone_number=phone_number,
                customer_name=customer_name
            )
            
            total_imported += imported
            print(f"✅ Imported {imported} conversations for {phone_number} ({customer_name})")
        
        print(f"\n✅ Total: {total_imported} conversations imported")
        
    except Exception as e:
        print(f"❌ Error importing from JSON: {e}")
        import traceback
        traceback.print_exc()


async def import_from_csv(file_path: str):
    """
    Import conversations from a CSV file
    
    Expected CSV format:
    phone_number,customer_name,message,response,timestamp,direction,message_id
    56912345678,John Doe,Hola,Hola ¿en qué puedo ayudarte?,2025-01-01 10:00:00,incoming,
    """
    try:
        from app.db.leads import import_conversation_batch
        
        # Group conversations by phone number
        contacts = {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                phone_number = row.get('phone_number', '').strip()
                if not phone_number:
                    continue
                
                if phone_number not in contacts:
                    contacts[phone_number] = {
                        'phone_number': phone_number,
                        'customer_name': row.get('customer_name', '').strip(),
                        'conversations': []
                    }
                
                # Parse timestamp
                timestamp_str = row.get('timestamp', '').strip()
                timestamp = None
                if timestamp_str:
                    try:
                        # Try different formats
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S%z']:
                            try:
                                timestamp = datetime.strptime(timestamp_str, fmt)
                                break
                            except ValueError:
                                continue
                    except:
                        pass
                
                contacts[phone_number]['conversations'].append({
                    'message': row.get('message', '').strip(),
                    'response': row.get('response', '').strip(),
                    'timestamp': timestamp.isoformat() if timestamp else None,
                    'direction': row.get('direction', 'incoming').strip(),
                    'message_id': row.get('message_id', '').strip() or None
                })
        
        # Import each contact's conversations
        total_imported = 0
        for phone_number, contact_data in contacts.items():
            imported = await import_conversation_batch(
                conversations=contact_data['conversations'],
                phone_number=contact_data['phone_number'],
                customer_name=contact_data['customer_name']
            )
            
            total_imported += imported
            print(f"✅ Imported {imported} conversations for {phone_number} ({contact_data['customer_name']})")
        
        print(f"\n✅ Total: {total_imported} conversations imported")
        
    except Exception as e:
        print(f"❌ Error importing from CSV: {e}")
        import traceback
        traceback.print_exc()


async def create_sample_import_template():
    """Create a sample JSON template for importing conversations"""
    sample = [
        {
            "phone_number": "56912345678",
            "customer_name": "Ejemplo Cliente",
            "conversations": [
                {
                    "message": "Hola, quiero información sobre los tours",
                    "response": "¡Hola! Claro, te puedo ayudar con información sobre nuestros tours HotBoat...",
                    "timestamp": "2025-01-15T10:00:00Z",
                    "direction": "incoming",
                    "message_id": "sample_1"
                },
                {
                    "message": "¿Cuánto cuesta?",
                    "response": "Los precios varían según el número de personas. Para 2 personas es $69.990 por persona...",
                    "timestamp": "2025-01-15T10:05:00Z",
                    "direction": "incoming",
                    "message_id": "sample_2"
                }
            ]
        }
    ]
    
    with open('conversations_import_template.json', 'w', encoding='utf-8') as f:
        json.dump(sample, f, indent=2, ensure_ascii=False)
    
    print("✅ Created 'conversations_import_template.json' with sample format")


if __name__ == "__main__":
    print("📥 WhatsApp Conversations Import Tool")
    print("=" * 60)
    
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python import_whatsapp_conversations.py <file_path> [json|csv]")
        print("  python import_whatsapp_conversations.py template  # Create template")
        print("\nExamples:")
        print("  python import_whatsapp_conversations.py conversations.json")
        print("  python import_whatsapp_conversations.py conversations.csv csv")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if file_path == "template":
        asyncio.run(create_sample_import_template())
        sys.exit(0)
    
    # Detect file type
    file_type = sys.argv[2] if len(sys.argv) > 2 else None
    if not file_type:
        if file_path.endswith('.csv'):
            file_type = 'csv'
        elif file_path.endswith('.json'):
            file_type = 'json'
        else:
            print("❌ Cannot detect file type. Please specify 'json' or 'csv'")
            sys.exit(1)
    
    if file_type == 'json':
        asyncio.run(import_from_json(file_path))
    elif file_type == 'csv':
        asyncio.run(import_from_csv(file_path))
    else:
        print(f"❌ Unknown file type: {file_type}")
        sys.exit(1)

