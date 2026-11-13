import os
import json
import time
from flask import Flask, render_template, request, jsonify, send_file
import requests
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta

app = Flask(__name__, static_folder="static", template_folder="templates")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zkqzejnflpzknuuirlav.supabase.co")
SUPABASE_KEY = process_key = os.environ.get("SUPABASE_KEY", "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS")

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
        n = int(float(str(val).replace(",", ".")))
        return max(0, n)
    except Exception:
        return None

def parse_valor_numeric(val):
    if val is None or val == "" or val == "-" or str(val).strip() == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        clean = str(val).replace("R$", "").replace(" ", "").replace("\xa0", "").strip()
        if not clean:
            return None
        if "," in clean:
            clean = clean.replace(".", "").replace(",", ".")
        return float(clean)
    except Exception:
        return None

def compute_operational_status(item):
    pc_val = sanitize_number(item.get("pc"))
    hl = item.get("l_horario")
    hc = item.get("c_horario")
    hf = item.get("f_horario")
    obs = str(item.get("observacao") or item.get("observacoes") or item.get("motivo") or "").lower()
    is_hf_valid = hf and str(hf).strip() not in ["", "-"]
    if "bloqueio" in obs:
        return "BLOQUEIO"
    elif "deslocamento" in obs:
        return "DESLOCAMENTO"
    elif pc_val is not None and pc_val > 0 and hl and hc and is_hf_valid:
        return "FINALIZADO"
    return "PENDENTE"

# Tabela oficial de upgrade Truck -> Carreta
# Camaçari 1007.33 -> 1249.70 | Feira 1468.13 -> 2189.60 | Lauro 992.17 -> 1229.73 | Salvador 1021.05 -> 1256.30 | Simões Filho 664.22 -> 899.64
FRETE_UPGRADE_MAP = {
    1007.33: 1249.70,
    1468.13: 2189.60,
    992.17:  1229.73,
    1021.05: 1256.30,
    664.22:  899.64
}

def compute_frete_upgrade(base_val, cliente_str=""):
    if not base_val:
        return None
    for k, v in FRETE_UPGRADE_MAP.items():
        if abs(base_val - k) < 0.15:
            return v
    cli = (cliente_str or "").lower()
    if "simoes" in cli or "simões" in cli:
        return 899.64
    if "feira" in cli:
        return 2189.60
    if "lauro" in cli:
        return 1229.73
    if "camaçari" in cli or "camacari" in cli:
        return 1249.70
    if "salvador" in cli or "paripe" in cli or "bonocô" in cli or "bonoco" in cli:
        return 1256.30
    return None

def extract_valor_final(item):
    if not item or not isinstance(item, dict):
        return None

    valor = parse_valor_numeric(item.get("valor") or item.get("valor_frete") or item.get("valor_total") or item.get("val_frete"))
    obs = str(item.get("observacao") or item.get("observacoes") or item.get("motivo") or "").lower()
    st = compute_operational_status(item)

    # 1. Se for Bloqueio: 0.0
    if st == "BLOQUEIO" or "bloqueio" in obs:
        return 0.0

    # 2. Se for Deslocamento: Metade (50%)
    if st == "DESLOCAMENTO" or "deslocamento" in obs:
        if valor is not None:
            return round(valor / 2.0, 2)
        return 0.0

    # Verifica se a coleta de fato ocorreu: Deve ter horário E paletes coletados (pc >= 0)
    pc_val = sanitize_number(item.get("pc"))
    ch = str(item.get("c_horario") or "").strip()
    fh = str(item.get("f_horario") or "").strip()
    has_horario = bool((ch and ch != "-") or (fh and fh != "-"))
    has_pc = pc_val is not None and pc_val >= 0

    if not (has_horario and has_pc):
        return None

    # Se a coleta ocorreu, verifica se há valor manual válido (não inflado)
    manual_val = None
    val = item.get("valor_final")
    if val is not None and str(val).strip() != "":
        try:
            m = round(float(val), 2)
            if valor and m > valor * 10:
                pass  # Ignora valor corrompido/inflado por bug antigo
            else:
                manual_val = m
        except Exception:
            pass
    if manual_val is None:
        obs_sis = item.get("observacoes_sistema")
        if obs_sis:
            try:
                parsed = json.loads(obs_sis) if isinstance(obs_sis, str) else obs_sis
                if isinstance(parsed, dict) and "valor_final" in parsed and parsed["valor_final"] is not None:
                    m = round(float(parsed["valor_final"]), 2)
                    if not (valor and m > valor * 10):
                        manual_val = m
            except Exception:
                pass

    if manual_val is not None:
        return manual_val

    # Se agendado até 272 e coletado > 272, aplica a regra de upgrade (nunca abaixa)
    paletes_val = sanitize_number(item.get("paletes"))
    if paletes_val is not None and paletes_val <= 272 and pc_val is not None and pc_val > 272:
        up = compute_frete_upgrade(valor, item.get("cliente"))
        if up and (valor is None or up >= valor):
            return up

    # 3. O resto: Fica o mesmo valor integral!
    if valor is not None:
        return round(valor, 2)
    return None

def parse_date_to_dt(date_str):
    if not date_str:
        return None
    d = str(date_str).strip()
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(d, fmt)
        except Exception:
            pass
    return None

def get_week_range(ref_date):
    monday = ref_date - timedelta(days=ref_date.weekday())
    saturday = monday + timedelta(days=5) # Segunda a Sabado
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    saturday = saturday.replace(hour=23, minute=59, second=59, microsecond=999999)
    return monday, saturday

_CACHED_REAL_COLS = None
KNOWN_DELIVERIES_COLS = {
    'id', 'data', 'motorista', 'delivery', 'cliente', 'unidade', 'paletes', 'valor_frete',
    'l_horario', 'c_horario', 'f_horario', 'cs_ok', 'c_ok', 'l_ok', 'f_ok', 'tipo',
    'status', 'cpf', 'cavalo', 'carreta', 'observacoes', 'inconsistencias', 'confianca',
    'criado_em', 'atualizado_em', 'cliente_bloqueado', 'motorista_bloqueado',
    'unidade_bloqueado', 'observacoes_sistema', 'sr', 'data_finalizacao', 'pc', 'status_chep'
}

def get_real_table_columns():
    global _CACHED_REAL_COLS
    if _CACHED_REAL_COLS:
        return _CACHED_REAL_COLS
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?select=*&limit=1"
        res = requests.get(url, headers=get_headers(), timeout=5)
        if res.status_code == 200 and res.json():
            _CACHED_REAL_COLS = set(res.json()[0].keys())
            return _CACHED_REAL_COLS
    except Exception as e:
        print(f"Erro ao consultar colunas reais: {e}")
    return KNOWN_DELIVERIES_COLS

