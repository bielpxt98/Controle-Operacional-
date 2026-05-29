import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from supabase import create_client

st.set_page_config(page_title="Controle Operacional", layout="wide")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://zkqzejnflpzknuuirlav.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("Controle Operacional — Supabase + Excel Mestre")

def texto(v):
    if v is None or str(v).lower() == "nan":
        return ""
    return str(v).strip()

def numero(v):
    if v is None or str(v).strip() == "" or str(v).lower() == "nan":
        return None
    try:
        return float(str(v).replace("R$", "").replace(" ", "").replace(".", "").replace(",", "."))
    except Exception:
        return None

def normalizar_colunas(df):
    mapa = {}
    for c in df.columns:
        k = str(c).strip().lower()
        if k in ["data", "date"]:
            mapa[c] = "data"
        elif k in ["motorista", "driver"]:
            mapa[c] = "motorista"
        elif k in ["delivery", "documento", "doc", "remessa"]:
            mapa[c] = "delivery"
        elif k in ["cliente", "client"]:
            mapa[c] = "cliente"
        elif k in ["unidade", "local", "região", "regiao"]:
            mapa[c] = "unidade"
        elif k in ["paletes", "pallets", "pallet"]:
            mapa[c] = "paletes"
        elif k in ["valor", "frete", "valor_frete", "valor frete"]:
            mapa[c] = "valor_frete"
        elif k in ["l", "l_horario", "chegada"]:
            mapa[c] = "l_horario"
        elif k in ["c", "c_horario", "coleta"]:
            mapa[c] = "c_horario"
        elif k in ["f", "f_horario", "final"]:
            mapa[c] = "f_horario"
        elif k in ["tipo", "tipo_operacao", "tipo operação"]:
            mapa[c] = "tipo"
        elif k in ["status"]:
            mapa[c] = "status"
        elif k in ["observação", "observacao", "observações", "observacoes", "obs"]:
            mapa[c] = "observacoes"
        elif k in ["inconsistência", "inconsistencia", "inconsistências", "inconsistencias"]:
            mapa[c] = "inconsistencias"
        elif k in ["confiança", "confianca"]:
            mapa[c] = "confianca"
    return df.rename(columns=mapa)

def listar():
    res = supabase.table("deliveries").select("*").order("data").execute()
    return pd.DataFrame(res.data or [])

def montar_linha(r, bloquear_manual=False):
    delivery = texto(r.get("delivery", ""))
    if not delivery:
        return None
    linha = {
        "data": texto(r.get("data", "")),
        "motorista": texto(r.get("motorista", "")),
        "delivery": delivery,
        "cliente": texto(r.get("cliente", "")),
        "unidade": texto(r.get("unidade", "")),
        "paletes": numero(r.get("paletes", "")),
        "valor_frete": numero(r.get("valor_frete", "")),
        "l_horario": texto(r.get("l_horario", "")),
        "c_horario": texto(r.get("c_horario", "")),
        "f_horario": texto(r.get("f_horario", "")),
        "tipo": texto(r.get("tipo", "")),
        "status": texto(r.get("status", "")),
        "observacoes": texto(r.get("observacoes", "")),
        "inconsistencias": texto(r.get("inconsistencias", "")),
        "confianca": texto(r.get("confianca", "")),
        "atualizado_em": datetime.now().isoformat(),
    }
    if bloquear_manual:
        linha["cliente_bloqueado"] = True
        linha["motorista_bloqueado"] = True
        linha["unidade_bloqueado"] = True
    return linha

def buscar_existente(delivery):
    res = supabase.table("deliveries").select("*").eq("delivery", str(delivery)).limit(1).execute()
    return res.data[0] if res.data else None

def merge_preservando_manual(novo):
    existente = buscar_existente(novo["delivery"])
    if not existente:
        return novo

    obs_sistema = texto(existente.get("observacoes_sistema", ""))

    for campo, bloqueio in [
        ("cliente", "cliente_bloqueado"),
        ("motorista", "motorista_bloqueado"),
        ("unidade", "unidade_bloqueado"),
    ]:
        if existente.get(bloqueio) and texto(existente.get(campo)):
            sugerido = texto(novo.get(campo))
            confirmado = texto(existente.get(campo))
            if sugerido and sugerido != confirmado:
                obs_sistema = (obs_sistema + f" | IA sugeriu {campo}: {sugerido}; mantido manual: {confirmado}").strip(" |")
            novo[campo] = confirmado
            novo[bloqueio] = True

    if obs_sistema:
        novo["observacoes_sistema"] = obs_sistema

    return novo

def upsert_linhas(df, bloquear_manual=False):
    df = normalizar_colunas(df)
    linhas = []
    for _, row in df.iterrows():
        item = montar_linha(row, bloquear_manual=bloquear_manual)
        if item:
            linhas.append(merge_preservando_manual(item))

    if not linhas:
        return 0

    for i in range(0, len(linhas), 500):
        supabase.table("deliveries").upsert(linhas[i:i+500], on_conflict="delivery").execute()
    return len(linhas)

def excel_bytes(df):
    out = BytesIO()
    view = df.copy()
    rename = {
        "data": "Data", "motorista": "Motorista", "delivery": "Delivery", "cliente": "Cliente",
        "unidade": "Unidade", "paletes": "Paletes", "valor_frete": "Valor",
        "l_horario": "L", "c_horario": "C", "f_horario": "F",
        "cs_ok": "CS_OK", "l_ok": "L_OK", "c_ok": "C_OK", "f_ok": "F_OK",
        "tipo": "Tipo", "status": "Status", "observacoes": "Observações",
        "observacoes_sistema": "Observações do sistema",
        "inconsistencias": "Inconsistências", "confianca": "Confiança",
        "cliente_bloqueado": "Cliente manual", "motorista_bloqueado": "Motorista manual",
        "unidade_bloqueado": "Unidade manual",
    }
    view = view.rename(columns=rename)
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        view.to_excel(writer, index=False, sheet_name="Mestre")
    return out.getvalue()

