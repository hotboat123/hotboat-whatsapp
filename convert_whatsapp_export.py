"""
Script auxiliar para convertir exportaciones de WhatsApp a formato de importación

Este script ayuda a convertir diferentes formatos de exportación de WhatsApp
al formato requerido por el sistema de importación.
"""
import json
import csv
import re
from datetime import datetime
from typing import List, Dict

def parse_whatsapp_txt(text_content: str) -> List[Dict]:
    """
    Convierte un archivo .txt exportado de WhatsApp al formato de importación
    
    Formato típico de exportación de WhatsApp:
    [15/01/2025, 10:00:00] Juan Pérez: Hola, quiero información
    [15/01/2025, 10:05:00] Tú: ¡Hola! Te puedo ayudar...
    """
    conversations = []
    lines = text_content.split('\n')
    
    current_user_msg = None
    current_bot_msg = None
    
    # Patrón para detectar líneas de mensaje
    # Formato: [DD/MM/YYYY, HH:MM:SS] Nombre: Mensaje
    pattern = r'\[(\d{2}/\d{2}/\d{4}),\s+(\d{2}:\d{2}:\d{2})\]\s+(.+?):\s+(.+)'
    
    for line in lines:
        match = re.match(pattern, line.strip())
        if not match:
            continue
        
        date_str, time_str, sender, message = match.groups()
        
        # Parsear fecha
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M:%S")
            timestamp = dt.isoformat()
        except:
            timestamp = None
        
        # Determinar si es mensaje entrante o saliente
        # Asume que "Tú" o tu nombre es saliente, otros son entrantes
        if sender.lower() in ['tú', 'you', 'yo']:
            # Es una respuesta del bot
            if current_user_msg:
                conversations.append({
                    "message": current_user_msg["message"],
                    "response": message,
                    "timestamp": timestamp or current_user_msg.get("timestamp"),
                    "direction": "incoming",
                    "message_id": None
                })
                current_user_msg = None
        else:
            # Es un mensaje del usuario
            if current_user_msg and not current_bot_msg:
                # Mensaje anterior sin respuesta
                conversations.append({
                    "message": current_user_msg["message"],
                    "response": "",
                    "timestamp": current_user_msg.get("timestamp"),
                    "direction": "incoming",
                    "message_id": None
                })
            
            current_user_msg = {
                "message": message,
                "timestamp": timestamp,
                "sender": sender
            }
            current_bot_msg = None
    
    return conversations


def convert_csv_to_import_format(input_csv: str, output_json: str):
    """
    Convierte un CSV personalizado al formato de importación JSON
    
    El CSV puede tener diferentes formatos, este script intenta detectarlo.
    """
    contacts = {}
    
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Detectar formato de CSV
            phone_key = None
            name_key = None
            msg_key = None
            resp_key = None
            time_key = None
            
            # Buscar columnas posibles
            for col in row.keys():
                col_lower = col.lower()
                if 'phone' in col_lower or 'numero' in col_lower or 'tel' in col_lower:
                    phone_key = col
                elif 'name' in col_lower or 'nombre' in col_lower:
                    name_key = col
                elif 'message' in col_lower or 'mensaje' in col_lower or 'msg' in col_lower:
                    msg_key = col
                elif 'response' in col_lower or 'respuesta' in col_lower or 'reply' in col_lower:
                    resp_key = col
                elif 'time' in col_lower or 'fecha' in col_lower or 'date' in col_lower or 'timestamp' in col_lower:
                    time_key = col
            
            if not phone_key:
                print(f"⚠️  No se encontró columna de teléfono en el CSV")
                continue
            
            phone = row[phone_key].strip() if phone_key else ""
            name = row[name_key].strip() if name_key and name_key in row else ""
            message = row[msg_key].strip() if msg_key and msg_key in row else ""
            response = row[resp_key].strip() if resp_key and resp_key in row else ""
            timestamp = row[time_key].strip() if time_key and time_key in row else None
            
            # Limpiar número de teléfono
            phone = re.sub(r'[^\d]', '', phone)
            
            if not phone:
                continue
            
            if phone not in contacts:
                contacts[phone] = {
                    "phone_number": phone,
                    "customer_name": name,
                    "conversations": []
                }
            
            if message or response:
                contacts[phone]["conversations"].append({
                    "message": message,
                    "response": response,
                    "timestamp": timestamp,
                    "direction": "incoming",
                    "message_id": None
                })
    
    # Convertir a formato de lista
    result = list(contacts.values())
    
    # Guardar JSON
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Convertido {len(result)} contactos a {output_json}")
    return result


def convert_txt_to_import_format(input_txt: str, phone_number: str, customer_name: str, output_json: str):
    """
    Convierte un archivo .txt de exportación de WhatsApp a formato de importación
    
    Args:
        input_txt: Ruta al archivo .txt exportado de WhatsApp
        phone_number: Número de teléfono del contacto
        customer_name: Nombre del contacto
        output_json: Ruta donde guardar el JSON de salida
    """
    with open(input_txt, 'r', encoding='utf-8') as f:
        content = f.read()
    
    conversations = parse_whatsapp_txt(content)
    
    result = [{
        "phone_number": phone_number,
        "customer_name": customer_name,
        "conversations": conversations
    }]
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Convertido {len(conversations)} conversaciones a {output_json}")
    return result


if __name__ == "__main__":
    import sys
    
    print("🔄 Conversor de Exportaciones de WhatsApp")
    print("=" * 60)
    
    if len(sys.argv) < 3:
        print("\nUso:")
        print("  python convert_whatsapp_export.py txt <input.txt> <phone> <name> <output.json>")
        print("  python convert_whatsapp_export.py csv <input.csv> <output.json>")
        print("\nEjemplos:")
        print("  python convert_whatsapp_export.py txt chat_juan.txt 56912345678 'Juan Pérez' juan.json")
        print("  python convert_whatsapp_export.py csv conversaciones.csv conversaciones.json")
        sys.exit(1)
    
    format_type = sys.argv[1]
    
    if format_type == "txt":
        if len(sys.argv) < 6:
            print("❌ Faltan argumentos para formato TXT")
            print("Uso: python convert_whatsapp_export.py txt <input.txt> <phone> <name> <output.json>")
            sys.exit(1)
        
        input_file = sys.argv[2]
        phone = sys.argv[3]
        name = sys.argv[4]
        output_file = sys.argv[5]
        
        convert_txt_to_import_format(input_file, phone, name, output_file)
    
    elif format_type == "csv":
        if len(sys.argv) < 4:
            print("❌ Faltan argumentos para formato CSV")
            print("Uso: python convert_whatsapp_export.py csv <input.csv> <output.json>")
            sys.exit(1)
        
        input_file = sys.argv[2]
        output_file = sys.argv[3]
        
        convert_csv_to_import_format(input_file, output_file)
    
    else:
        print(f"❌ Formato desconocido: {format_type}")
        print("Formatos soportados: txt, csv")
        sys.exit(1)

