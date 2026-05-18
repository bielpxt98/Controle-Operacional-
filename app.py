
from pathlib import Path
from datetime import datetime
import shutil
import pandas as pd
import streamlit as st
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

APP = "Controle Operacional Local Gratuito"
DATA_DIR = Path("dados")
BACKUP_DIR = DATA_DIR / "backups"
MASTER_FILE = DATA_DIR / "excel_mestre_operacional.xlsx"

DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

COLS = [
    "Data", "Motorista", "Documento", "Cliente", "Unidade", "Paletes", "Valor",
    "L", "C", "F", "Status", "Tipo", "CPF", "Cavalo", "Carreta",
    "CS_OK", "C_OK", "L_OK", "F_OK", "Observações", "Inconsistências"
]

FILL_HEADER = "1F4E78"
FILL_L = "BDD7EE"
FILL_C = "FFF2CC"
FILL_F = "C6E0B4"
FILL_PROBLEM = "FFC7CE"
FILL_MONEY = "E2F0D9"

MOTORISTAS = {
    "GABRIEL BORGES": {"CPF": "809.066.155-87", "Cavalo": "KIY3204", "Carreta": "KGG1152"},
    "VALDEMIR DE JESUS": {"CPF": "044.327.095-37", "Cavalo": "KFL0115", "Carreta": ""},
    "JEAN ROBSON": {"CPF": "032.795.865-00", "Cavalo": "HWB9F22", "Carreta": ""},
    "WILSON REIS": {"CPF": "806.984.765-49", "Cavalo": "JJF1856", "Carreta": "NKZ6545"},
    "FABIO SOUZA": {"CPF": "007.714.835-30", "Cavalo": "PEJ4695", "Carreta": "NVQ8447"},
    "LUIS CARLOS": {"CPF": "934.560.345-04", "Cavalo": "KLB5018", "Carreta": "DTD8506"},
    "ARGEMIRO BORGES": {"CPF": "041.604.865-09", "Cavalo": "PEG7666", "Carreta": ""},
    "JONES ROSARIO": {"CPF": "533.594.654-00", "Cavalo": "JHX3C33", "Carreta": "KKT9007"},
}

def norm(v):
    return str(v or "").strip()

def norm_upper(v):
    return norm(v).upper()

def only_digits(v):
    return "".join(ch for ch in norm(v) if ch.isdigit())

def day_sheet_name(data):
    return norm(data).replace("/", "-") if norm(data) else "Sem data"

def create_empty_workbook(path=MASTER_FILE):
    wb = Workbook()
    ws = wb.active
    ws.title = "Mestre"
    ws.append(COLS)
    add_rules_sheet(wb)
    style_all(wb)
    wb.save(path)

def add_rules_sheet(wb):
    if "Regras" in wb.sheetnames:
        del wb["Regras"]
    ws = wb.create_sheet("Regras")
    rows = [
        ["Regra", "Descrição"],
        ["Sem custo de API", "Este sistema não lê foto automaticamente por IA paga. Ele guarda, organiza, busca e atualiza o Excel mestre local."],
        ["Fluxo", "Você envia as fotos no ChatGPT, recebe o Excel atualizado e importa aqui."],
        ["Histórico", "Nunca apagar histórico anterior; sempre consolidar registros por documento/data."],
        ["L/C/F", "Usar somente horários confirmados conforme sua interpretação operacional."],
        ["Sem coleta", "Quando houver deslocamento, D ou sem coleta, não criar C."],
        ["Remessa", "Remessa 3401 pode ter apenas CS/C/L/F OK, sem horários."],
        ["Bonocô Jean", "Delivery Bonocô do Jean termina com 3871."],
        ["JDE CAFÉ", "Remessas JDE CAFÉ devem manter exatamente esse nome."],
    ]
    for r in rows:
        ws.append(r)