tab_busca, tab_importar, tab_excel = st.tabs(["Buscar / editar", "Importar Excel mestre", "Baixar Excel mestre"])

df = listar()

with tab_busca:
    st.subheader("Buscar na nuvem")
    q = st.text_input("Pesquisar por delivery, motorista, cliente, data ou unidade")
    resultado = df
    if q and not df.empty:
        q_upper = q.upper()
        resultado = df[df.apply(lambda r: q_upper in " ".join([str(x).upper() for x in r.values]), axis=1)]
    st.dataframe(resultado, use_container_width=True, hide_index=True)

    st.subheader("Editar / excluir")
    resultado["delivery"] = resultado["delivery"].fillna("")
resultado["sr"] = resultado["sr"].fillna("")
resultado["motorista"] = resultado["motorista"].fillna("")
resultado["cliente"] = resultado["cliente"].fillna("")

resultado["label_edicao"] = (
    "ID "
    + resultado["id"].astype(str)
    + " | Delivery: "
    + resultado["delivery"].astype(str)
    + " | SR: "
    + resultado["sr"].astype(str)
    + " | Motorista: "
    + resultado["motorista"].astype(str)
    + " | Cliente: "
    + resultado["cliente"].astype(str)
)

selected = st.selectbox(
    "Selecione um registro",
    [""] + resultado["label_edicao"].tolist()
)

    if selected:
        id_selecionado = int(
    selected.split("|")[0]
    .replace("ID", "")
    .strip()
)

item = df[df["id"] == id_selecionado].iloc[0].to_dict()
        with st.form("editar"):
            c1, c2, c3 = st.columns(3)
            data = c1.text_input("Data", item.get("data", ""))
            motorista = c2.text_input("Motorista", item.get("motorista", ""))
            delivery = c3.text_input("Delivery", item.get("delivery", ""))

            c4, c5, c6 = st.columns(3)
            cliente = c4.text_input("Cliente", item.get("cliente", ""))
            unidade = c5.text_input("Unidade", item.get("unidade", ""))
            paletes = c6.text_input("Paletes", str(item.get("paletes") or ""))

            c7, c8, c9, c10 = st.columns(4)
            valor = c7.text_input("Valor", str(item.get("valor_frete") or ""))
            l_h = c8.text_input("L", item.get("l_horario", ""))
            c_h = c9.text_input("C", item.get("c_horario", ""))
            f_h = c10.text_input("F", item.get("f_horario", ""))

            tipo = st.text_input("Tipo", item.get("tipo", ""))
            status = st.text_input("Status", item.get("status", ""))
            obs = st.text_area("Observações", item.get("observacoes", ""))

            bloquear_cliente = st.checkbox("Manter cliente manual e impedir IA de trocar", value=bool(item.get("cliente_bloqueado")))
            bloquear_motorista = st.checkbox("Manter motorista manual e impedir IA de trocar", value=bool(item.get("motorista_bloqueado")))
            bloquear_unidade = st.checkbox("Manter unidade manual e impedir IA de trocar", value=bool(item.get("unidade_bloqueado")))

            if st.form_submit_button("Salvar alterações"):
                linha = montar_linha({
                    "data": data, "motorista": motorista, "delivery": delivery, "cliente": cliente,
                    "unidade": unidade, "paletes": paletes, "valor_frete": valor, "l_horario": l_h,
                    "c_horario": c_h, "f_horario": f_h, "tipo": tipo, "status": status, "observacoes": obs,
                })
                linha["cliente_bloqueado"] = bloquear_cliente
                linha["motorista_bloqueado"] = bloquear_motorista
                linha["unidade_bloqueado"] = bloquear_unidade
                supabase.table("deliveries").upsert(linha, on_conflict="delivery").execute()
                st.success("Atualizado com sucesso.")

        if st.button("Excluir delivery selecionada"):
            supabase.table("deliveries").delete().eq("delivery", selected).execute()
            st.warning("Delivery excluída.")

with tab_importar:
    st.subheader("Importar Excel mestre para a nuvem")
    st.info("Use esta aba para enviar o Excel mestre atual. Delivery existente será atualizada sem duplicar. Campos manuais bloqueados serão preservados.")

    arquivo = st.file_uploader("Enviar Excel mestre (.xlsx)", type=["xlsx"])
    if arquivo:
        abas = pd.read_excel(arquivo, sheet_name=None)
        nomes = list(abas.keys())
        aba = st.selectbox("Escolha a aba para importar", nomes)
        preview = normalizar_colunas(abas[aba])
        st.dataframe(preview.head(50), use_container_width=True)

        bloquear_manual = st.checkbox(
            "Tratar cliente/motorista/unidade deste Excel como correção manual protegida",
            value=True
        )

        if st.button("Confirmar importação para Supabase"):
            total = upsert_linhas(preview, bloquear_manual=bloquear_manual)
            st.success(f"{total} registros importados/atualizados na nuvem.")

with tab_excel:
    st.subheader("Baixar Excel mestre atualizado")
    df_atual = listar()
    st.write(f"Registros na nuvem: {len(df_atual)}")
    st.download_button(
        "⬇️ Baixar Excel mestre",
        data=excel_bytes(df_atual),
        file_name="excel_mestre_operacional.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.dataframe(df_atual, use_container_width=True, hide_index=True)
