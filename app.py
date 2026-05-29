import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from supabase import create_client

st.set_page_config(page_title="Controle Operacional", layout="wide")

SUPABASE_URL = "https://zkqzejnflpzknuuirlav.supabase.co"
SUPABASE_KEY = "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("Controle Operacional — Supabase + Excel Mestre")


def texto(v):
    if v is None:
        return ""
    if str(v).lower() in ["nan", "none", "null"]:
        return ""
    return str(v).strip()


def numero(v):
    if v is None:
        return None

    s = str(v).strip()

    if s == "" or s.lower() in ["nan", "none", "null"]:
        return None

    try:
        s = s.replace("R$", "")
        s = s.replace(" ", "")
        s = s.replace(".", "")
        s = s.replace(",", ".")
        return float(s)
    except Exception:
        return None


def listar():
    res = supabase.table("deliveries").select("*").order("id").execute()
    return pd.DataFrame(res.data or [])


def normalizar_colunas(df):
    mapa = {}

    for c in df.columns:
        k = str(c).strip().lower()

        if k in ["data", "date"]:
            mapa[c] = "data"
        elif k in ["data_finalizacao", "data finalização", "finalizacao"]:
            mapa[c] = "data_finalizacao"
        elif k in ["motorista", "driver"]:
            mapa[c] = "motorista"
        elif k in ["delivery", "documento", "doc", "remessa"]:
            mapa[c] = "delivery"
        elif k in ["sr", "s/r"]:
            mapa[c] = "sr"
        elif k in ["cliente", "client"]:
            mapa[c] = "cliente"
        elif k in ["unidade", "local", "regiao", "região"]:
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
        elif k in ["tipo", "tipo_operacao"]:
            mapa[c] = "tipo"
        elif k in ["status"]:
            mapa[c] = "status"
        elif k in ["observacao", "observação", "observacoes", "observações", "obs"]:
            mapa[c] = "observacoes"
        elif k in ["inconsistencia", "inconsistência", "inconsistencias", "inconsistências"]:
            mapa[c] = "inconsistencias"
        elif k in ["confianca", "confiança"]:
            mapa[c] = "confianca"
        elif k in ["cpf"]:
            mapa[c] = "cpf"
        elif k in ["cavalo"]:
            mapa[c] = "cavalo"
        elif k in ["carreta"]:
            mapa[c] = "carreta"

    return df.rename(columns=mapa)


def montar_registro(row):
    delivery = texto(row.get("delivery", ""))
    sr = texto(row.get("sr", ""))

    if not delivery and not sr:
        return None

    return {
        "data": texto(row.get("data", "")) or None,
        "data_finalizacao": texto(row.get("data_finalizacao", "")) or None,
        "motorista": texto(row.get("motorista", "")) or None,
        "delivery": delivery or None,
        "sr": sr or None,
        "cliente": texto(row.get("cliente", "")) or None,
        "unidade": texto(row.get("unidade", "")) or None,
        "paletes": numero(row.get("paletes", "")),
        "valor_frete": numero(row.get("valor_frete", "")),
        "l_horario": texto(row.get("l_horario", "")) or None,
        "c_horario": texto(row.get("c_horario", "")) or None,
        "f_horario": texto(row.get("f_horario", "")) or None,
        "tipo": texto(row.get("tipo", "")) or None,
        "status": texto(row.get("status", "")) or None,
        "observacoes": texto(row.get("observacoes", "")) or None,
        "inconsistencias": texto(row.get("inconsistencias", "")) or None,
        "confianca": texto(row.get("confianca", "")) or None,
        "cpf": texto(row.get("cpf", "")) or None,
        "cavalo": texto(row.get("cavalo", "")) or None,
        "carreta": texto(row.get("carreta", "")) or None,
        "atualizado_em": datetime.now().isoformat(),
    }


def salvar_registro(registro):
    if registro.get("delivery"):
        supabase.table("deliveries").upsert(
            registro,
            on_conflict="delivery"
        ).execute()
    elif registro.get("sr"):
        supabase.table("deliveries").upsert(
            registro,
            on_conflict="sr"
        ).execute()


def excel_bytes(df):
    out = BytesIO()

    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Mestre")

    return out.getvalue()


tab_busca, tab_importar, tab_excel = st.tabs(
    [
        "Buscar / editar",
        "Importar Excel mestre",
        "Baixar Excel mestre",
    ]
)

df = listar()