def style_ws(ws):
    thin = Side(style="thin", color="D9E2F3")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=FILL_HEADER)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=thin)
    headers = [c.value for c in ws[1]]
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
            header = headers[cell.column-1] if cell.column-1 < len(headers) else ""
            if header == "L":
                cell.fill = PatternFill("solid", fgColor=FILL_L)
            elif header == "C":
                cell.fill = PatternFill("solid", fgColor=FILL_C)
            elif header == "F":
                cell.fill = PatternFill("solid", fgColor=FILL_F)
            elif header == "Valor":
                cell.fill = PatternFill("solid", fgColor=FILL_MONEY)
            elif header == "Inconsistências" and cell.value:
                cell.fill = PatternFill("solid", fgColor=FILL_PROBLEM)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = {
        "A": 12, "B": 22, "C": 16, "D": 32, "E": 18, "F": 10, "G": 12,
        "H": 10, "I": 10, "J": 10, "K": 22, "L": 15, "M": 16, "N": 12,
        "O": 12, "P": 9, "Q": 9, "R": 9, "S": 9, "T": 45, "U": 45
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

def style_all(wb):
    for ws in wb.worksheets:
        style_ws(ws)

def backup_current():
    if MASTER_FILE.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(MASTER_FILE, BACKUP_DIR / f"backup_excel_mestre_{ts}.xlsx")

def ensure_workbook():
    if not MASTER_FILE.exists():
        create_empty_workbook()

def ensure_day_sheet(wb, data):
    name = day_sheet_name(data)
    if name not in wb.sheetnames:
        ws = wb.create_sheet(name)
        ws.append(COLS)
    return wb[name]

def get_headers(ws):
    return [c.value for c in ws[1]]

def find_record_row(ws, documento, data=None):
    doc = only_digits(documento)
    if not doc:
        return None
    for idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        row_doc = only_digits(row[2].value)
        row_data = norm(row[0].value)
        if row_doc == doc and (not data or row_data == norm(data)):
            return idx
    for idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        if only_digits(row[2].value) == doc:
            return idx
    return None

def enrich(row):
    motorista = norm_upper(row.get("Motorista"))
    for name, data in MOTORISTAS.items():
        if motorista and (motorista in name or name in motorista):
            row["Motorista"] = name.title()
            row["CPF"] = data["CPF"]
            row["Cavalo"] = data["Cavalo"]
            row["Carreta"] = data["Carreta"]
            break

    doc = only_digits(row.get("Documento"))
    cliente = norm_upper(row.get("Cliente"))
    unidade = norm_upper(row.get("Unidade"))
    mot = norm_upper(row.get("Motorista"))

    if "JEAN" in mot and ("BONOCO" in cliente or "BONOCÔ" in cliente or "BONOCO" in unidade or "BONOCÔ" in unidade):
        if doc.endswith("3816"):
            row["Documento"] = doc[:-4] + "3871"
            row["Observações"] = (norm(row.get("Observações")) + " | Corrigido Bonocô Jean final 3871").strip(" |")

    if doc.startswith("3401") and ("JDE" in cliente or "CAFÉ" in cliente or "CAFE" in cliente):
        row["Cliente"] = "JDE CAFÉ"

    status_context = " ".join([norm_upper(row.get("Status")), norm_upper(row.get("Tipo")), norm_upper(row.get("Observações"))])
    if any(x in status_context for x in ["DESLOCAMENTO", "SEM COLETA", "BLOQUEIO"]):
        row["C"] = ""
        if not norm(row.get("Tipo")):
            row["Tipo"] = "deslocamento"
    return row

def update_ws(ws, row):
    row = enrich(row.copy())
    headers = get_headers(ws)
    data = norm(row.get("Data"))
    doc = norm(row.get("Documento"))
    idx = find_record_row(ws, doc, data)

    values = [row.get(c, "") for c in COLS]

    if idx is None:
        ws.append(values)
        return "criado"

    # atualizar somente campos novos; horários já existentes não são apagados automaticamente
    for col_idx, col_name in enumerate(COLS, start=1):
        new_val = row.get(col_name, "")
        cell = ws.cell(idx, col_idx)
        if new_val in ["", None, False]:
            continue
        if col_name in ["L", "C", "F"] and cell.value and norm(cell.value) != norm(new_val):
            obs_col = headers.index("Observações") + 1
            old_obs = norm(ws.cell(idx, obs_col).value)
            ws.cell(idx, obs_col).value = (old_obs + f" | {col_name} mantido {cell.value}; novo sugerido {new_val}").strip(" |")
            continue
        cell.value = new_val
    return "atualizado"

def workbook_to_df():
    ensure_workbook()
    wb = load_workbook(MASTER_FILE, data_only=True)
    ws = wb["Mestre"]
    data = list(ws.values)
    if len(data) <= 1:
        return pd.DataFrame(columns=COLS)
    return pd.DataFrame(data[1:], columns=data[0]).dropna(how="all")

def import_excel(uploaded):
    tmp = DATA_DIR / "importado.xlsx"
    tmp.write_bytes(uploaded.getvalue())

    backup_current()
    ensure_workbook()

    source = load_workbook(tmp, data_only=True)
    target = load_workbook(MASTER_FILE)

    # tenta usar aba Mestre; senão usa primeira aba
    s_ws = source["Mestre"] if "Mestre" in source.sheetnames else source[source.sheetnames[0]]
    rows = list(s_ws.values)
    if not rows:
        return 0

    headers = [norm(h) for h in rows[0]]
    count = 0

    for raw in rows[1:]:
        if not any(raw):
            continue
        row = {}
        for i, h in enumerate(headers):
            if h in COLS:
                row[h] = raw[i] if i < len(raw) else ""
        # mínimo necessário
        if not row.get("Documento") and len(raw) >= 3:
            row["Documento"] = raw[2]
        if not row.get("Data") and len(raw) >= 1:
            row["Data"] = raw[0]
        if not row.get("Motorista") and len(raw) >= 2:
            row["Motorista"] = raw[1]

        if not norm(row.get("Documento")):
            continue

        m_ws = target["Mestre"]
        d_ws = ensure_day_sheet(target, row.get("Data"))
        update_ws(m_ws, row)
        update_ws(d_ws, row)
        count += 1

    add_rules_sheet(target)
    style_all(target)
    target.save(MASTER_FILE)
    return count

def add_manual_record(row):
    backup_current()
    ensure_workbook()
    wb = load_workbook(MASTER_FILE)
    update_ws(wb["Mestre"], row)
    update_ws(ensure_day_sheet(wb, row.get("Data")), row)
    add_rules_sheet(wb)
    style_all(wb)
    wb.save(MASTER_FILE)

st.set_page_config(page_title=APP, layout="wide")
st.title(APP)

st.info("Sistema gratuito/local: você importa o Excel atualizado que recebeu do ChatGPT, o programa guarda histórico, separa por dia e permite busca. Não usa API paga.")

with st.sidebar:
    st.header("Arquivo mestre")
    if not MASTER_FILE.exists():
        if st.button("Criar Excel mestre vazio"):
            create_empty_workbook()
            st.success("Criado.")
    st.write(f"Arquivo local: `{MASTER_FILE}`")
    if MASTER_FILE.exists():
        with open(MASTER_FILE, "rb") as f:
            st.download_button("Baixar Excel mestre local", f, file_name="excel_mestre_operacional.xlsx")

tab1, tab2, tab3, tab4 = st.tabs(["Importar Excel atualizado", "Buscar", "Adicionar manual", "Histórico"])

with tab1:
    st.subheader("Importar Excel atualizado")
    st.write("Use aqui o Excel que o ChatGPT te enviou. O sistema consolida no banco local sem apagar histórico.")
    uploaded = st.file_uploader("Enviar Excel atualizado (.xlsx)", type=["xlsx"])
    if uploaded and st.button("Importar e consolidar"):
        qtd = import_excel(uploaded)
        st.success(f"Importação concluída. Registros processados: {qtd}")

with tab2:
    st.subheader("Busca operacional")
    df = workbook_to_df()
    q = st.text_input("Pesquisar por delivery, final, motorista, cliente, CPF, placa, unidade, data, remessa...")
    if q:
        qn = norm_upper(q)
        mask = df.apply(lambda r: qn in " ".join([norm_upper(x) for x in r.values]), axis=1)
        result = df[mask]
    else:
        result = df
    st.dataframe(result, use_container_width=True, hide_index=True)
    st.caption(f"{len(result)} registro(s) encontrado(s).")

with tab3:
    st.subheader("Adicionar ou corrigir registro manualmente")
    with st.form("manual"):
        c1, c2, c3 = st.columns(3)
        data = c1.text_input("Data", placeholder="15/05/2026")
        motorista = c2.text_input("Motorista")
        documento = c3.text_input("Delivery / Remessa")

        c4, c5, c6 = st.columns(3)
        cliente = c4.text_input("Cliente")
        unidade = c5.text_input("Unidade")
        tipo = c6.selectbox("Tipo", ["delivery", "remessa", "deslocamento", "sem coleta", "não identificado"])

        c7, c8, c9, c10, c11 = st.columns(5)
        paletes = c7.text_input("Paletes")
        valor = c8.text_input("Valor")
        L = c9.text_input("L")
        C = c10.text_input("C")
        F = c11.text_input("F")

        c12, c13, c14, c15 = st.columns(4)
        CS_OK = c12.checkbox("CS OK")
        C_OK = c13.checkbox("C OK")
        L_OK = c14.checkbox("L OK")
        F_OK = c15.checkbox("F OK")

        status = st.text_input("Status")
        obs = st.text_area("Observações")
        inc = st.text_area("Inconsistências")

        submitted = st.form_submit_button("Salvar no Excel mestre local")
        if submitted:
            row = {
                "Data": data, "Motorista": motorista, "Documento": documento,
                "Cliente": cliente, "Unidade": unidade, "Paletes": paletes, "Valor": valor,
                "L": L, "C": C, "F": F, "Status": status, "Tipo": tipo,
                "CS_OK": CS_OK, "C_OK": C_OK, "L_OK": L_OK, "F_OK": F_OK,
                "Observações": obs, "Inconsistências": inc
            }
            add_manual_record(row)
            st.success("Registro salvo/atualizado.")

with tab4:
    st.subheader("Histórico local")
    df = workbook_to_df()
    if df.empty:
        st.warning("Ainda não há registros.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Registros", len(df))
        c2.metric("Motoristas", df["Motorista"].dropna().nunique())
        c3.metric("Clientes", df["Cliente"].dropna().nunique())
        c4.metric("Dias", df["Data"].dropna().nunique())

        st.write("Últimos registros:")
        st.dataframe(df.tail(30), use_container_width=True, hide_index=True)
