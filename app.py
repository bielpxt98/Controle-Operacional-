import streamlit as st
import pandas as pd
from io import BytesIO
from supabase import create_client
from datetime import datetime

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://zkqzejnflpzknuuirlav.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Controle Operacional", layout="wide")
st.title("Controle Operacional - Nuvem de Deliveries")

def listar():
    res = supabase.table("deliveries").select("*").order("data").execute()
    return pd.DataFrame(res.data or [])

def numero(v):
    if v in ["", None]:
        return None
    try:
        return float(str(v).replace(".", "").replace(",", "."))
    except Exception:
        return None

def upsert(row):
    row["atualizado_em"] = datetime.now().isoformat()
    supabase.table("deliveries").upsert(row, on_conflict="delivery").execute()

def excluir(delivery):
    supabase.table("deliveries").delete().eq("delivery", delivery).execute()

def excel_bytes(df):
    out = BytesIO()
    view = df.copy()
    rename = {
        "data": "Data", "motorista": "Motorista", "delivery": "Delivery", "cliente": "Cliente",
        "unidade": "Unidade", "paletes": "Paletes", "valor_frete": "Valor",
        "l_horario": "L", "c_horario": "C", "f_horario": "F",
        "cs_ok": "CS_OK", "l_ok": "L_OK", "c_ok": "C_OK", "f_ok": "F_OK",
        "tipo": "Tipo", "status": "Status", "observacoes": "Observações",
        "inconsistencias": "Inconsistências", "confianca": "Confiança"
    }
    view = view.rename(columns=rename)
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        view.to_excel(writer, index=False, sheet_name="Mestre")
    return out.getvalue()

df = listar()
tab1, tab2, tab3 = st.tabs(["Buscar / Editar", "Novo registro", "Excel mestre"])

with tab1:
    q = st.text_input("Buscar delivery, motorista, cliente ou data")
    result = df
    if q and not df.empty:
        q_upper = q.upper()
        mask = df.apply(lambda r: q_upper in " ".join([str(x).upper() for x in r.values]), axis=1)
        result = df[mask]
    st.dataframe(result, use_container_width=True, hide_index=True)

    deliveries = result["delivery"].dropna().astype(str).tolist() if not result.empty and "delivery" in result else []
    selected = st.selectbox("Selecione para editar/excluir", [""] + deliveries)
    if selected:
        item = df[df["delivery"].astype(str) == selected].iloc[0].to_dict()
        with st.form("editar"):
            c1,c2,c3 = st.columns(3)
            data = c1.text_input("Data", item.get("data",""))
            motorista = c2.text_input("Motorista", item.get("motorista",""))
            delivery = c3.text_input("Delivery", item.get("delivery",""))
            c4,c5,c6 = st.columns(3)
            cliente = c4.text_input("Cliente", item.get("cliente",""))
            unidade = c5.text_input("Unidade", item.get("unidade",""))
            paletes = c6.text_input("Paletes", str(item.get("paletes") or ""))
            c7,c8,c9,c10 = st.columns(4)
            valor = c7.text_input("Valor", str(item.get("valor_frete") or ""))
            l_h = c8.text_input("L", item.get("l_horario",""))
            c_h = c9.text_input("C", item.get("c_horario",""))
            f_h = c10.text_input("F", item.get("f_horario",""))
            status = st.text_input("Status", item.get("status",""))
            tipo = st.text_input("Tipo", item.get("tipo",""))
            obs = st.text_area("Observações", item.get("observacoes",""))
            if st.form_submit_button("Salvar alterações"):
                upsert({"data":data,"motorista":motorista,"delivery":delivery,"cliente":cliente,"unidade":unidade,
                        "paletes":numero(paletes),"valor_frete":numero(valor),"l_horario":l_h,"c_horario":c_h,
                        "f_horario":f_h,"status":status,"tipo":tipo,"observacoes":obs})
                st.success("Atualizado.")
        if st.button("Excluir delivery selecionada"):
            excluir(selected)
            st.warning("Excluída.")

with tab2:
    with st.form("novo"):
        data = st.text_input("Data")
        motorista = st.text_input("Motorista")
        delivery = st.text_input("Delivery")
        cliente = st.text_input("Cliente")
        unidade = st.text_input("Unidade")
        paletes = st.text_input("Paletes")
        valor = st.text_input("Valor")
        l_h = st.text_input("L")
        c_h = st.text_input("C")
        f_h = st.text_input("F")
        status = st.text_input("Status")
        tipo = st.text_input("Tipo")
        obs = st.text_area("Observações")
        if st.form_submit_button("Salvar"):
            upsert({"data":data,"motorista":motorista,"delivery":delivery,"cliente":cliente,"unidade":unidade,
                    "paletes":numero(paletes),"valor_frete":numero(valor),"l_horario":l_h,"c_horario":c_h,
                    "f_horario":f_h,"status":status,"tipo":tipo,"observacoes":obs})
            st.success("Salvo.")

with tab3:
    st.write(f"Registros na nuvem: {len(df)}")
    st.download_button("Baixar Excel mestre atualizado", data=excel_bytes(df),
                       file_name="excel_mestre_operacional.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.dataframe(df, use_container_width=True, hide_index=True)
