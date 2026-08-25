import os
from flask import Flask, render_template, request, jsonify, send_file
import requests
import pandas as pd
from io import BytesIO
from datetime import datetime

app = Flask(__name__, static_folder="static", template_folder="templates")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zkqzejnflpzknuuirlav.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS")

def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def format_date_variants(date_str):
    if not date_str:
        return []
    variants = [date_str.strip()]
    try:
        if "/" in date_str:
            parts = [p.strip() for p in date_str.split("/")]
            if len(parts) == 3:
                day, month, year = parts[0], parts[1], parts[2]
                day_pad, month_pad = day.zfill(2), month.zfill(2)
                day_raw, month_raw = str(int(day)), str(int(month))
                
                variants.append(f"{day_pad}/{month_pad}/{year}")
                variants.append(f"{day_raw}/{month_raw}/{year}")
                variants.append(f"{day_raw}/{month_pad}/{year}")
                variants.append(f"{day_pad}/{month_raw}/{year}")
                
                variants.append(f"{year}-{month_pad}-{day_pad}")
                variants.append(f"{year}-{month_raw}-{day_raw}")
        elif "-" in date_str:
            parts = [p.strip() for p in date_str.split("-")]
            if len(parts) == 3:
                year, month, day = parts[0], parts[1], parts[2]
                day_pad, month_pad = day.zfill(2), month.zfill(2)
                day_raw, month_raw = str(int(day)), str(int(month))
                
                variants.append(f"{day_pad}/{month_pad}/{year}")
                variants.append(f"{day_raw}/{month_raw}/{year}")
                variants.append(f"{year}-{month_pad}-{day_pad}")
                variants.append(f"{year}-{month_raw}-{day_raw}")
    except Exception:
        pass
    return list(set(variants))

def parse_date_for_sort(date_str):
    if not date_str:
        return datetime.min
    d_str = str(date_str).strip()
    try:
        if "/" in d_str:
            parts = d_str.split("/")
            if len(parts) == 3:
                # DD/MM/YYYY
                return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
        elif "-" in d_str:
            parts = d_str.split("-")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    # YYYY-MM-DD
                    return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                else:
                    # DD-MM-YYYY
                    return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
    except Exception:
        pass
    return datetime.min

def sanitize_number(val):
    if val is None or val == "" or val == "-":
        return None
    try:
        return int(float(str(val).replace(",", ".")))
    except Exception:
        return None

def parse_valor_numeric(val):
    if val is None or val == "" or val == "-" or str(val).strip() == "":
        return None
    try:
        clean = str(val).replace("R$", "").replace(" ", "").replace("\xa0", "").strip()
        if "," in clean:
            clean = clean.replace(".", "").replace(",", ".")
        return float(clean)
    except Exception:
        return None

def get_real_table_columns():
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?select=*&limit=1"
        res = requests.get(url, headers=get_headers(), timeout=5)
        if res.status_code == 200 and res.json():
            return set(res.json()[0].keys())
    except Exception as e:
        print(f"Erro ao consultar colunas reais: {e}")

def db_select_all():
    """Busca todos os registros do Supabase sem filtro de data (para pesquisa global)."""
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?select=*&order=id.asc"
        res = requests.get(url, headers=get_headers(), timeout=12)
        if res.status_code in [200, 201, 206]:
            return res.json()
        print(f"Erro em db_select_all: HTTP {res.status_code} - {res.text}")
        return []
    except Exception as e:
        print(f"Erro em db_select_all: {e}")
        return []


def db_update_by_id(rec_id, registro):
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=eq.{rec_id}"
    res = requests.patch(url, headers=get_headers(), json=registro, timeout=12)
    if res.status_code in [200, 204]:
        return res.json() if res.content else [{"id": rec_id, **registro}]
    raise Exception(f"HTTP {res.status_code}: {res.text}")

