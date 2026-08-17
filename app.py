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
        return jsonify({"status": "success", "data": []})
        
    import re
    from datetime import datetime
    
    date_pattern = r'(\d{2}/\d{2}(?:/\d{2,4})?)'
    dates = re.findall(date_pattern, q)
    
    target_status = None
    if "deslocamento" in q: target_status = "deslocamento"
    elif "bloqueio" in q: target_status = "bloqueio"
    elif "finalizado" in q: target_status = "finalizado"
    elif "pendente" in q: target_status = "pendente"

    try:
        raw_data = db_select_all()
        all_data = []
        min_date_global = datetime.strptime("01/08/2026", "%d/%m/%Y")
        
        for item in raw_data:
            item_date = parse_date_for_sort(item.get("data", ""))
            try:
                idt = datetime.strptime(item_date, "%Y-%m-%d")
                if idt >= min_date_global:
                    all_data.append(item)
            except:
                pass
        
        results = []
        
        if target_status and len(dates) >= 2:
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
                        
            start_date = parse_custom_date(dates[0])
            end_date = parse_custom_date(dates[-1])
            if start_date > end_date:
                start_date, end_date = end_date, start_date
                
            for item in all_data:
                item_date = parse_date_for_sort(item.get("data", ""))
                try:
                    idt = datetime.strptime(item_date, "%Y-%m-%d")
                except:
                    continue
                if start_date <= idt <= end_date:
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
                        
                    if st == target_status:
                        results.append(item)
        else:
            for item in all_data:
                # Busca a palavra-chave em qualquer campo do registro
                row_str = " ".join([str(v) for v in item.values() if v is not None]).lower()
                if q in row_str:
                    results.append(item)
                
        # Sort results by recent dates first
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
        # Sincroniza exclusões: deleta do Supabase coletas daquele dia que foram removidas da tela
        if data_operacao:
            try:
                variants = set(format_date_variants(data_operacao))
                existing_for_day = [item for item in db_select_all() if str(item.get("data", "")).strip() in variants]
                incoming_ids = set(str(c.get("id")) for c in coletas if c.get("id"))
                for ex in existing_for_day:
                    ex_id = str(ex.get("id"))
                    if ex_id and ex_id not in incoming_ids:
                        print(f"Deletando coleta excluida do Supabase: ID {ex_id}")
                        try:
                            db_delete(ex_id)
                        except Exception as del_err:
                            print(f"Erro ao deletar ID {ex_id}: {del_err}")
            except Exception as sync_err:
                print(f"Erro ao sincronizar exclusoes: {sync_err}")

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

            registro_final = {k: (None if v == "" or v == "-" else v) for k, v in registro.items()}

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
