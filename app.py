import os
from flask import Flask, render_template, request, jsonify, send_file
import requests
import pandas as pd
from io import BytesIO

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
    variants = [date_str]
    try:
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                iso_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                variants.append(iso_date)
        elif "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                br_date = f"{parts[2].zfill(2)}/{parts[1].zfill(2)}/{parts[0]}"
                variants.append(br_date)
    except Exception:
        pass
    return list(set(variants))

def sanitize_number(val):
    if val is None or val == "" or val == "-":
        return None
    try:
        return int(float(str(val).replace(",", ".")))
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
    return None

def db_select_all():
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?select=*"
    res = requests.get(url, headers=get_headers(), timeout=12)
    if res.status_code in [200, 201]:
        return res.json()
    raise Exception(f"HTTP {res.status_code}: {res.text}")

def db_update_by_id(rec_id, registro):
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=eq.{rec_id}"
    res = requests.patch(url, headers=get_headers(), json=registro, timeout=12)
    if res.status_code in [200, 204]:
        return res.json() if res.content else [{"id": rec_id, **registro}]
    raise Exception(f"HTTP {res.status_code}: {res.text}")

def db_insert_new(registro):
    headers = get_headers()
    headers["Prefer"] = "return=representation"
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries"
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
        saved_items = []
        for item in coletas:
            obs_value = str(item.get("observacao") or item.get("motivo") or item.get("observacoes") or "")
            
            raw_registro = {
                "data": data_operacao or item.get("data"),
                "motorista": item.get("motorista") or "",
                "delivery": item.get("delivery") or "",
                "cliente": item.get("cliente") or "",
                "paletes": sanitize_number(item.get("paletes")),
                "pc": sanitize_number(item.get("pc")),
                "valor": str(item.get("valor") or ""),
                "l_horario": str(item.get("l_horario") or ""),
                "c_horario": str(item.get("c_horario") or ""),
                "f_horario": str(item.get("f_horario") or ""),
                "sr": str(item.get("sr") or ""),
                "observacoes": obs_value,
                "cpf": str(item.get("cpf") or ""),
                "cavalo": str(item.get("cavalo") or ""),
                "carreta": str(item.get("carreta") or "")
            }

            # Filtra para remover a chave 'id' do payload e chaves inexistentes no banco
            if real_cols:
                registro = {k: v for k, v in raw_registro.items() if k in real_cols and k != "id"}
            else:
                registro = raw_registro

            rec_id = item.get("id")
            is_valid_id = rec_id is not None and str(rec_id).isdigit() and int(rec_id) > 0

            if is_valid_id:
                # Atualização de registro existente por ID (PATCH)
                res = db_update_by_id(int(rec_id), registro)
            else:
                # Criação de novo registro sem o ID (POST) -> Postgres gera o ID automaticamente!
                res = db_insert_new(registro)

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
    try:
        all_data = db_select_all()
        if data_filtro:
            variants = set(format_date_variants(data_filtro))
            data = [d for d in all_data if str(d.get("data", "")).strip() in variants]
        else:
            data = all_data

        if not data:
            df = pd.DataFrame(columns=[
                "MOTORISTA", "DELIVERY", "CLIENTES", "PALETES", "PALETES COLETADO",
                "VALOR", "H_LOCAL", "H_COLETADO", "H_FINALIZADO", "SR", "MOTIVO", "CPF", "CAVALO", "CARRETA"
            ])
        else:
            rows = []
            for d in data:
                rows.append({
                    "MOTORISTA": d.get("motorista", ""),
                    "DELIVERY": d.get("delivery", ""),
                    "CLIENTES": d.get("cliente", ""),
                    "PALETES": d.get("paletes", ""),
                    "PALETES COLETADO": d.get("pc", ""),
                    "VALOR": d.get("valor", ""),
                    "H_LOCAL": d.get("l_horario", ""),
                    "H_COLETADO": d.get("c_horario", ""),
                    "H_FINALIZADO": d.get("f_horario", ""),
                    "SR": d.get("sr", ""),
                    "MOTIVO": d.get("observacoes") or d.get("observacao") or "",
                    "CPF": d.get("cpf", ""),
                    "CAVALO": d.get("cavalo", ""),
                    "CARRETA": d.get("carreta", "")
                })
            df = pd.DataFrame(rows)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Coletas")
        output.seek(0)

        filename = f"Relatorio_Coletas_{data_filtro.replace('/', '_') if data_filtro else 'Geral'}.xlsx"
        return send_file(output, download_name=filename, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