def db_select_all():
    """Busca todos os registros do Supabase sem filtro de data (para pesquisa global)."""
    try:
        headers = get_headers()
        headers["Range"] = "0-9999"
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?select=*&order=id.desc"
        res = requests.get(url, headers=headers, timeout=12)
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
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"status": "success", "data": [], "total": 0})
        
    import re
    from datetime import datetime
    
    q_clean = q.strip()
    q_lower = q_clean.lower()
    
    date_pattern = r'(\d{2}/\d{2}(?:/\d{2,4})?)'
    dates = re.findall(date_pattern, q_lower)
    
    # Extrair linguagem natural como "dia 10 ao dia 20" ou "do dia 10 ao 20"
    if not dates:
        nat_pattern = r'(?:do\s+)?(?:dia\s+)?(\d{1,2})\s+(?:a|ao|ate|at[eé])\s+(?:o\s+)?(?:dia\s+)?(\d{1,2})'
        nat_match = re.search(nat_pattern, q_lower)
        if nat_match:
            d1, d2 = nat_match.groups()
            curr_month = datetime.now().month
            curr_year = datetime.now().year
            dates = [f"{int(d1):02d}/{curr_month:02d}/{curr_year}", f"{int(d2):02d}/{curr_month:02d}/{curr_year}"]
            q_clean = re.sub(nat_pattern, '', q_clean, flags=re.IGNORECASE).strip()
            
    # Extrair também buscas por um único dia "dia 10"
    if not dates:
        single_day_pattern = r'dia\s+(\d{1,2})\b'
        single_match = re.search(single_day_pattern, q_lower)
        if single_match:
            d1 = single_match.group(1)
            curr_month = datetime.now().month
            curr_year = datetime.now().year
            dates = [f"{int(d1):02d}/{curr_month:02d}/{curr_year}"]
            q_clean = re.sub(single_day_pattern, '', q_clean, flags=re.IGNORECASE).strip()
    
    target_status = None
    if "deslocamento" in q_lower: target_status = "deslocamento"
    elif "bloqueio" in q_lower: target_status = "bloqueio"
    elif "finalizado" in q_lower: target_status = "finalizado"
    elif "pendente" in q_lower: target_status = "pendente"

    is_sr_search = (q_lower in ["sr", "s.r.", "s/r", "so sr", "só sr", "com sr", "pendencia sr", "pendencias sr"]) or (
        "sr" in q_lower.split() and not any(len(w) >= 6 and w.isdigit() for w in q_lower.split())
    )

    try:
        results = []

        if is_sr_search:
            all_data = db_select_all()
            for item in all_data:
                sr_val = str(item.get("sr") or "").strip()
                if not sr_val or sr_val in ["-", "0"]:
                    continue

                # 1. Ignorar se nao contiver numeros ou for palavra como atraso/bloqueio/deslocamento
                if not any(c.isdigit() for c in sr_val):
                    continue
                if sr_val.lower() in ["atraso", "bloqueio", "deslocamento", "cancelado", "sem", "nao"]:
                    continue

                # 2. Ignorar se o status operacional for DESLOCAMENTO ou BLOQUEIO
                op_status = compute_operational_status(item)
                db_status = str(item.get("status") or "").strip().upper()
                if op_status in ["DESLOCAMENTO", "BLOQUEIO"] or db_status in ["DESLOCAMENTO", "BLOQUEIO"]:
                    continue

                if dates:
                    def parse_custom_date(ds):
                        parts = ds.split('/')
                        if len(parts) == 2:
                            ds = f"{ds}/{datetime.now().year}"
                        for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
                            try:
                                return datetime.strptime(ds, fmt)
                            except:
                                pass
                        return datetime.min

                    start_date = parse_custom_date(dates[0])
                    end_date = parse_custom_date(dates[-1]) if len(dates) >= 2 else start_date
                    if start_date > end_date:
                        start_date, end_date = end_date, start_date

                    item_dt = parse_date_to_dt(item.get("data") or item.get("df") or item.get("data_finalizacao"))
                    if not item_dt or item_dt < start_date or item_dt > end_date:
                        continue

                extra_terms = [t for t in q_clean.lower().split() if t not in ["sr", "s.r.", "s/r", "so", "só", "com", "de", "do", "da"]]
                if extra_terms:
                    text_all = " ".join([str(v) for v in item.values() if v is not None]).lower()
                    if not all(t in text_all for t in extra_terms):
                        continue

                item["valor_final"] = extract_valor_final(item)
                item["status"] = compute_operational_status(item)
                results.append(item)

            def sort_key_sr(x):
                dt = parse_date_to_dt(x.get("data") or x.get("df") or x.get("data_finalizacao"))
                return (dt if dt else datetime.min, int(x.get("id") or 0))

            results.sort(key=sort_key_sr, reverse=True)
            return jsonify({"status": "success", "data": results, "total": len(results), "is_sr_search": True})

        # Se for busca direta por texto (cliente, motorista, delivery, etc.)
        if not target_status and len(dates) == 0:
            terms = [t.strip() for t in q_clean.split() if len(t.strip()) > 0]
            searchTerm = q_clean.replace(" ", "%")
            url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?or=(cliente.ilike.*{searchTerm}*,motorista.ilike.*{searchTerm}*,delivery.ilike.*{searchTerm}*,sr.ilike.*{searchTerm}*,cavalo.ilike.*{searchTerm}*,carreta.ilike.*{searchTerm}*,observacoes.ilike.*{searchTerm}*,data.ilike.*{searchTerm}*)&order=id.desc&limit=150"
            res = requests.get(url, headers=get_headers(), timeout=8)
            if res.status_code in [200, 206]:
                results = res.json()
            else:
                results = []
                
            if not results and len(terms) > 1:
                firstTerm = terms[0]
                url_fb = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?or=(cliente.ilike.*{firstTerm}*,motorista.ilike.*{firstTerm}*,delivery.ilike.*{firstTerm}*)&order=id.desc&limit=150"
                res_fb = requests.get(url_fb, headers=get_headers(), timeout=8)
                if res_fb.status_code in [200, 206]:
                    all_fb = res_fb.json()
                    results = [
                        item for item in all_fb
                        if all(t.lower() in " ".join([str(v) for v in item.values() if v is not None]).lower() for t in terms)
                    ]
        else:
            all_data = db_select_all()
            
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
            elif len(dates) == 1:
                start_date = parse_custom_date(dates[0])
                end_date = start_date

            search_terms = q_clean.lower().split()

            for item in all_data:
                item_date = parse_date_for_sort(item.get("data", ""))
                idt = item_date
                    
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

                if target_status and start_date and end_date:
                    if start_date <= idt <= end_date and st == target_status:
                        results.append(item)
                elif start_date and end_date:
                    if start_date <= idt <= end_date:
                        row_str = " ".join([str(v) for v in item.values() if v is not None]).lower()
                        if not search_terms or all(t in row_str for t in search_terms):
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
                    
        for r in results:
            r["valor_final"] = extract_valor_final(r)
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

