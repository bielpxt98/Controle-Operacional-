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
    fixed_count = 0
    for row in data:
        df = row.get('data_finalizacao')
        rec_id = row.get('id')
        if df and df != '05/08/2026' and rec_id < 410: # Only fixing old records
            # Update the record
            patch_url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=eq.{rec_id}"
            patch_res = requests.patch(patch_url, headers=get_headers(), json={'data': df})
            if patch_res.status_code in [200, 204]:
                print(f"Fixed ID {rec_id}: Set data to {df}")
                fixed_count += 1
            else:
                print(f"Failed to fix ID {rec_id}: {patch_res.status_code} {patch_res.text}")
    print(f"Fixed {fixed_count} records.")
else:
    print('Failed to fetch:', res.status_code, res.text)
