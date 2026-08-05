import os, requests
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://zkqzejnflpzknuuirlav.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS')
headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?cliente=ilike.*UNIMARKA*"
res = requests.get(url, headers=headers)
for row in res.json():
    print(f"ID: {row.get('id')} | CLIENTE: {row.get('cliente')} | DATA: {row.get('data')} | DF: {row.get('data_finalizacao')}")
