from supabase import create_client

url = 'https://zczzcvlpvnwevoxfosdp.supabase.co'
key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpjenpjdmxwdm53ZXZveGZvc2RwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTQ3NDAwOCwiZXhwIjoyMDgxMDUwMDA4fQ.-SKRKc3bREusIwJrV33KIBNO7SXBSWx3ua-tuYxAzmQ'
client = create_client(url, key)

print("Probando header Accept-Profile...")

# Agregar header Accept-Profile para acceder al schema valle_frio_bot
client.postgrest.headers["Accept-Profile"] = "valle_frio_bot"

try:
    result = client.table('bot1_nominas_descargadas').select('*').limit(1).execute()
    print('✓ FUNCIONA: Accept-Profile header')
    print(f'  Datos: {result.data}')
except Exception as e:
    print(f'✗ Error: {type(e).__name__}: {e}')