with tab_busca:
    st.subheader("Buscar na nuvem")

    q = st.text_input(
        "Pesquisar por delivery, SR, motorista, cliente, data ou unidade"
    )

    resultado = df.copy()

    if q and not df.empty:
        q_upper = q.upper()

        resultado = df[
            df.apply(
                lambda r: q_upper in " ".join([str(x).upper() for x in r.values]),
                axis=1,
            )
        ]

    st.dataframe(resultado, use_container_width=True, hide_index=True)

    st.subheader("Editar / excluir")

    id_digitado = st.text_input("Digite o ID do registro para editar")

    if id_digitado:
        try:
            id_selecionado = int(id_digitado)

            item_df = df[df["id"] == id_selecionado]

            if item_df.empty:
                st.warning("ID não encontrado.")
            else:
                item = item_df.iloc[0].to_dict()

                with st.form("editar"):
                    c1, c2, c3, c4 = st.columns(4)

                    data = c1.text_input("Data", texto(item.get("data")))
                    data_finalizacao = c2.text_input(
                        "Data Finalização",
                        texto(item.get("data_finalizacao"))
                    )
                    motorista = c3.text_input("Motorista", texto(item.get("motorista")))
                    delivery = c4.text_input("Delivery", texto(item.get("delivery")))

                    c5, c6, c7, c8 = st.columns(4)

                    sr = c5.text_input("SR", texto(item.get("sr")))
                    cliente = c6.text_input("Cliente", texto(item.get("cliente")))
                    unidade = c7.text_input("Unidade", texto(item.get("unidade")))
                    paletes = c8.text_input("Paletes", texto(item.get("paletes")))

                    c9, c10, c11, c12 = st.columns(4)

                    valor = c9.text_input("Valor Frete", texto(item.get("valor_frete")))
                    l_h = c10.text_input("L", texto(item.get("l_horario")))
                    c_h = c11.text_input("C", texto(item.get("c_horario")))
                    f_h = c12.text_input("F", texto(item.get("f_horario")))

                    c13, c14, c15 = st.columns(3)

                    tipo = c13.text_input("Tipo", texto(item.get("tipo")))
                    status = c14.text_input("Status", texto(item.get("status")))
                    confianca = c15.text_input("Confiança", texto(item.get("confianca")))

                    cpf = st.text_input("CPF", texto(item.get("cpf")))
                    cavalo = st.text_input("Cavalo", texto(item.get("cavalo")))
                    carreta = st.text_input("Carreta", texto(item.get("carreta")))

                    observacoes = st.text_area(
                        "Observações",
                        texto(item.get("observacoes"))
                    )

                    inconsistencias = st.text_area(
                        "Inconsistências",
                        texto(item.get("inconsistencias"))
                    )

                    salvar = st.form_submit_button("Salvar alterações")

                    if salvar:
                        registro = {
                            "data": data or None,
                            "data_finalizacao": data_finalizacao or None,
                            "motorista": motorista or None,
                            "delivery": delivery or None,
                            "sr": sr or None,
                            "cliente": cliente or None,
                            "unidade": unidade or None,
                            "paletes": numero(paletes),
                            "valor_frete": numero(valor),
                            "l_horario": l_h or None,
                            "c_horario": c_h or None,
                            "f_horario": f_h or None,
                            "tipo": tipo or None,
                            "status": status or None,
                            "confianca": confianca or None,
                            "cpf": cpf or None,
                            "cavalo": cavalo or None,
                            "carreta": carreta or None,
                            "observacoes": observacoes or None,
                            "inconsistencias": inconsistencias or None,
                            "atualizado_em": datetime.now().isoformat(),
                        }

                        supabase.table("deliveries").update(registro).eq(
                            "id",
                            id_selecionado
                        ).execute()

                        st.success("Registro atualizado.")

                if st.button("Excluir registro"):
                    supabase.table("deliveries").delete().eq(
                        "id",
                        id_selecionado
                    ).execute()

                    st.warning("Registro excluído.")

        except Exception as e:
            st.error(f"Erro ao editar: {e}")


with tab_importar:
    st.subheader("Importar Excel mestre")

    arquivo = st.file_uploader(
        "Enviar Excel mestre (.xlsx)",
        type=["xlsx"]
    )

    if arquivo:
        abas = pd.read_excel(arquivo, sheet_name=None)

        nomes_abas = list(abas.keys())

        aba = st.selectbox("Escolha a aba", nomes_abas)

        df_excel = normalizar_colunas(abas[aba])

        st.dataframe(df_excel.head(50), use_container_width=True)

        if st.button("Importar para Supabase"):
            total = 0
            ignorados = 0

            for _, row in df_excel.iterrows():
                registro = montar_registro(row)

                if not registro:
                    ignorados += 1
                    continue

                salvar_registro(registro)
                total += 1

            st.success(f"{total} registros importados/atualizados.")
            st.info(f"{ignorados} linhas ignoradas sem delivery e sem SR.")


with tab_excel:
    st.subheader("Baixar Excel mestre atualizado")

    df_atual = listar()

    st.write(f"Registros na nuvem: {len(df_atual)}")

    st.download_button(
        "⬇️ Baixar Excel mestre",
        data=excel_bytes(df_atual),
        file_name="excel_mestre_operacional.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.dataframe(df_atual, use_container_width=True, hide_index=True)