def db_insert_new(registro):
    headers = get_headers()
    headers["Prefer"] = "return=representation, resolution=merge-duplicates"
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?on_conflict=delivery"
    res = requests.post(url, headers=headers, json=registro, timeout=12)
    if res.status_code in [200, 201]:
        return res.json()
    raise Exception(f"HTTP {res.status_code}: {res.text}")

def db_delete(id_coleta):
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=eq.{id_coleta}"
    res = requests.delete(url, headers=get_headers(), timeout=12)
    if res.status_code in [200, 204]:
        return True
    raise Exception(f"HTTP {res.status_code}: {res.text}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/ping", methods=["GET"])
def ping():
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?select=id&limit=1"
        res = requests.get(url, headers=get_headers(), timeout=5)
        return jsonify({"status": "online", "render": "OK", "supabase": "OK" if res.status_code in [200, 201] else "PAUSED"}), 200
    except Exception as e:
        return jsonify({"status": "online", "render": "OK", "supabase": str(e)}), 200

@app.route("/api/search", methods=["GET"])
def search_coletas():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"status": "success", "data": [], "total": 0})
        
    import re
    from datetime import datetime
    
    date_pattern = r'(\d{2}/\d{2}(?:/\d{2,4})?)'
    dates = re.findall(date_pattern, q)
    
    # Extrair linguagem natural como "dia 10 ao dia 20" ou "do dia 10 ao 20"
    if not dates:
        nat_pattern = r'(?:do\s+)?(?:dia\s+)?(\d{1,2})\s+(?:a|ao|ate|at[eé])\s+(?:o\s+)?(?:dia\s+)?(\d{1,2})'
        nat_match = re.search(nat_pattern, q)
        if nat_match:
            d1, d2 = nat_match.groups()
            curr_month = datetime.now().month
            curr_year = datetime.now().year
            dates = [f"{int(d1):02d}/{curr_month:02d}/{curr_year}", f"{int(d2):02d}/{curr_month:02d}/{curr_year}"]
            q = re.sub(nat_pattern, '', q).strip()
            
    # Extrair também buscas por um único dia "dia 10"
    if not dates:
        single_day_pattern = r'dia\s+(\d{1,2})'
        single_match = re.search(single_day_pattern, q)
        if single_match:
            d1 = single_match.group(1)
            curr_month = datetime.now().month
            curr_year = datetime.now().year
            dates = [f"{int(d1):02d}/{curr_month:02d}/{curr_year}", f"{int(d1):02d}/{curr_month:02d}/{curr_year}"]
            q = re.sub(single_day_pattern, '', q).strip()
    
    target_status = None
    if "deslocamento" in q: target_status = "deslocamento"
    elif "bloqueio" in q: target_status = "bloqueio"
    elif "finalizado" in q: target_status = "finalizado"
    elif "pendente" in q: target_status = "pendente"

    try:
        all_data = db_select_all()
        results = []
        
        def parse_custom_date(ds):
            parts = ds.split('/')
            if len(parts) == 2:
                ds = f"{ds}/{datetime.now().year}"
            try:
                return datetime.strptime(ds, "%d/%m/%Y")
            except:
                try:
                    return datetime.strptime(ds, "%d/%m/%y")
                except:
                    return datetime.min
        
        start_date = None
        end_date = None
        if len(dates) >= 2:
            start_date = parse_custom_date(dates[0])
            end_date = parse_custom_date(dates[-1])
            if start_date > end_date:
                start_date, end_date = end_date, start_date

        search_terms = q.split()

        for item in all_data:
            item_date = parse_date_for_sort(item.get("data", ""))
            try:
                idt = datetime.strptime(item_date, "%Y-%m-%d")
            except:
                continue
                
            pc_val = sanitize_number(item.get("pc"))
            hl = item.get("l_horario")
            hc = item.get("c_horario")
            hf = item.get("f_horario")
            obs = str(item.get("observacao") or item.get("observacoes") or item.get("motivo") or "").lower()
            
            st = "pendente"
            if (pc_val is not None and pc_val > 0 and hl and hc and hf):
                st = "finalizado"
            elif (pc_val is None or pc_val == 0) and hl and hf and "bloqueio" in obs:
                st = "bloqueio"
            elif (pc_val is None or pc_val == 0) and hl and hf and "deslocamento" in obs:
                st = "deslocamento"

            if target_status and len(dates) >= 2:
                if start_date <= idt <= end_date and st == target_status:
                    results.append(item)
            elif target_status:
                if st == target_status:
                    row_str = " ".join([str(v) for v in item.values() if v is not None]).lower()
                    other_terms = [t for t in search_terms if t != target_status]
                    if all(t in row_str for t in other_terms):
                        results.append(item)
            else:
                row_str = " ".join([str(v) for v in item.values() if v is not None]).lower() + f" {st}"
                if all(t in row_str for t in search_terms):
                    results.append(item)
                
        results.sort(key=lambda x: parse_date_for_sort(x.get("data", "")), reverse=True)
        
        return jsonify({"status": "success", "data": results, "total": len(results)})
    except Exception as e:
        print(f"Erro em search_coletas: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/check_delivery", methods=["GET"])
