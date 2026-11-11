# -*- coding: utf-8 -*-
"""
Gerenciador e Restaurador Inteligente de Backups de Coletas (Supabase)
Autor: Antigravity / Google DeepMind
"""

import os
import sys
import json
import time
from datetime import datetime
import requests
import pandas as pd

SUPABASE_URL = "https://zkqzejnflpzknuuirlav.supabase.co"
SUPABASE_KEY = "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

BACKUP_DIR = r"C:\Users\TRANSRAP05\Desktop\Backups_Coletas_Excel"
os.makedirs(BACKUP_DIR, exist_ok=True)


def get_all_supabase_coletas():
    """Baixa todas as coletas do Supabase com ordenação por ID."""
    url = f"{SUPABASE_URL}/rest/v1/deliveries?select=*&order=id.asc"
    res = requests.get(url, headers=HEADERS, timeout=15)
    if res.status_code in [200, 206]:
        return res.json()
    raise Exception(f"Erro ao consultar Supabase: Status {res.status_code} - {res.text}")


def salvar_backup_completo(trigger="manual"):
    """Gera um snapshot em JSON e planilha Excel formatada (.xlsx)."""
    print("\n⏳ Conectando ao Supabase para coletar todos os registros...")
    coletas = get_all_supabase_coletas()
    if not coletas:
        print("❌ Nenhuma coleta encontrada no banco de dados.")
        return None

    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    data_formatada = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    json_path = os.path.join(BACKUP_DIR, f"Backup_Coletas_{timestamp_str}.json")
    xlsx_path = os.path.join(BACKUP_DIR, f"Backup_Coletas_{timestamp_str}.xlsx")

    # 1. Salva arquivo JSON completo
    backup_payload = {
        "timestamp": timestamp_str,
        "data_formatada": data_formatada,
        "tipo": trigger,
        "total": len(coletas),
        "coletas": coletas
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(backup_payload, f, ensure_ascii=False, indent=2)

    # 2. Salva arquivo Excel (.xlsx) com layout limpo e legível
    df_rows = []
    for c in coletas:
        df_rows.append({
            "ID": c.get("id"),
            "Data da Coleta": c.get("data"),
            "Delivery": c.get("delivery"),
            "Cliente": c.get("cliente"),
            "Motorista": c.get("motorista"),
            "Paletes Agendados": c.get("paletes"),
            "Paletes Coletados (PC)": c.get("pc"),
            "Valor Frete": c.get("valor_frete"),
            "Valor Final": c.get("valor_final"),
            "H_Local (Chegada)": c.get("l_horario"),
            "H_Coletado": c.get("c_horario"),
            "H_Finalizado": c.get("f_horario"),
            "Data Finalização (DF)": c.get("data_finalizacao") or c.get("df"),
            "SR": c.get("sr"),
            "Observações / Motivo": c.get("observacoes") or c.get("motivo"),
            "Cavalo": c.get("cavalo"),
            "Carreta": c.get("carreta"),
            "Status": c.get("status")
        })

    df = pd.DataFrame(df_rows)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Todas as Coletas")
        ws = writer.sheets["Todas as Coletas"]
        for idx, col in enumerate(df.columns):
            col_letter = chr(65 + idx) if idx < 26 else f"A{chr(65 + idx - 26)}"
            lens = [len(str(val)) for val in df[col].dropna().values]
            max_len = max(lens + [len(col)]) + 3 if lens else len(col) + 3
            ws.column_dimensions[col_letter].width = min(max_len, 40)

    print(f"✅ Backup concluído com sucesso!")
    print(f"📊 Total de coletas salvas: {len(coletas)}")
    print(f"📁 Planilha Excel: {xlsx_path}")
    print(f"📁 Arquivo JSON:    {json_path}\n")
    return json_path


def listar_backups_existentes():
    """Lista todos os backups JSON encontrados no diretório ordenados do mais recente ao mais antigo."""
    files = [f for f in os.listdir(BACKUP_DIR) if f.startswith("Backup_Coletas_") and f.endswith(".json")]
    files.sort(reverse=True)
    return [os.path.join(BACKUP_DIR, f) for f in files]


def verificar_e_restaurar_deslocamento(backup_path=None):
    """
    Compara o estado atual do Supabase com o backup.
    Se alguma coleta mudou de dia indevidamente, ou teve horários/paletes alterados,
    detecta a divergência e restaura para o estado original.
    """
    backups = listar_backups_existentes()
    if not backups:
        print("❌ Nenhum arquivo de backup encontrado para comparar.")
        return

    if not backup_path:
        backup_path = backups[0]

    with open(backup_path, "r", encoding="utf-8") as f:
        bkp_data = json.load(f)

    coletas_bkp = bkp_data.get("coletas", [])
    bkp_data_fmt = bkp_data.get("data_formatada", "Desconhecida")
    print(f"\n🔍 Comparando dados atuais com o backup de [{bkp_data_fmt}] ({len(coletas_bkp)} coletas no backup)...")

    atuais = get_all_supabase_coletas()
    atuais_map = {c.get("id"): c for c in atuais if c.get("id")}

    divergencias_data = []
    divergencias_dados = []

    for c_bkp in coletas_bkp:
        cid = c_bkp.get("id")
        if not cid:
            continue
        c_atual = atuais_map.get(cid)
        if not c_atual:
            continue

        data_bkp = str(c_bkp.get("data") or "").strip()
        data_atual = str(c_atual.get("data") or "").strip()
        deliv = c_bkp.get("delivery") or "-"
        cli = c_bkp.get("cliente") or "-"
        mot = c_bkp.get("motorista") or "-"

        # 1. Checa mudança indevida de data
        if data_bkp != data_atual:
            divergencias_data.append({
                "id": cid,
                "delivery": deliv,
                "cliente": cli,
                "motorista": mot,
                "data_original": data_bkp,
                "data_atual": data_atual,
                "bkp_record": c_bkp
            })
        else:
            # 2. Checa perda de horários ou paletes
            pc_bkp = c_bkp.get("pc")
            pc_atual = c_atual.get("pc")
            h_bkp = c_bkp.get("c_horario")
            h_atual = c_atual.get("c_horario")
            if (pc_bkp and not pc_atual) or (h_bkp and not h_atual):
                divergencias_dados.append({
                    "id": cid,
                    "delivery": deliv,
                    "cliente": cli,
                    "bkp_record": c_bkp
                })

    if not divergencias_data and not divergencias_dados:
        print("✅ Nenhuma coleta saiu do lugar! Todas as datas e dados estão 100% íntegros de acordo com o backup.\n")
        return

    if divergencias_data:
        print(f"\n⚠️  ATENÇÃO: Foram encontradas {len(divergencias_data)} coleta(s) com DATA DIFERENTE do backup:")
        for div in divergencias_data:
            print(f"  • ID {div['id']} | Deliv: {div['delivery']} ({div['cliente']})")
            print(f"    Data no Backup: {div['data_original']}  --->  Data Atual: {div['data_atual']}")

    if divergencias_dados:
        print(f"\n⚠️  ATENÇÃO: Foram encontradas {len(divergencias_dados)} coleta(s) com horários/paletes desatualizados em relação ao backup.")

    resposta = input("\n👉 Deseja restaurar essas coletas de volta para a data e dados originais do backup? (S/N): ").strip().upper()
    if resposta != "S":
        print("Operação cancelada pelo usuário.\n")
        return

    print("\n⏳ Restaurando no Supabase...")
    total_restaurado = 0
    alvos = divergencias_data + divergencias_dados
    for item in alvos:
        cid = item["id"]
        c_bkp = item["bkp_record"]
        patch_payload = {
            "data": c_bkp.get("data"),
            "delivery": c_bkp.get("delivery"),
            "cliente": c_bkp.get("cliente"),
            "motorista": c_bkp.get("motorista"),
            "paletes": c_bkp.get("paletes"),
            "pc": c_bkp.get("pc"),
            "valor_frete": c_bkp.get("valor_frete"),
            "valor_final": c_bkp.get("valor_final"),
            "l_horario": c_bkp.get("l_horario"),
            "c_horario": c_bkp.get("c_horario"),
            "f_horario": c_bkp.get("f_horario"),
            "data_finalizacao": c_bkp.get("data_finalizacao") or c_bkp.get("df"),
            "sr": c_bkp.get("sr"),
            "observacoes": c_bkp.get("observacoes") or c_bkp.get("motivo"),
            "cavalo": c_bkp.get("cavalo"),
            "carreta": c_bkp.get("carreta"),
            "status": c_bkp.get("status"),
            "atualizado_em": datetime.utcnow().isoformat()
        }
        url = f"{SUPABASE_URL}/rest/v1/deliveries?id=eq.{cid}"
        res = requests.patch(url, headers=HEADERS, json=patch_payload, timeout=8)
        if res.status_code in [200, 204]:
            total_restaurado += 1
            print(f"  ✓ Coleta ID {cid} (Deliv: {c_bkp.get('delivery')}) restaurada com sucesso para {c_bkp.get('data')}.")
        else:
            print(f"  ✗ Erro ao restaurar ID {cid}: Status {res.status_code} - {res.text}")

    print(f"\n🎉 Concluído! {total_restaurado} coleta(s) restaurada(s) exatamente para o estado do backup!\n")


def restaurar_ponto_completo():
    """Permite selecionar um backup salvo para restaurar todas as coletas integralmente."""
    backups = listar_backups_existentes()
    if not backups:
        print("❌ Nenhum backup salvo encontrado.")
        return

    print("\n📋 Backups salvos disponíveis:")
    for idx, b in enumerate(backups[:10]):
        filename = os.path.basename(b)
        print(f"  [{idx + 1}] {filename}")

    esc = input("\n👉 Escolha o número do backup que deseja restaurar (ou Enter para cancelar): ").strip()
    if not esc.isdigit() or int(esc) < 1 or int(esc) > min(10, len(backups)):
        print("Restauração cancelada.\n")
        return

    escolhido = backups[int(esc) - 1]
    with open(escolhido, "r", encoding="utf-8") as f:
        bkp = json.load(f)

    coletas = bkp.get("coletas", [])
    data_fmt = bkp.get("data_formatada", "Data Desconhecida")

    aviso = f"\n⚠️  ATENÇÃO: Você escolheu restaurar TODAS as {len(coletas)} coletas para o estado de [{data_fmt}].\nTem certeza absoluta? Digite SIM para prosseguir: "
    conf = input(aviso).strip().upper()
    if conf != "SIM":
        print("Operação cancelada.\n")
        return

    print("\n⏳ Restaurando banco de dados...")
    sucesso = 0
    for c in coletas:
        cid = c.get("id")
        if not cid:
            continue
        patch_payload = {
            "data": c.get("data"),
            "delivery": c.get("delivery"),
            "cliente": c.get("cliente"),
            "motorista": c.get("motorista"),
            "paletes": c.get("paletes"),
            "pc": c.get("pc"),
            "valor_frete": c.get("valor_frete"),
            "valor_final": c.get("valor_final"),
            "l_horario": c.get("l_horario"),
            "c_horario": c.get("c_horario"),
            "f_horario": c.get("f_horario"),
            "data_finalizacao": c.get("data_finalizacao") or c.get("df"),
            "sr": c.get("sr"),
            "observacoes": c.get("observacoes") or c.get("motivo"),
            "cavalo": c.get("cavalo"),
            "carreta": c.get("carreta"),
            "status": c.get("status"),
            "atualizado_em": datetime.utcnow().isoformat()
        }
        url = f"{SUPABASE_URL}/rest/v1/deliveries?id=eq.{cid}"
        res = requests.patch(url, headers=HEADERS, json=patch_payload, timeout=8)
        if res.status_code in [200, 204]:
            sucesso += 1

    print(f"🎉 Restauração concluída! {sucesso} coletas restauradas com sucesso.\n")


def menu():
    while True:
        print("=" * 65)
        print("🛡️  SISTEMA DE BACKUP & PROTEÇÃO DE COLETAS (SUPABASE & EXCEL)")
        print("=" * 65)
        print("  [1] 📥 Salvar Backup Agora (Gera Excel .xlsx e JSON completo)")
        print("  [2] 🔍 Verificar se coletas mudaram de dia e restaurar")
        print("  [3] ⏪ Restaurar tudo a partir de um backup anterior")
        print("  [4] 📂 Abrir pasta dos arquivos Excel de Backup")
        print("  [0] 🚪 Sair")
        print("=" * 65)

        opc = input("👉 Escolha uma opção [0-4]: ").strip()
        if opc == "1":
            salvar_backup_completo("manual")
        elif opc == "2":
            verificar_e_restaurar_deslocamento()
        elif opc == "3":
            restaurar_ponto_completo()
        elif opc == "4":
            os.system(f'explorer "{BACKUP_DIR}"')
        elif opc == "0":
            print("Encerrando.")
            break
        else:
            print("Opção inválida.")
        input("\nPressione Enter para continuar...")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--backup":
            salvar_backup_completo("auto")
            sys.exit(0)
        elif sys.argv[1] == "--verificar":
            verificar_e_restaurar_deslocamento()
            sys.exit(0)
    menu()
