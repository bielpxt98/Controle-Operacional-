import os, requests
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://zkqzejnflpzknuuirlav.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS')
headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=eq.5"
res = requests.get(url, headers=headers)
print(res.json())