def check_delivery():
    delivery = request.args.get("delivery", "").strip()
    exclude_id = request.args.get("exclude_id", "").strip()
    if not delivery:
        return jsonify({"status": "error", "message": "Delivery não fornecido"}), 400
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?delivery=eq.{delivery}&select=*&order=id.asc"
        res = requests.get(url, headers=get_headers(), timeout=5)
        if res.status_code in [200, 201, 206]:
            records = res.json()
            # Filtra o exclude_id se necessário
            if exclude_id:
                records = [r for r in records if str(r.get("id")) != exclude_id]
            
            if records:
                # Retorna o registro mais recente
                records.sort(key=lambda x: parse_date_for_sort(x.get("data", "")), reverse=True)
                return jsonify({"status": "success", "exists": True, "data": records[0]})
            return jsonify({"status": "success", "exists": False})
        return jsonify({"status": "error", "message": "Erro ao consultar Supabase"}), 500
    except Exception as e:
        print(f"Erro em check_delivery: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/coletas", methods=["GET"])
def get_coletas():
    data_filtro = request.args.get("data")
    try:
        all_data = db_select_all()
        if data_filtro:
            variants = set(format_date_variants(data_filtro))
            filtered = [item for item in all_data if str(item.get("data", "")).strip() in variants]
            return jsonify({"status": "success", "data": filtered})
        return jsonify({"status": "success", "data": all_data})
    except Exception as e:
        print(f"Erro em GET /api/coletas: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/coletas", methods=["POST"])
