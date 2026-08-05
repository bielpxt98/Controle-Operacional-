import os, requests
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://zkqzejnflpzknuuirlav.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS')
headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}', 'Content-Type': 'application/json', 'Prefer': 'return=representation'}
url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=eq.414"
res = requests.patch(url, headers=headers, json={'data': '03/08/2026', 'data_finalizacao': '03/08/2026'})
print(res.status_code)
