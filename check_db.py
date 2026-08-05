import os
import requests
import json

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://zkqzejnflpzknuuirlav.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS')

def get_headers():
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?data=eq.05/08/2026"
res = requests.get(url, headers=get_headers())
if res.status_code == 200:
    data = res.json()
    print(f"Found {len(data)} records for 05/08/2026.")
    for row in data:
        print(f"ID: {row.get('id')} | MOTORISTA: {row.get('motorista')} | CLIENTE: {row.get('cliente')} | DATA: {row.get('data')} | DF: {row.get('df')} | DATA_FINALIZACAO: {row.get('data_finalizacao')}")
else:
    print('Failed to fetch:', res.status_code, res.text)