@app.route("/api/move_delivery", methods=["POST"])
def move_delivery():
    payload = request.json or {}
    deliv_id = payload.get("id")
    new_date = str(payload.get("new_date", "")).strip()

    if not deliv_id or not new_date:
        return jsonify({"status": "error", "message": "ID e nova data sao obrigatorios"}), 400

    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=eq.{deliv_id}"
        patch_data = {
            "data": new_date,
            "atualizado_em": datetime.utcnow().isoformat()
        }
        res = requests.patch(url, headers=get_headers(), json=patch_data, timeout=8)
        if res.status_code not in [200, 204]:
            print(f"Erro no patch Supabase ao mover coleta: {res.status_code} {res.text}")
            return jsonify({"status": "error", "message": f"Erro Supabase: {res.status_code}"}), 500

        res_get = requests.get(url + "&select=*", headers=get_headers(), timeout=5)
        updated_record = res_get.json()[0] if (res_get.status_code in [200, 206] and res_get.json()) else patch_data

        try:
            create_coletas_snapshot("move")
        except Exception:
            pass

        return jsonify({
            "status": "success",
            "message": f"Coleta transferida para {new_date} com sucesso",
            "coleta": updated_record
        })
    except Exception as e:
        print(f"Erro em move_delivery: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==============================================================================
# SISTEMA DE SNAPSHOTS, BACKUPS ROTATIVOS EM EXCEL/JSON E RESTAURAÇÃO
# ==============================================================================
BACKUP_DIR = os.path.join(BASE_DIR, "backups_coletas")
try:
    os.makedirs(BACKUP_DIR, exist_ok=True)
except Exception:
    pass

_last_snapshot_time = 0

def create_coletas_snapshot(trigger="auto"):
    global _last_snapshot_time
    now = time.time()
    # Throttling de snapshot automático a cada 60s
    if trigger == "auto" and (now - _last_snapshot_time < 60):
        return None
    _last_snapshot_time = now

    try:
        all_data = db_select_all()
        if not all_data:
            return None

        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        json_file = os.path.join(BACKUP_DIR, f"snapshot_{timestamp_str}.json")
        xlsx_file = os.path.join(BACKUP_DIR, f"snapshot_{timestamp_str}.xlsx")

        # 1. Salva JSON completo com todos os campos
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": timestamp_str,
                "data_formatada": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "total": len(all_data),
                "coletas": all_data
            }, f, ensure_ascii=False, indent=2)

        # 2. Salva Planilha Excel organizada
        try:
            df_rows = []
            for item in all_data:
                df_rows.append({
                    "ID": item.get("id"),
                    "Data": item.get("data"),
                    "Delivery": item.get("delivery"),
                    "Cliente": item.get("cliente"),
                    "Motorista": item.get("motorista"),
                    "Paletes Agendados": item.get("paletes"),
                    "Paletes Coletados (PC)": item.get("pc"),
                    "Valor Frete": item.get("valor_frete"),
                    "Valor Final": item.get("valor_final"),
                    "H_Local": item.get("l_horario"),
                    "H_Coletado": item.get("c_horario"),
                    "H_Finalizado": item.get("f_horario"),
                    "DF": item.get("data_finalizacao") or item.get("df"),
                    "SR": item.get("sr"),
                    "Observações/Motivo": item.get("observacoes") or item.get("motivo"),
                    "Cavalo": item.get("cavalo"),
                    "Carreta": item.get("carreta"),
                    "Status": item.get("status")
                })
            df = pd.DataFrame(df_rows)
            with pd.ExcelWriter(xlsx_file, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Coletas")
                ws = writer.sheets["Coletas"]
                for idx, col in enumerate(df.columns):
                    col_letter = chr(65 + idx) if idx < 26 else f"A{chr(65 + idx - 26)}"
                    ws.column_dimensions[col_letter].width = 20
        except Exception as e_xlsx:
            print("Aviso ao salvar Excel do snapshot:", e_xlsx)

        # 3. Limpeza automática (mantém os últimos 20 snapshots)
        try:
            json_files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("snapshot_") and f.endswith(".json")])
            if len(json_files) > 20:
                for old_f in json_files[:-20]:
                    try:
                        os.remove(os.path.join(BACKUP_DIR, old_f))
                        xlsx_old = os.path.join(BACKUP_DIR, old_f.replace(".json", ".xlsx"))
                        if os.path.exists(xlsx_old):
                            os.remove(xlsx_old)
                    except Exception:
                        pass
        except Exception:
            pass

        return timestamp_str
    except Exception as e:
        print("Erro ao gerar snapshot de coletas:", e)
        return None

@app.route("/api/backups", methods=["GET"])
def list_backups():
    try:
        snapshots = []
        if os.path.exists(BACKUP_DIR):
            files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("snapshot_") and f.endswith(".json")], reverse=True)
            for f in files[:15]:
                try:
                    p = os.path.join(BACKUP_DIR, f)
                    with open(p, "r", encoding="utf-8") as fp:
                        meta = json.load(fp)
                    xlsx_name = f.replace(".json", ".xlsx")
                    has_xlsx = os.path.exists(os.path.join(BACKUP_DIR, xlsx_name))
                    snapshots.append({
                        "file": f,
                        "xlsx_file": xlsx_name if has_xlsx else None,
                        "timestamp": meta.get("timestamp"),
                        "data_formatada": meta.get("data_formatada"),
                        "total": meta.get("total", 0)
                    })
                except Exception:
                    pass
        return jsonify({"status": "success", "backups": snapshots})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/backups/download/<filename>", methods=["GET"])
def download_backup(filename):
    try:
        safe_name = os.path.basename(filename)
        path = os.path.join(BACKUP_DIR, safe_name)
        if not os.path.exists(path):
            return jsonify({"status": "error", "message": "Arquivo de backup nao encontrado"}), 404
        return send_file(path, as_attachment=True)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/backups/criar", methods=["POST"])
def manual_backup():
    try:
        ts = create_coletas_snapshot(trigger="manual")
        return jsonify({"status": "success", "message": "Backup manual gerado com sucesso!", "timestamp": ts})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/backups/restaurar", methods=["POST"])
def restore_backup():
    try:
        payload = request.get_json(force=True) or {}
        filename = payload.get("file")
        if not filename:
            files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("snapshot_") and f.endswith(".json")], reverse=True)
            if not files:
                return jsonify({"status": "error", "message": "Nenhum snapshot de backup disponivel para restaurar"}), 400
            filename = files[0]

        safe_name = os.path.basename(filename)
        path = os.path.join(BACKUP_DIR, safe_name)
        if not os.path.exists(path):
            return jsonify({"status": "error", "message": f"Arquivo {safe_name} nao encontrado"}), 404

        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)

        coletas_backup = data.get("coletas", [])
        if not coletas_backup:
            return jsonify({"status": "error", "message": "Snapshot vazio"}), 400

        restauradas = 0
        real_cols = get_real_deliveries_columns()
        for c in coletas_backup:
            cid = c.get("id")
            if not cid:
                continue

            raw_update = {
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
                "cpf": c.get("cpf"),
                "cavalo": c.get("cavalo"),
                "carreta": c.get("carreta"),
                "status": c.get("status")
            }
            if real_cols:
                final_upd = {k: v for k, v in raw_update.items() if k in real_cols and k != "id"}
            else:
                final_upd = raw_update

            final_upd["atualizado_em"] = datetime.utcnow().isoformat()
            url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=eq.{cid}"
            res = requests.patch(url, headers=get_headers(), json=final_upd, timeout=8)
            if res.status_code in [200, 204]:
                restauradas += 1

        return jsonify({
            "status": "success",
            "message": f"Backup restaurado com sucesso! {restauradas} coletas recuperadas exatamente para o estado do snapshot de {data.get('data_formatada')}.",
            "total_restauradas": restauradas
        })
    except Exception as e:
        print(f"Erro em /api/backups/restaurar: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/coletas", methods=["GET"])
