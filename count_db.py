import os, requests
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://zkqzejnflpzknuuirlav.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS')
headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?data=eq.05/08/2026"
res = requests.get(url, headers=headers)
data = res.json()
print('Found', len(data), 'records for 05/08/2026')
for row in data:
    print(f"ID: {row.get('id')} | DATA: {row.get('data')} | DF: {row.get('data_finalizacao')}")