def save_coletas():
    payload = request.json or {}
    coletas = payload.get("coletas", [])
    data_operacao = payload.get("data")

    real_cols = get_real_table_columns()

    try:
        # A sincronizacao de exclusoes automatica foi removida para seguranca.

        existing_data = db_select_all()
        existing_items = {str(r.get("id")): r for r in existing_data}
        
        saved_items = []
        for item in coletas:
            obs_value = str(item.get("observacao") or item.get("motivo") or item.get("observacoes") or "").strip()
            valor_raw = item.get("valor") or item.get("valor_frete") or item.get("valor_total") or item.get("val_frete")
            valor_num = parse_valor_numeric(valor_raw)
            f_horario_val = str(item.get("f_horario") or "").strip()
            
            # DF editável enviado do formulário ou auto-sugerido
            df_user_val = str(item.get("df") or item.get("data_finalizacao") or "").strip()
            if not df_user_val and f_horario_val and f_horario_val != "-":
                df_user_val = data_operacao

            raw_registro = {
                "data": data_operacao or item.get("data"),
                "motorista": item.get("motorista") or "",
                "delivery": item.get("delivery") or "",
                "cliente": item.get("cliente") or "",
                "paletes": sanitize_number(item.get("paletes")),
                "pc": sanitize_number(item.get("pc")),
                "valor": valor_num,
                "valor_frete": valor_num,
                "valor_total": valor_num,
                "val_frete": valor_num,
                "l_horario": str(item.get("l_horario") or "").strip() or None,
                "c_horario": str(item.get("c_horario") or "").strip() or None,
                "f_horario": f_horario_val or None,
                "data_finalizacao": df_user_val if df_user_val else None,
                "df": df_user_val if df_user_val else None,
                "sr": str(item.get("sr") or "").strip() or None,
                "observacoes": obs_value if obs_value else None,
                "observacao": obs_value if obs_value else None,
                "cpf": str(item.get("cpf") or "").strip() or None,
                "cavalo": str(item.get("cavalo") or "").strip() or None,
                "carreta": str(item.get("carreta") or "").strip() or None
            }

            if real_cols:
                registro = {k: v for k, v in raw_registro.items() if k in real_cols and k != "id"}
            else:
                registro = raw_registro

            registro_final = {}
            protected_fields = ["l_horario", "c_horario", "f_horario", "pc", "motorista"]
            existing = existing_items.get(str(item.get("id", "")), {})
            
            for k, v in registro.items():
                is_empty_stale = (v is None or str(v).strip() == "")
                is_explicit_clear = (str(v).strip() == "-")
                
                if is_empty_stale and k in protected_fields and existing.get(k):
                    continue  # Mantem o valor existente no banco (protege contra overwrite do frontend)
                    
                if is_explicit_clear:
                    registro_final[k] = None # Delecao explicita autorizada
                else:
                    registro_final[k] = None if is_empty_stale else v

            rec_id = item.get("id")
            is_valid_id = rec_id is not None and str(rec_id).isdigit() and int(rec_id) > 0

            if is_valid_id:
                res = db_update_by_id(int(rec_id), registro_final)
            else:
                res = db_insert_new(registro_final)

            saved_items.extend(res if isinstance(res, list) else [res])

        return jsonify({"status": "success", "message": "Coletas salvas com sucesso no Supabase!", "saved": saved_items})
    except Exception as e:
        print(f"Erro em POST /api/coletas: {e}")
        return jsonify({"status": "error", "message": f"Erro no Supabase: {str(e)}"}), 500

