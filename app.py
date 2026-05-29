import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from supabase import create_client

st.set_page_config(page_title="Controle Operacional", layout="wide")

# =====================================================
# SUPABASE
# =====================================================

SUPABASE_URL = "https://zkqzejnflpzknuuirlav.supabase.co"

SUPABASE_KEY = "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("Controle Operacional")


# =====================================================
# FUNÇÕES
# =====================================================

def texto(v):
    if v is None:
        return ""
    if str(v).lower() == "nan":
        return ""
    return str(v).strip()


def numero(v):
    if v is None:
        return None

    s = str(v).strip()

    if s == "":
        return None

    try:
        s = s.replace("R$", "")
        s = s.replace(".", "")
        s = s.replace(",", ".")
        return float(s)
    except:
        return None


def listar():
    res = supabase.table("deliveries").select("*").execute()
    return pd.DataFrame(res.data or [])


def excel_bytes(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Mestre")

    return output.getvalue()


# =====================================================
# TABS
# =====================================================

tab_busca, tab_excel = st.tabs(
    [
        "Buscar / editar",
        "Baixar Excel"
    ]
)

df = listar()


# =====================================================
# BUSCA
# =====================================================

with tab_busca:

    st.subheader("Buscar na nuvem")

    q = st.text_input(
        "Pesquisar por delivery, SR, motorista, cliente ou data"
    )

    resultado = df.copy()

    if q and not df.empty:

        q_upper = q.upper()

        resultado = resultado[
            resultado.apply(
                lambda r: q_upper in " ".join(
                    [str(x).upper() for x in r.values]
                ),
                axis=1
            )
        ]

    st.dataframe(
        resultado,
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Editar / excluir")

    if not resultado.empty:

        if "delivery" not in resultado.columns:
            resultado["delivery"] = ""

        if "sr" not in resultado.columns:
            resultado["sr"] = ""

        if "motorista" not in resultado.columns:
            resultado["motorista"] = ""

        if "cliente" not in resultado.columns:
            resultado["cliente"] = ""

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

                data = c1.text_input(
                    "Data",
                    texto(item.get("data"))
                )

                motorista = c2.text_input(
                    "Motorista",
                    texto(item.get("motorista"))
                )

                delivery = c3.text_input(
                    "Delivery",
                    texto(item.get("delivery"))
                )

                c4, c5, c6 = st.columns(3)

                sr = c4.text_input(
                    "SR",
                    texto(item.get("sr"))
                )

                cliente = c5.text_input(
                    "Cliente",
                    texto(item.get("cliente"))
                )

                unidade = c6.text_input(
                    "Unidade",
                    texto(item.get("unidade"))
                )

                c7, c8, c9 = st.columns(3)

                paletes = c7.text_input(
                    "Paletes",
                    texto(item.get("paletes"))
                )

                valor = c8.text_input(
                    "Valor",
                    texto(item.get("valor_frete"))
                )

                status = c9.text_input(
                    "Status",
                    texto(item.get("status"))
                )

                c10, c11, c12 = st.columns(3)

                l_h = c10.text_input(
                    "L",
                    texto(item.get("l_horario"))
                )

                c_h = c11.text_input(
                    "C",
                    texto(item.get("c_horario"))
                )

                f_h = c12.text_input(
                    "F",
                    texto(item.get("f_horario"))
                )

                observacoes = st.text_area(
                    "Observações",
                    texto(item.get("observacoes"))
                )

                salvar = st.form_submit_button(
                    "Salvar alterações"
                )

                if salvar:

                    registro = {
                        "data": data,
                        "motorista": motorista,
                        "delivery": delivery,
                        "sr": sr,
                        "cliente": cliente,
                        "unidade": unidade,
                        "paletes": numero(paletes),
                        "valor_frete": numero(valor),
                        "status": status,
                        "l_horario": l_h,
                        "c_horario": c_h,
                        "f_horario": f_h,
                        "observacoes": observacoes,
                        "atualizado_em": datetime.now().isoformat()
                    }

                    supabase.table("deliveries").update(
                        registro
                    ).eq(
                        "id",
                        id_selecionado
                    ).execute()

                    st.success("Registro atualizado")

            if st.button("Excluir registro"):

                supabase.table("deliveries").delete().eq(
                    "id",
                    id_selecionado
                ).execute()

                st.warning("Registro excluído")


# =====================================================
# EXCEL
# =====================================================

with tab_excel:

    st.subheader("Baixar Excel Mestre")

    df_atual = listar()

    st.download_button(
        "Baixar Excel",
        data=excel_bytes(df_atual),
        file_name="excel_mestre_operacional.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.dataframe(
        df_atual,
        use_container_width=True,
        hide_index=True
    )
