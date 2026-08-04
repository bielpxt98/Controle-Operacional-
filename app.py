import os
from flask import Flask, render_template, request, jsonify, send_file
from supabase import create_client
import pandas as pd
from io import BytesIO
from datetime import datetime

app = Flask(__name__, static_folder="static", template_folder="templates")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zkqzejnflpzknuuirlav.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def format_date_variants(date_str):
    """Retorna uma lista com variações de data (03/08/2026 e 2026-08-03) para buscar no Supabase sem erros."""
    if not date_str:
        return []
    variants = [date_str]
    try:
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                # DD/MM/YYYY -> YYYY-MM-DD
                iso_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                variants.append(iso_date)
        elif "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                # YYYY-MM-DD -> DD/MM/YYYY
                br_date = f"{parts[2].zfill(2)}/{parts[1].zfill(2)}/{parts[0]}"
                variants.append(br_date)
    except Exception:
        pass
    return list(set(variants))

def sanitize_number(val):
    """Converte valores numéricos como paletes e pc para inteiros/floats ou None se vazios."""
    if val is None or val == "" or val == "-":
        return None
    try:
        return int(float(str(val).replace(",", ".")))
    except Exception:
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/coletas", methods=["GET"])
def get_coletas():
    data_filtro = request.args.get("data")
    try:
        # Busca todas as coletas ou filtra pelas variações de data
        response = supabase.table("deliveries").select("*").execute()
        all_data = response.data or []

        if data_filtro:
            variants = set(format_date_variants(data_filtro))
            filtered = []
            for item in all_data:
                item_date = str(item.get("data", "")).strip()
                if item_date in variants:
                    filtered.append(item)
            return jsonify({"status": "success", "data": filtered})
        
        return jsonify({"status": "success", "data": all_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/coletas", methods=["POST"])
def save_coletas():
    payload = request.json or {}
    coletas = payload.get("coletas", [])
    data_operacao = payload.get("data")

    try:
        saved_items = []
        for item in coletas:
            # Sanitiza os campos para evitar erros de tipo no Postgres/Supabase
            registro = {
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
                "observacao": str(item.get("observacao") or item.get("motivo") or ""),
                "observacoes": str(item.get("observacao") or item.get("motivo") or ""), # Compatibilidade
                "cpf": str(item.get("cpf") or ""),
                "cavalo": str(item.get("cavalo") or ""),
                "carreta": str(item.get("carreta") or "")
            }

            # Tenta atualizar por ID se existir, ou por delivery, ou insere novo
            record_id = item.get("id")
            delivery = item.get("delivery")

            if record_id:
                res = supabase.table("deliveries").update(registro).eq("id", record_id).execute()
            elif delivery:
                # Verifica se a delivery já existe no banco
                existing = supabase.table("deliveries").select("id").eq("delivery", delivery).execute()
                if existing.data and len(existing.data) > 0:
                    ex_id = existing.data[0]["id"]
                    res = supabase.table("deliveries").update(registro).eq("id", ex_id).execute()
                else:
                    res = supabase.table("deliveries").insert(registro).execute()
            else:
                res = supabase.table("deliveries").insert(registro).execute()
            
            if res.data:
                saved_items.extend(res.data)

        return jsonify({"status": "success", "message": "Coletas salvas com sucesso no Supabase!", "saved": saved_items})
    except Exception as e:
        print(f"Erro ao salvar no Supabase: {e}")
        return jsonify({"status": "error", "message": f"Erro no Supabase: {str(e)}"}), 500

@app.route("/api/coletas/<id_coleta>", methods=["DELETE"])
def delete_coleta(id_coleta):
    try:
        supabase.table("deliveries").delete().eq("id", id_coleta).execute()
        return jsonify({"status": "success", "message": "Coleta excluída com sucesso."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/export-excel", methods=["GET"])
def export_excel():
    data_filtro = request.args.get("data")
    try:
        res = supabase.table("deliveries").select("*").execute()
        all_data = res.data or []

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
                    "MOTIVO": d.get("observacao") or d.get("observacoes") or "",
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
