"""Migration 018: add customer_birthday column and birthday_emails_sent table."""
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
ALTER TABLE hotboat_appointments
ADD COLUMN IF NOT EXISTS customer_birthday DATE;

CREATE TABLE IF NOT EXISTS birthday_emails_sent (
    customer_email  VARCHAR(255) NOT NULL,
    sent_year       INT          NOT NULL,
    sent_at         TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (customer_email, sent_year)
);
""")
conn.commit()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='hotboat_appointments' AND column_name='customer_birthday'")
row = cur.fetchone()
print("customer_birthday column exists:", bool(row))

cur.close(); conn.close()
print("Migration 018 done.")
