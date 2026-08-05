import os, requests
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://zkqzejnflpzknuuirlav.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS')
headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?motorista=eq.-- SELECIONE --"
res = requests.delete(url, headers=headers)
print("Deleted empty rows:", res.status_code)
url2 = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?motorista=eq."
res2 = requests.delete(url2, headers=headers)
print("Deleted empty rows 2:", res2.status_code)