@app.route("/api/coletas/<id_coleta>", methods=["DELETE"])
def delete_coleta(id_coleta):
    try:
        db_delete(id_coleta)
        return jsonify({"status": "success", "message": "Coleta excluída com sucesso."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/delete-old", methods=["POST"])
def delete_old_records():
    try:
        all_data = db_select_all()
        min_date = datetime.strptime("01/08/2026", "%d/%m/%Y")
        deleted = 0
        for item in all_data:
            item_date = parse_date_for_sort(item.get("data", ""))
            try:
                idt = datetime.strptime(item_date, "%Y-%m-%d")
                if idt < min_date:
                    item_id = item.get("id")
                    if item_id:
                        db_delete(str(item_id))
                        deleted += 1
            except:
                pass
        return jsonify({"status": "success", "deleted": deleted})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/export-excel", methods=["GET"])
def export_excel():
    data_filtro = request.args.get("data")
    month_str = request.args.get("month")
    year_str = request.args.get("year")
    all_str = request.args.get("all")

    try:
        all_data = db_select_all()
        sheet_name = "Coletas"
        filename = "Relatorio_Coletas.xlsx"

        if all_str:
            data = all_data
            filename = "Relatorio_Projeto_Todo.xlsx"
            sheet_name = "Projeto Todo"
        elif month_str and year_str:
            suffix = f"/{month_str}/{year_str}"
            data = [d for d in all_data if str(d.get("data", "")).strip().endswith(suffix)]
            filename = f"Relatorio_Mes_{month_str}_{year_str}.xlsx"
            sheet_name = f"Mes {month_str}-{year_str}"
        elif data_filtro:
            variants = set(format_date_variants(data_filtro))
            data = [d for d in all_data if str(d.get("data", "")).strip() in variants]
            filename = f"Relatorio_{data_filtro.replace('/', '_')}.xlsx"
            sheet_name = f"Dia {data_filtro.replace('/', '-')}"
        else:
            data = all_data

        if not data:
            df = pd.DataFrame(columns=[
                "MOTORISTA", "DELIVERY", "CLIENTES", "PALETES", "PALETES COLETADO",
                "VALOR", "H_LOCAL", "H_COLETADO", "H_FINALIZADO", "DATA FINALIZACAO (DF)", "SR", "MOTIVO", "CPF", "CAVALO", "CARRETA"
            ])
        else:
            rows = []
            for d in data:
                val_raw = d.get("valor") or d.get("valor_frete") or d.get("valor_total") or d.get("val_frete")
                if isinstance(val_raw, (int, float)):
                    val_display = f"R$ {val_raw:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
                else:
                    val_display = str(val_raw or "")
                
                df_display = d.get("df") or d.get("data_finalizacao") or ""
                rows.append({
                    "MOTORISTA": d.get("motorista", ""),
                    "DELIVERY": d.get("delivery", ""),
                    "CLIENTES": d.get("cliente", ""),
                    "PALETES": d.get("paletes", ""),
                    "PALETES COLETADO": d.get("pc", ""),
                    "VALOR": val_display,
                    "H_LOCAL": d.get("l_horario", ""),
                    "H_COLETADO": d.get("c_horario", ""),
                    "H_FINALIZADO": d.get("f_horario", ""),
                    "DATA FINALIZACAO (DF)": df_display,
                    "SR": d.get("sr", ""),
                    "MOTIVO": d.get("motivo") or d.get("observacoes") or d.get("observacao") or "",
                    "CPF": d.get("cpf", ""),
                    "CAVALO": d.get("cavalo", ""),
                    "CARRETA": d.get("carreta", "")
                })
            df = pd.DataFrame(rows)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
            
            # Ajuste auto width para colunas
            worksheet = writer.sheets[sheet_name[:31]]
            for idx, col in enumerate(df.columns):
                worksheet.column_dimensions[chr(65 + idx)].width = 20
                
        output.seek(0)
        return send_file(output, download_name=filename, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/whatsapp")
def whatsapp_qr():
    import os as _os
    import time
    qr_path = _os.path.join(app.static_folder, "qr.png")
    if _os.path.exists(qr_path):
        ts = int(time.time())
        return f"<h1>Conecte o WhatsApp</h1><p>Escaneie o QR Code abaixo:</p><img src='/static/qr.png?t={ts}' style='width:300px'/><p>Atualize a pagina em 10 seg.</p>"
    return "<h1>WhatsApp Conectado!</h1><p>Bot ativo e monitorando mensagens.</p>"


@app.route("/logs")
def view_logs():
    import subprocess
    try:
        log_out = subprocess.check_output(["pm2", "logs", "RoboWPP", "--lines", "100", "--nostream"], text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        log_out = f"Erro ao ler logs via PM2: {str(e)}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Logs do Robo WhatsApp & CHEP</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {{ background: #0d1117; color: #c9d1d9; font-family: monospace; padding: 20px; }}
            h2 {{ color: #58a6ff; margin-bottom: 5px; }}
            p {{ color: #8b949e; margin-top: 0; font-size: 14px; }}
            pre {{ background: #161b22; padding: 15px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; font-size: 13px; line-height: 1.5; border: 1px solid #30363d; }}
        </style>
    </head>
    <body>
        <h2>📋 Logs do Robo (WhatsApp + CHEP)</h2>
        <p>Atualizando automaticamente a cada 5 segundos...</p>
        <pre>{log_out}</pre>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
