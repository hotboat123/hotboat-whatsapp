"""
Crea una reserva de prueba con $100 CLP para testear el sistema de pago.
Ejecutar: python _test_pago.py
"""
import os, sys

# Load .env
env = {}
try:
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
except FileNotFoundError:
    pass

db_url = env.get('DATABASE_URL') or os.environ.get('DATABASE_URL', '')
if not db_url:
    print("ERROR: DATABASE_URL no encontrada en .env")
    sys.exit(1)

import psycopg

print("Conectando a la base de datos...")
with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO all_appointments (
                source, nombre_cliente, telefono, email,
                fecha, hora, num_personas,
                ingreso_reserva, ingreso_extras, ingreso_total,
                status, observaciones
            ) VALUES (
                'test', 'Cliente Test', '56912345678', 'test@hotboat.cl',
                CURRENT_DATE + INTERVAL '7 days', '10:00', 2,
                100, 0, 100,
                'pendiente', 'RESERVA DE PRUEBA - sistema de pago $100 CLP'
            )
            RETURNING id
        """)
        row = cur.fetchone()
        conn.commit()
        rid = row[0]

print(f"\n✅ Reserva de prueba creada con ID: {rid}")
print(f"   Nombre:  Cliente Test")
print(f"   Total:   $100 CLP")
print(f"   Fecha:   en 7 días")
print(f"\n👉 Ve al admin → Reservas → busca ID {rid}")
print(f"   Haz clic en la reserva y presiona '💳 Solicitar Pago'")
print(f"\nPara eliminarla después de la prueba, ejecuta:")
print(f"   python -c \"import psycopg,os; conn=psycopg.connect('{db_url}'); cur=conn.cursor(); cur.execute('DELETE FROM all_appointments WHERE id=%s', ({rid},)); conn.commit(); print('Eliminada')\"")
