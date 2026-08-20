import os
import time
import subprocess

REPO_DIR = os.path.dirname(os.path.abspath(__file__))

def check_for_updates():
    try:
        # Baixa as infos mais recentes do GitHub
        subprocess.check_call(['git', 'remote', 'update'], cwd=REPO_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Pega as versoes local e do github
        local = subprocess.check_output(['git', 'rev-parse', '@'], cwd=REPO_DIR).strip()
        remote = subprocess.check_output(['git', 'rev-parse', '@{u}'], cwd=REPO_DIR).strip()
        
        if local != remote:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Novas mudancas detectadas no GitHub! Atualizando o servidor...")
            subprocess.check_call(['git', 'pull'], cwd=REPO_DIR)
            print("Codigo atualizado! Reiniciando o sistema...")
            # Usa shell=True para o PM2 ser reconhecido facilmente no PATH
            subprocess.check_call('pm2 restart all', shell=True)
    except Exception as e:
        pass

if __name__ == "__main__":
    print("Atualizador Automatico Iniciado. Checando o GitHub a cada 60 segundos...")
    while True:
        check_for_updates()
        time.sleep(60)