def get_coletas():
    data_filtro = request.args.get("data")
    try:
        if data_filtro:
            raw_dates = [d.strip() for d in data_filtro.split(",") if d.strip()]
            all_variants = []
            for rd in raw_dates:
                all_variants.extend(format_date_variants(rd))
            variants = list(dict.fromkeys(all_variants))
            try:
                # Busca direta ultra-rápida no Supabase indexada por data (suporta 1 data ou lote de datas)
                quoted_variants = ",".join([f'"{v}"' for v in variants])
                headers = get_headers()
                headers["Range"] = "0-999"
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?data=in.({quoted_variants})&order=id.asc"
                res = requests.get(url, headers=headers, timeout=8)
                if res.status_code in [200, 206]:
                    items = res.json()
                    for item in items:
                        item["valor_final"] = extract_valor_final(item)
                    return jsonify({"status": "success", "data": items})
            except Exception as e_direct:
                print(f"Fallback para db_select_all: {e_direct}")

            all_data = db_select_all()
            var_set = set(variants)
            filtered = [item for item in all_data if str(item.get("data", "")).strip() in var_set]
            for item in filtered:
                item["valor_final"] = extract_valor_final(item)
            return jsonify({"status": "success", "data": filtered})

        all_data = db_select_all()
        for item in all_data:
            item["valor_final"] = extract_valor_final(item)
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

        # Busca cirúrgica ultra-rápida apenas das coletas envolvidas no salvamento (elimina o peso de baixar o banco todo)
        ids_to_check = [str(item.get("id")) for item in coletas if item.get("id") and str(item.get("id")).isdigit()]
        existing_items = {}
        if ids_to_check:
            try:
                quoted_ids = ",".join(ids_to_check)
                headers = get_headers()
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?id=in.({quoted_ids})"
                res = requests.get(url, headers=headers, timeout=8)
                if res.status_code in [200, 206]:
                    for r in res.json():
                        existing_items[str(r.get("id"))] = r
            except Exception as e_ids:
                print(f"Fallback busca cirúrgica de IDs: {e_ids}")
                if data_operacao:
                    try:
                        headers = get_headers()
                        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/deliveries?data=eq.{data_operacao}"
                        res = requests.get(url, headers=headers, timeout=8)
                        if res.status_code in [200, 206]:
                            for r in res.json():
                                existing_items[str(r.get("id"))] = r
                    except Exception:
                        pass
        
        saved_items = []
        for item in coletas:
            deliv_raw = str(item.get("delivery") or "").strip()
            cliente_raw = str(item.get("cliente") or "").strip()
            driver_raw = str(item.get("motorista") or "").strip()
            if driver_raw in ["-", "-- SELECIONE --", "-- SELECIONE MOTORISTA --"]:
                driver_raw = ""
            obs_value = str(item.get("observacao") or item.get("motivo") or item.get("observacoes") or "").strip()
            valor_raw = item.get("valor") or item.get("valor_frete") or item.get("valor_total") or item.get("val_frete")
            valor_num = parse_valor_numeric(valor_raw)
            valor_final_raw = item.get("valor_final") or item.get("val_final")
            valor_final_num = parse_valor_numeric(valor_final_raw)
            paletes_num = sanitize_number(item.get("paletes"))
            pc_num = sanitize_number(item.get("pc"))
            l_h = str(item.get("l_horario") or "").strip()
            c_h = str(item.get("c_horario") or "").strip()
            f_horario_val = str(item.get("f_horario") or "").strip()

            # Regra de exibição e gravação: Se não for Bloqueio nem Deslocamento,
            # V. FINAL só deve ser gravado se houver Horário E Paletes Coletados
            is_bloqueio = ("bloqueio" in obs_value.lower())
            is_deslocamento = ("deslocamento" in obs_value.lower())
            has_h = bool((c_h and c_h != "-") or (f_horario_val and f_horario_val != "-"))
            has_p = (pc_num is not None and pc_num >= 0)

            if is_bloqueio:
                valor_final_num = 0.0
            elif is_deslocamento:
                valor_final_num = round(valor_num / 2.0, 2) if valor_num else 0.0
            elif not (has_h and has_p):
                # Se o usuário digitou manualmente um valor_final, preserva!
                pass
            else:
                # Regra oficial: se agendado até 272 e coletado > 272, aplica a regra de upgrade (nunca abaixa)
                if paletes_num is not None and paletes_num <= 272 and pc_num is not None and pc_num > 272:
                    up = compute_frete_upgrade(valor_num, cliente_raw)
                    if up and (valor_final_num is None or valor_final_num == valor_num or valor_final_num < up):
                        valor_final_num = up
                if valor_final_num is not None and valor_num and valor_final_num > valor_num * 10:
                    valor_final_num = valor_num

            # Ignora inserção de linhas completamente vazias
            if not item.get("id"):
                if not deliv_raw and not cliente_raw and not driver_raw and not paletes_num and not pc_num and not valor_num and valor_final_num is None and not obs_value and not l_h and not c_h and not f_horario_val:
                    continue
            
            existing = existing_items.get(str(item.get("id", "")), {})
            item_date = existing.get("data") or item.get("data") or data_operacao

            # DF editável enviado do formulário ou auto-sugerido
            df_user_val = str(item.get("df") or item.get("data_finalizacao") or "").strip()
            if not df_user_val and f_horario_val and f_horario_val != "-":
                df_user_val = item_date or data_operacao

            raw_registro = {
                "data": item_date,
                "motorista": driver_raw or item.get("motorista") or "",
                "delivery": deliv_raw,
                "cliente": cliente_raw,
                "paletes": paletes_num,
                "pc": pc_num,
                "valor": valor_num,
                "valor_frete": valor_num,
                "valor_total": valor_num,
                "val_frete": valor_num,
                "valor_final": valor_final_num,
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

            if real_cols and "valor_final" not in real_cols:
                existing_obs_sis = existing.get("observacoes_sistema")
                obs_sis_dict = {}
                if existing_obs_sis:
                    try:
                        obs_sis_dict = json.loads(existing_obs_sis) if isinstance(existing_obs_sis, str) else dict(existing_obs_sis)
                    except Exception:
                        obs_sis_dict = {}
                if valor_final_num is not None:
                    obs_sis_dict["valor_final"] = valor_final_num
                    obs_sis_dict["manual_edit"] = True
                else:
                    obs_sis_dict.pop("valor_final", None)
                    obs_sis_dict.pop("manual_edit", None)
                raw_registro["observacoes_sistema"] = json.dumps(obs_sis_dict) if obs_sis_dict else None

            if real_cols:
                registro = {k: v for k, v in raw_registro.items() if k in real_cols and k != "id"}
            else:
                registro = raw_registro

            registro_final = {}
            for k, v in registro.items():
                is_empty = (v is None or str(v).strip() in ["", "-", "00:00"])
                if is_empty:
                    registro_final[k] = None
                else:
                    registro_final[k] = v

            rec_id = item.get("id")
            is_valid_id = rec_id is not None and str(rec_id).isdigit() and int(rec_id) > 0

            if is_valid_id:
                # TRAVA DE FERRO: Coletas existentes NUNCA têm a data alterada na tela comum
                # A data é estritamente imutável na rota normal (apenas /api/move_delivery pode alterar)
                registro_final.pop("data", None)

                old_m = str(existing.get("motorista") or "").strip().upper()
                new_m = str(registro_final.get("motorista") or "").strip().upper()
                old_cav = str(existing.get("cavalo") or "").strip().upper()
                new_cav = str(registro_final.get("cavalo") or "").strip().upper()
                old_car = str(existing.get("carreta") or "").strip().upper()
                new_car = str(registro_final.get("carreta") or "").strip().upper()

                # Se motorista ou placas foram alterados ou atribuidos, reseta status_chep para reenvio
                if (new_m and new_m != old_m) or (new_cav and new_cav != old_cav) or (new_car and new_car != old_car):
                    registro_final["status_chep"] = None

                res = db_update_by_id(int(rec_id), registro_final)
            else:
                res = db_insert_new(registro_final)

            saved_items.extend(res if isinstance(res, list) else [res])

        try:
            create_coletas_snapshot("auto")
        except Exception:
            pass

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
    start_date_str = request.args.get("start_date") or request.args.get("data_inicio")
    end_date_str = request.args.get("end_date") or request.args.get("data_fim")
    month_str = request.args.get("month")
    year_str = request.args.get("year")
    week_str = request.args.get("week") or request.args.get("semana")
    motorista_filtro = (request.args.get("motorista") or "").strip().upper()
    all_str = request.args.get("all")

    try:
        all_data = db_select_all()
        for d in all_data:
            d["valor_final"] = extract_valor_final(d)
            d["status_operacional"] = compute_operational_status(d)

        data = all_data
        sheet_name = "Coletas"
        filename = "Relatorio_Coletas.xlsx"
        now = datetime.now()

        if all_str:
            data = all_data
            filename = "Relatorio_Projeto_Todo.xlsx"
            sheet_name = "Projeto Todo"
        elif week_str:
            ref_dt = now
            if week_str not in ["current", "esta_semana", "atual", "true"]:
                dt_cand = parse_date_to_dt(week_str)
                if dt_cand:
                    ref_dt = dt_cand
            elif data_filtro:
                dt_cand = parse_date_to_dt(data_filtro)
                if dt_cand:
                    ref_dt = dt_cand
            mon, sat = get_week_range(ref_dt)
            data = [d for d in all_data if mon <= parse_date_for_sort(d.get("data", "")) <= sat]
            mon_s = mon.strftime("%d_%m")
            sat_s = sat.strftime("%d_%m_%Y")
            filename = f"Relatorio_Semanal_{mon_s}_a_{sat_s}.xlsx"
            sheet_name = f"Semana {mon_s} a {sat_s}"[:31]
        elif start_date_str and end_date_str:
            dt_start = parse_date_to_dt(start_date_str)
            dt_end = parse_date_to_dt(end_date_str)
            if dt_start and dt_end:
                if dt_start > dt_end:
                    dt_start, dt_end = dt_end, dt_start
                dt_end = dt_end.replace(hour=23, minute=59, second=59)
                data = [d for d in all_data if dt_start <= parse_date_for_sort(d.get("data", "")) <= dt_end]
                d1_s = dt_start.strftime("%d_%m")
                d2_s = dt_end.strftime("%d_%m_%Y")
                filename = f"Relatorio_{d1_s}_a_{d2_s}.xlsx"
                sheet_name = f"{d1_s} a {d2_s}"[:31]
        elif month_str and year_str:
            suffix = f"/{month_str.zfill(2)}/{year_str}"
            data = [d for d in all_data if str(d.get("data", "")).strip().endswith(suffix)]
            filename = f"Relatorio_Mes_{month_str}_{year_str}.xlsx"
            sheet_name = f"Mes {month_str}-{year_str}"[:31]
        elif data_filtro:
            variants = set(format_date_variants(data_filtro))
            data = [d for d in all_data if str(d.get("data", "")).strip() in variants]
            filename = f"Relatorio_{data_filtro.replace('/', '_')}.xlsx"
            sheet_name = f"Dia {data_filtro.replace('/', '-')}"[:31]

        if motorista_filtro and motorista_filtro not in ["TODOS", "TODOS OS MOTORISTAS", "-- SELECIONE --", "-- SELECIONE MOTORISTA --"]:
            data = [d for d in data if motorista_filtro in str(d.get("motorista") or "").upper()]
            clean_drv = motorista_filtro.replace(" ", "_")
            filename = f"Relatorio_{clean_drv}_{filename.replace('Relatorio_', '')}"

        data.sort(key=lambda x: parse_date_for_sort(x.get("data", "")), reverse=False)

        if not data:
            df = pd.DataFrame(columns=[
                "DATA", "MOTORISTA", "DELIVERY", "CLIENTES", "PALETES", "PALETES COLETADO",
                "VALOR", "VALOR FINAL", "H_LOCAL", "H_COLETADO", "H_FINALIZADO", "DATA FINALIZACAO (DF)", "STATUS", "SR", "MOTIVO", "CPF", "CAVALO", "CARRETA"
            ])
        else:
            rows = []
            for d in data:
                val_raw = d.get("valor") or d.get("valor_frete") or d.get("valor_total") or d.get("val_frete")
                if isinstance(val_raw, (int, float)):
                    val_display = f"R$ {val_raw:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
                else:
                    val_display = str(val_raw or "")

                vf_raw = d.get("valor_final")
                if isinstance(vf_raw, (int, float)):
                    vf_display = f"R$ {vf_raw:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
                else:
                    vf_display = str(vf_raw or "")
                
                df_display = d.get("df") or d.get("data_finalizacao") or ""
                rows.append({
                    "DATA": d.get("data", ""),
                    "MOTORISTA": d.get("motorista", ""),
                    "DELIVERY": d.get("delivery", ""),
                    "CLIENTES": d.get("cliente", ""),
                    "PALETES": d.get("paletes", ""),
                    "PALETES COLETADO": d.get("pc", ""),
                    "VALOR": val_display,
                    "VALOR FINAL": vf_display,
                    "H_LOCAL": d.get("l_horario", ""),
                    "H_COLETADO": d.get("c_horario", ""),
                    "H_FINALIZADO": d.get("f_horario", ""),
                    "DATA FINALIZACAO (DF)": df_display,
                    "STATUS": d.get("status_operacional", ""),
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
                col_letter = chr(65 + idx) if idx < 26 else f"A{chr(65 + idx - 26)}"
                worksheet.column_dimensions[col_letter].width = 20
                
        output.seek(0)
        return send_file(output, download_name=filename, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/relatorios", methods=["GET"])
def api_relatorios():
    period = request.args.get("period", "this_week").strip().lower()
    start_date_str = request.args.get("start_date", "").strip()
    end_date_str = request.args.get("end_date", "").strip()
    motorista_filtro = request.args.get("motorista", "").strip().upper()

    try:
        all_data = db_select_all()
        for d in all_data:
            d["valor_final"] = extract_valor_final(d)
            d["status_operacional"] = compute_operational_status(d)

        now = datetime.now()
        dt_start = None
        dt_end = None

        if period == "today":
            dt_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            dt_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif period in ["this_week", "week", "semana_atual"]:
            dt_start, dt_end = get_week_range(now)
        elif period in ["last_week", "semana_passada"]:
            dt_start, dt_end = get_week_range(now - timedelta(days=7))
        elif period in ["this_month", "month", "mes_atual"]:
            dt_start = datetime(now.year, now.month, 1)
            next_m = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
            dt_end = next_m - timedelta(microseconds=1)
        elif period in ["last_month", "mes_passado"]:
            last_m_dt = (datetime(now.year, now.month, 1) - timedelta(days=1))
            dt_start = datetime(last_m_dt.year, last_m_dt.month, 1)
            dt_end = datetime(now.year, now.month, 1) - timedelta(microseconds=1)
        elif period == "custom" and start_date_str and end_date_str:
            dt_start = parse_date_to_dt(start_date_str)
            dt_end = parse_date_to_dt(end_date_str)
            if dt_start and dt_end:
                if dt_start > dt_end:
                    dt_start, dt_end = dt_end, dt_start
                dt_end = dt_end.replace(hour=23, minute=59, second=59)
        elif period == "all":
            dt_start = datetime.min
            dt_end = datetime.max

        today_date = now.date()

        filtered_realizadas = []
        filtered_futuras = []

        for item in all_data:
            idt = parse_date_for_sort(item.get("data", ""))
            if dt_start and dt_end:
                if not (dt_start <= idt <= dt_end):
                    continue
            if motorista_filtro and motorista_filtro not in ["TODOS", "TODOS OS MOTORISTAS"]:
                if motorista_filtro not in str(item.get("motorista") or "").upper():
                    continue

            # Classifica se é coleta futura que ainda não iniciou
            item_dt = parse_date_to_dt(item.get("data"))
            item_d = item_dt.date() if item_dt else None
            is_future = bool(item_d and item_d > today_date)
            st = item.get("status_operacional")
            pc = sanitize_number(item.get("pc")) or 0
            c_h = str(item.get("c_horario") or "").strip()
            has_started = (st in ["FINALIZADO", "BLOQUEIO", "DESLOCAMENTO"]) or (pc > 0) or (c_h and c_h not in ["", "-", "00:00"])

            if is_future and not has_started:
                item["is_futura"] = True
                filtered_futuras.append(item)
            else:
                item["is_futura"] = False
                filtered_realizadas.append(item)

        # As métricas de execução realizada consideram apenas as coletas até hoje (dias operados)
        total_coletas = len(filtered_realizadas)
        finalizadas = sum(1 for d in filtered_realizadas if d.get("status_operacional") == "FINALIZADO")
        bloqueios = sum(1 for d in filtered_realizadas if d.get("status_operacional") == "BLOQUEIO")
        deslocamentos = sum(1 for d in filtered_realizadas if d.get("status_operacional") == "DESLOCAMENTO")
        pendentes = total_coletas - (finalizadas + bloqueios + deslocamentos)

        paletes_agendados = sum(sanitize_number(d.get("paletes")) or 0 for d in filtered_realizadas)
        paletes_coletados = sum(sanitize_number(d.get("pc")) or 0 for d in filtered_realizadas)
        eficacia_pct = round((paletes_coletados / paletes_agendados * 100), 1) if paletes_agendados > 0 else 0.0

        valor_previsto = sum(parse_valor_numeric(d.get("valor") or d.get("valor_frete")) or 0 for d in filtered_realizadas)
        valor_final = sum(d.get("valor_final") or 0 for d in filtered_realizadas)
        saldo_frete = round(valor_final - valor_previsto, 2)

        # Métricas de Programação Futura (coletas agendadas de amanhã em diante)
        total_futuras = len(filtered_futuras)
        paletes_futuros = sum(sanitize_number(d.get("paletes")) or 0 for d in filtered_futuras)
        valor_futuro = sum(parse_valor_numeric(d.get("valor") or d.get("valor_frete")) or 0 for d in filtered_futuras)

        dias_unicos = set(d.get("data") for d in filtered_realizadas if d.get("data"))
        motoristas_unicos = set(str(d.get("motorista")).strip().upper() for d in filtered_realizadas if d.get("motorista") and str(d.get("motorista")).strip() not in ["-", "", "NONE", "NULL"])

        drivers_map = {}
        for d in filtered_realizadas:
            m_name = str(d.get("motorista") or "").strip().upper()
            if not m_name or m_name in ["-", "NONE", "NULL", "-- SELECIONE --", "-- SELECIONE MOTORISTA --"]:
                m_name = "SEM MOTORISTA"
            if m_name not in drivers_map:
                drivers_map[m_name] = {
                    "motorista": m_name,
                    "coletas": 0,
                    "finalizadas": 0,
                    "bloqueios": 0,
                    "deslocamentos": 0,
                    "pendentes": 0,
                    "paletes_agendados": 0,
                    "paletes_coletados": 0,
                    "valor_previsto": 0.0,
                    "valor_final": 0.0,
                    "dias": set(),
                    "placas": set()
                }
            grp = drivers_map[m_name]
            grp["coletas"] += 1
            st = d.get("status_operacional")
            if st == "FINALIZADO": grp["finalizadas"] += 1
            elif st == "BLOQUEIO": grp["bloqueios"] += 1
            elif st == "DESLOCAMENTO": grp["deslocamentos"] += 1
            else: grp["pendentes"] += 1

            p = sanitize_number(d.get("paletes")) or 0
            pc = sanitize_number(d.get("pc")) or 0
            grp["paletes_agendados"] += p
            grp["paletes_coletados"] += pc

            v = parse_valor_numeric(d.get("valor") or d.get("valor_frete")) or 0.0
            vf = d.get("valor_final") or 0.0
            grp["valor_previsto"] += v
            grp["valor_final"] += vf

            if d.get("data"): grp["dias"].add(d.get("data"))
            cav = str(d.get("cavalo") or "").strip()
            car = str(d.get("carreta") or "").strip()
            if cav and cav != "-":
                grp["placas"].add(f"{cav}/{car}" if car and car != "-" else cav)

        por_motorista = []
        for m_name, grp in drivers_map.items():
            tot_p = grp["paletes_agendados"]
            tot_pc = grp["paletes_coletados"]
            ef = round((tot_pc / tot_p * 100), 1) if tot_p > 0 else 0.0
            v_prev = round(grp["valor_previsto"], 2)
            v_fin = round(grp["valor_final"], 2)
            saldo = round(v_fin - v_prev, 2)
            por_motorista.append({
                "motorista": m_name,
                "coletas": grp["coletas"],
                "finalizadas": grp["finalizadas"],
                "bloqueios": grp["bloqueios"],
                "deslocamentos": grp["deslocamentos"],
                "pendentes": grp["pendentes"],
                "paletes_agendados": tot_p,
                "paletes_coletados": tot_pc,
                "eficacia_pct": ef,
                "valor_previsto": v_prev,
                "valor_final": v_fin,
                "saldo_frete": saldo,
                "dias_operados": len(grp["dias"]),
                "veiculos": list(grp["placas"])
            })

        por_motorista.sort(key=lambda x: x["coletas"], reverse=True)
        all_filtered = filtered_realizadas + filtered_futuras
        all_filtered.sort(key=lambda x: parse_date_for_sort(x.get("data", "")), reverse=True)

        return jsonify({
            "status": "success",
            "period": period,
            "start_date": dt_start.strftime("%d/%m/%Y") if dt_start and dt_start != datetime.min else "",
            "end_date": dt_end.strftime("%d/%m/%Y") if dt_end and dt_end != datetime.max else "",
            "kpis": {
                "total_coletas": total_coletas,
                "finalizadas": finalizadas,
                "bloqueios": bloqueios,
                "deslocamentos": deslocamentos,
                "pendentes": pendentes,
                "paletes_agendados": paletes_agendados,
                "paletes_coletados": paletes_coletados,
                "eficacia_pct": eficacia_pct,
                "valor_previsto": round(valor_previsto, 2),
                "valor_final": round(valor_final, 2),
                "saldo_frete": saldo_frete,
                "total_futuras": total_futuras,
                "paletes_futuros": paletes_futuros,
                "valor_futuro": round(valor_futuro, 2),
                "dias_operados": len(dias_unicos),
                "total_motoristas": len(motoristas_unicos)
            },
            "por_motorista": por_motorista,
            "total_registros": len(all_filtered),
            "coletas": all_filtered[:200]
        })
    except Exception as e:
        print(f"Erro em api_relatorios: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/whatsapp")
def whatsapp_qr():
    import os as _os
    import time
    qr_path = os.path.join(app.static_folder, "qr.png")
    if os.path.exists(qr_path):
        ts = int(time.time())
        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Conectar WhatsApp</title>
    <meta http-equiv="refresh" content="6">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 85vh; background: #0f172a; color: white; margin: 0; }}
        .box {{ background: #1e293b; padding: 2.5rem; border-radius: 16px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); max-width: 400px; }}
        img {{ border-radius: 12px; background: white; padding: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
        .pulse {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #22c55e; margin-right: 6px; animation: blink 1.5s infinite; }}
        @keyframes blink {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}
    </style>
</head>
<body>
    <div class="box">
        <h2 style="color:#22c55e; margin-top:0;">📱 Conectar WhatsApp</h2>
        <p style="font-size:0.95rem; color:#cbd5e1; line-height: 1.5;">Abra o WhatsApp no celular:<br><b>Menu > Aparelhos conectados > Conectar aparelho</b></p>
        <img id="qrImg" src="/static/qr.png?t={ts}" style="width:260px; height:260px;"/>
        <p style="font-size:0.85rem; color:#94a3b8; margin-top: 15px;"><span class="pulse"></span>Atualizando em tempo real...</p>
    </div>
    <script>
        setInterval(function() {{
            var img = document.getElementById('qrImg');
            if (img) img.src = '/static/qr.png?t=' + Date.now();
        }}, 2000);
    </script>
</body>
</html>'''
    return '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>WhatsApp Conectado</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body {{ font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 85vh; background: #0f172a; color: white; }}
        .box {{ background: #1e293b; padding: 2.5rem; border-radius: 16px; text-align: center; }}
    </style>
</head>
<body>
    <div class="box">
        <h2 style="color:#22c55e;">✅ WhatsApp Conectado com Sucesso!</h2>
        <p style="color:#cbd5e1;">O robô já está ativo e monitorando mensagens em tempo real.</p>
    </div>
</body>
</html>'''


_chep_process = None

@app.route("/api/chep/disparar", methods=["POST", "GET"])
def disparar_chep():
    global _chep_process
    import subprocess
    if _chep_process is not None and _chep_process.poll() is None:
        return jsonify({
            "status": "running",
            "message": "O Robô CHEP já está em execução no momento. Aguarde a finalização."
        }), 200

    try:
        chep_script = os.path.join(BASE_DIR, "whatsapp-bot", "chep.js")
        if not os.path.exists(chep_script):
            return jsonify({"status": "error", "message": "Script chep.js não encontrado."}), 404
        
        log_file = open(os.path.join(BASE_DIR, "bot.log"), "a", encoding="utf-8")
        _chep_process = subprocess.Popen(["node", chep_script], cwd=os.path.join(BASE_DIR, "whatsapp-bot"), stdout=log_file, stderr=subprocess.STDOUT)
        return jsonify({
            "status": "success",
            "message": "Robô CHEP iniciado na nuvem com sucesso! Ele preencherá as coletas no portal da CHEP em segundo plano."
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao disparar robô CHEP: {str(e)}"}), 500

@app.route("/api/chep/status", methods=["GET"])
def status_chep():
    global _chep_process
    if _chep_process is not None and _chep_process.poll() is None:
        return jsonify({"status": "running", "running": True, "message": "Robô CHEP executando..."})
    return jsonify({"status": "idle", "running": False, "message": "Robô CHEP em Standby."})

@app.route("/logs")
def view_logs():
    log_out = ""
    # 1. Tenta ler o arquivo bot.log (Docker no Render ou Windows local)
    possible_log_paths = [
        os.path.join(BASE_DIR, "bot.log"),
        "/app/bot.log",
        os.path.join(BASE_DIR, "whatsapp-bot", "bot.log")
    ]
    for p in possible_log_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    log_out = "".join(lines[-150:])
                if log_out.strip():
                    break
            except Exception as e:
                log_out = f"Erro ao ler {p}: {e}"

    # 2. Se não achou arquivo de log, tenta PM2 como fallback
    if not log_out.strip():
        import subprocess
        try:
            log_out = subprocess.check_output(["pm2", "logs", "RoboWPP", "--lines", "120", "--nostream", "--out"], text=True, stderr=subprocess.STDOUT, timeout=4)
        except Exception:
            pass

    if not log_out.strip():
        log_out = "Nenhum log registrado ainda. O robô está inicializando ou pronto para conexões."

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
            .btn-clean {{ display: inline-block; background: #238636; color: #fff; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-bottom: 15px; border: 1px solid rgba(240,246,252,0.1); }}
            .btn-clean:hover {{ background: #2ea043; }}
            pre {{ background: #161b22; padding: 15px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; font-size: 13px; line-height: 1.5; border: 1px solid #30363d; }}
        </style>
    </head>
    <body>
        <h2>📋 Logs do Robo (WhatsApp + CHEP)</h2>
        <p>Atualizando automaticamente a cada 5 segundos...</p>
        <a href="/api/limpar-logs" class="btn-clean" onclick="return confirm('Deseja limpar todos os logs?')">🧹 Limpar Logs</a>
        <pre>{log_out}</pre>
    </body>
    </html>
    """
    return html

@app.route("/api/limpar-logs", methods=["GET", "POST"])
def limpar_logs():
    msg = []
    # Limpa bot.log se existir
    for p in [os.path.join(BASE_DIR, "bot.log"), "/app/bot.log", os.path.join(BASE_DIR, "whatsapp-bot", "bot.log")]:
        if os.path.exists(p):
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(f"--- Logs limpos em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ---\n")
                msg.append(f"Arquivo de log limpo: {p}")
            except Exception as e:
                msg.append(f"Erro ao limpar {p}: {e}")
    
    import subprocess
    try:
        subprocess.run("pkill -f chrome || true; pkill -f chromium || true", shell=True, timeout=5)
        msg.append("Processos de navegador encerrados.")
    except Exception as e:
        msg.append(f"Erro no pkill: {e}")
    try:
        subprocess.run("pm2 flush || true", shell=True, timeout=5)
    except Exception:
        pass
    
    return jsonify({"status": "success", "details": msg}), 200


# ==========================================
# GESTÃO DINÂMICA DE MOTORISTAS E FROTAS
# ==========================================

DEFAULT_DRIVERS = [
    {"id": "argemiro_borges", "name": "ARGEMIRO BORGES", "cpf": "041.604.865-09", "cavalo": "PEG7666", "carreta": "DTD8506"},
    {"id": "ariel_nascimento", "name": "ARIEL NASCIMENTO", "cpf": "050.153.565-95", "cavalo": "JVL8A44", "carreta": "-"},
    {"id": "fabio_souza", "name": "FABIO SOUZA", "cpf": "890.066.155-87", "cavalo": "PEJ4695", "carreta": "NLB7814"},
    {"id": "gabriel_borges", "name": "GABRIEL BORGES", "cpf": "095.312.255-75", "cavalo": "JJF1856", "carreta": "NVQ8447"},
    {"id": "jones_rosario", "name": "JONES ROSARIO", "cpf": "053.359.465-04", "cavalo": "JHX3C33", "carreta": "KKT9007"},
    {"id": "leandro_de_andrade", "name": "LEANDRO DE ANDRADE", "cpf": "017.793.835.84", "cavalo": "NZP7012", "carreta": "-"},
    {"id": "luis_carlos", "name": "LUIS CARLOS", "cpf": "830.317.905-53", "cavalo": "KLB5018", "carreta": "NKZ6545"},
    {"id": "romilson_damasceno", "name": "ROMILSON DAMASCENO", "cpf": "615.715.635-04", "cavalo": "KJY3204", "carreta": "KGG1152"},
    {"id": "valdemir_de_jesus", "name": "VALDEMIR DE JESUS", "cpf": "044.327.095-37", "cavalo": "HWB9F22", "carreta": "-"}
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CADASTRO_PATH = os.path.join(BASE_DIR, "motoristas_cadastro.json")
WPP_MOTORISTAS_PATH = os.path.join(BASE_DIR, "whatsapp-bot", "motoristas.json")
CHEP_MOTORISTAS_PATH = os.path.join(BASE_DIR, "chep-bot", "motoristas.json")

def load_drivers_list():
    if os.path.exists(CADASTRO_PATH) and os.path.getsize(CADASTRO_PATH) > 0:
        try:
            with open(CADASTRO_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            print("Erro ao ler cadastro de motoristas:", e)
    return DEFAULT_DRIVERS

def sync_drivers_to_bots(drivers):
    bot_dict = {}
    for d in drivers:
        name = str(d.get("name") or "").strip().upper()
        if not name:
            continue
        cpf = str(d.get("cpf") or "").strip()
        cavalo = str(d.get("cavalo") or "").strip().upper()
        carreta = str(d.get("carreta") or "").strip().upper()
        if carreta and carreta != "-":
            placa_str = f"{cavalo} / {carreta}"
        else:
            placa_str = cavalo
        
        bot_dict[name] = {"cpf": cpf, "placa": placa_str}
        first_name = name.split()[0]
        bot_dict[first_name] = {"cpf": cpf, "placa": placa_str}

        if "ROMILSON" in name:
            bot_dict["ROMILDO"] = {"cpf": cpf, "placa": placa_str}
        if "LUIS" in name or "LUIZ" in name:
            bot_dict["LUIZ"] = {"cpf": cpf, "placa": placa_str}
            bot_dict["LUZ"] = {"cpf": cpf, "placa": placa_str}
            bot_dict["LUIZ CARLOS"] = {"cpf": cpf, "placa": placa_str}

    # Salva no whatsapp-bot
    try:
        with open(WPP_MOTORISTAS_PATH, "w", encoding="utf-8") as f:
            json.dump(bot_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Erro ao atualizar whatsapp-bot/motoristas.json:", e)

    # Salva no chep-bot se existir
    if os.path.exists(os.path.dirname(CHEP_MOTORISTAS_PATH)):
        try:
            with open(CHEP_MOTORISTAS_PATH, "w", encoding="utf-8") as f:
                json.dump(bot_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Erro ao atualizar chep-bot/motoristas.json:", e)

@app.route("/api/motoristas", methods=["GET", "POST"])
def api_motoristas():
    if request.method == "GET":
        drivers = load_drivers_list()
        return jsonify({"status": "success", "drivers": drivers})

    try:
        data = request.get_json(force=True) or {}
        drivers = data.get("drivers")
        if not isinstance(drivers, list) or len(drivers) == 0:
            return jsonify({"status": "error", "message": "Lista de motoristas invalida."}), 400

        sanitized = []
        for d in drivers:
            name = str(d.get("name") or "").strip().upper()
            if not name:
                continue
            key = str(d.get("id") or "").strip().lower()
            if not key:
                key = name.lower().replace(" ", "_").replace("-", "_")
            sanitized.append({
                "id": key,
                "name": name,
                "cpf": str(d.get("cpf") or "").strip(),
                "cavalo": str(d.get("cavalo") or "").strip().upper(),
                "carreta": str(d.get("carreta") or "-").strip().upper() or "-"
            })

        with open(CADASTRO_PATH, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, ensure_ascii=False, indent=2)

        sync_drivers_to_bots(sanitized)
        return jsonify({"status": "success", "message": "Motoristas e frotas atualizados com sucesso!", "drivers": sanitized})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
