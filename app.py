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

DRIVER_DATABASE = {
    "wilson_reis": {"name": "WILSON REIS", "cpf": "806.984.765-49", "cavalo": "JJF1856", "carreta": "NVQ8447"},
    "gabriel_borges": {"name": "GABRIEL BORGES", "cpf": "809.066.155-87", "cavalo": "KJY3204", "carreta": "KGG1152"},
    "argemiro_borges": {"name": "ARGEMIRO BORGES", "cpf": "041.604.865-09", "cavalo": "PEG7666", "carreta": "DTD8506"},
    "valdemir_de_jesus": {"name": "VALDEMIR DE JESUS", "cpf": "044.327.095-37", "cavalo": "HWB9F22", "carreta": "-"},
    "jones_rosario": {"name": "JONES ROSARIO", "cpf": "533.594.654.00", "cavalo": "JHX3C33", "carreta": "KKT9007"},
    "luis_carlos": {"name": "LUIS CARLOS", "cpf": "934.560.345-04", "cavalo": "KLB5018", "carreta": "NKZ6545"},
    "fabio_souza": {"name": "FABIO SOUZA", "cpf": "007.714.335-30", "cavalo": "PEJ4695", "carreta": "NLB7814"},
    "jean_robson": {"name": "JEAN ROBSON", "cpf": "032.795.865-00", "cavalo": "HWB9F22", "carreta": "-"},
    "ariel_nascimento": {"name": "ARIEL NASCIMENTO", "cpf": "050.153.565-95", "cavalo": "JVL8A44", "carreta": "-"},
    "leandro_de_andrade": {"name": "LEANDRO DE ANDRADE", "cpf": "017.793.835.84", "cavalo": "NZP7012", "carreta": "-"}
}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/coletas", methods=["GET"])
def get_coletas():
    data_filtro = request.args.get("data")
    try:
        query = supabase.table("deliveries").select("*")
        if data_filtro:
            query = query.eq("data", data_filtro)
        response = query.execute()
        return jsonify({"status": "success", "data": response.data or []})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/coletas", methods=["POST"])
def save_coletas():
    payload = request.json or {}
    coletas = payload.get("coletas", [])
    data_operacao = payload.get("data")

    try:
        for item in coletas:
            registro = {
                "data": data_operacao or item.get("data"),
                "motorista": item.get("motorista"),
                "delivery": item.get("delivery"),
                "cliente": item.get("cliente"),
                "paletes": item.get("paletes"),
                "pc": item.get("pc"),
                "valor": item.get("valor"),
                "l_horario": item.get("l_horario"),
                "c_horario": item.get("c_horario"),
                "f_horario": item.get("f_horario"),
                "sr": item.get("sr"),
                "observacao": item.get("observacao"),
                "cpf": item.get("cpf"),
                "cavalo": item.get("cavalo"),
                "carreta": item.get("carreta")
            }
            if item.get("id"):
                supabase.table("deliveries").update(registro).eq("id", item["id"]).execute()
            else:
                supabase.table("deliveries").insert(registro).execute()

        return jsonify({"status": "success", "message": "Coletas salvas com sucesso no Supabase!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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
        query = supabase.table("deliveries").select("*")
        if data_filtro:
            query = query.eq("data", data_filtro)
        res = query.execute()
        data = res.data or []

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
                    "MOTIVO": d.get("observacao", ""),
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
