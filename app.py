import importlib
import re
import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from PIL import Image, ImageOps
from datetime import datetime
from supabase import create_client
from google import genai
from google.genai import types


ST_CROPPER_DISPONIVEL = importlib.util.find_spec("streamlit_cropper") is not None
st_cropper = (
    importlib.import_module("streamlit_cropper").st_cropper
    if ST_CROPPER_DISPONIVEL
    else None
)

st.set_page_config(page_title="Controle Operacional", layout="wide")

SUPABASE_URL = "https://zkqzejnflpzknuuirlav.supabase.co"
SUPABASE_KEY = "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


MOTORISTAS_FIXOS = {
    "WILSON REIS": {"cpf": "806.984.765-49", "cavalo": "JJF1856", "carreta": "NVQ8447"},
    "FABIO SOUZA": {"cpf": "007.714.335-30", "cavalo": "PEL4695", "carreta": "NLB7814"},
    "LUIS CARLOS": {"cpf": "934.560.345-04", "cavalo": "KLB5018", "carreta": "NKZ6545"},
    "ARGEMIRO BORGES": {"cpf": "041.604.865-09", "cavalo": "PEG7666", "carreta": "DTD8506"},
    "JEAN ROBSON": {"cpf": "032.795.865-00", "cavalo": "HWB9F22", "carreta": "TRUCK"},
    "JONES ROSARIO": {"cpf": "538.594.654-00", "cavalo": "JHX3C33", "carreta": "KKT9007"},
    "GABRIEL BORGES": {"cpf": "809.066.155-87", "cavalo": "KJV8204", "carreta": "KG61152"},
    "VALDEMIR DE JESUS": {"cpf": "044.327.095-37", "cavalo": "KFL0115", "carreta": "TRUCK"},
}


def texto(v):
    if v is None:
        return ""
    if str(v).lower() in ["nan", "none", "null"]:
        return ""
    return str(v).strip()


def limpar_busca(v):
    s = texto(v).upper()
    troca = {
        "Á": "A", "À": "A", "Â": "A", "Ã": "A",
        "É": "E", "Ê": "E",
        "Í": "I",
        "Ó": "O", "Ô": "O", "Õ": "O",
        "Ú": "U",
        "Ç": "C",
    }
    for a, b in troca.items():
        s = s.replace(a, b)
    return s


def normalizar_motorista(v):
    n = limpar_busca(v)

    if "WILSON" in n:
        return "WILSON REIS"
    if "FABIO" in n:
        return "FABIO SOUZA"
    if "LUIS" in n:
        return "LUIS CARLOS"
    if "ARGEMIRO" in n:
        return "ARGEMIRO BORGES"
    if "JEAN" in n:
        return "JEAN ROBSON"
    if "JONES" in n:
        return "JONES ROSARIO"
    if "GABRIEL" in n:
        return "GABRIEL BORGES"
    if "VALDEMIR" in n:
        return "VALDEMIR DE JESUS"

    return texto(v).upper()


def completar_dados_motorista(campos):
    motorista = normalizar_motorista(campos.get("motorista", ""))

    if motorista:
        campos["motorista"] = motorista

    dados = MOTORISTAS_FIXOS.get(motorista)

    if dados:
        campos["cpf"] = dados["cpf"]
        campos["cavalo"] = dados["cavalo"]
        campos["carreta"] = dados["carreta"]

    return campos



FORMATOS_IMAGEM_GEMINI = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def obter_gemini_api_key():
    try:
        api_key = texto(st.secrets["GEMINI_API_KEY"])
    except Exception:
        return ""

    return api_key


def validar_imagem_gemini(arquivo_imagem):
    if not arquivo_imagem:
        return None, None, "Envie uma imagem antes de interpretar."

    nome_arquivo = texto(getattr(arquivo_imagem, "name", ""))
    extensao = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
    mime_type = FORMATOS_IMAGEM_GEMINI.get(extensao)

    if not mime_type:
        return None, None, "Formato inválido. Envie uma imagem JPG, JPEG ou PNG."

    try:
        imagem_bytes = arquivo_imagem.getvalue()
    except Exception:
        return None, None, "Não foi possível ler a imagem enviada."

    if not imagem_bytes:
        return None, None, "A imagem enviada está vazia ou corrompida."

    try:
        with Image.open(BytesIO(imagem_bytes)) as imagem:
            formato_real = texto(imagem.format).lower()
            imagem.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None, "A imagem enviada não pôde ser aberta como JPG, JPEG ou PNG."

    if formato_real not in FORMATOS_IMAGEM_GEMINI:
        return None, None, "Formato inválido. Envie uma imagem JPG, JPEG ou PNG."

    mime_type = FORMATOS_IMAGEM_GEMINI[formato_real]
    return imagem_bytes, mime_type, None


def consultar_gemini(client, **kwargs):
    ultimo_erro = None

    for modelo in ["gemini-2.5-flash", "gemini-1.5-flash"]:
        try:
            resposta = client.models.generate_content(model=modelo, **kwargs)
            return resposta, modelo
        except Exception as e:
            ultimo_erro = e

    raise ultimo_erro


def mostrar_erro_gemini(erro):
    st.error("Erro ao consultar Gemini. Verifique a chave, limite da API ou formato da imagem.")

    with st.expander("Detalhes do erro"):
        st.code(repr(erro))


def testar_gemini():
    api_key = obter_gemini_api_key()

    if not api_key:
        st.error("Configure GEMINI_API_KEY em st.secrets para usar a integração Gemini.")
        return False

    try:
        client = genai.Client(api_key=api_key)
        resposta = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Responda apenas OK",
        )
    except Exception as e:
        mostrar_erro_gemini(e)
        return False

    st.success("Teste Gemini concluído.")
    st.write(texto(resposta.text))
    st.session_state["gemini_teste_ok"] = True
    return True

st.title("Controle Operacional — Supabase + Excel Mestre")


def senha_admin_configurada():
    try:
        return bool(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        return False


def autenticar_admin():
    if "admin_autenticado" not in st.session_state:
        st.session_state.admin_autenticado = False

    with st.sidebar:
        st.header("Acesso")

        if st.session_state.admin_autenticado:
            st.success("Administrador autenticado")
            if st.button("Sair do modo administrador"):
                st.session_state.admin_autenticado = False
                st.rerun()
            return True

        st.info("Visitante: acesso somente para buscar e visualizar.")

        if not senha_admin_configurada():
            st.warning("Configure ADMIN_PASSWORD em st.secrets para liberar o modo administrador.")
            return False

        senha = st.text_input("Senha administrativa", type="password")

        if st.button("Entrar como administrador"):
            if senha == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.admin_autenticado = True
                st.rerun()
            else:
                st.error("Senha administrativa inválida.")

        return False



def carregar_regras_operacionais():
    caminho_regras = "REGRAS_OPERACIONAIS.md"

    try:
        with open(caminho_regras, "r", encoding="utf-8") as arquivo_regras:
            regras = arquivo_regras.read().strip()
    except FileNotFoundError:
        regras = ""

    if regras:
        return regras

    return """
Você é um assistente operacional que lê fotos de folhas operacionais.
Extraia somente os registros operacionais visíveis e devolva uma linha por registro.
Não invente dados que não estejam legíveis na imagem.
Quando um campo não estiver legível, omita o campo em vez de chutar.
Use exatamente as abreviações aceitas pela Atualização rápida:
DATA = Data no formato dd/mm/aaaa
DF = Data finalização no formato dd/mm/aaaa
M = Motorista
D = Delivery
SR = SR
CL = Cliente
P = Paletes
V = Valor do frete com vírgula decimal quando houver centavos
L = Chegada no formato HH:MM
C = Coleta no formato HH:MM
FI = Finalização no formato HH:MM
O = Observação, somente para deslocamento, bloqueio, motivo, remessa, NOK, CS OK, C OK ou L OK

Regras obrigatórias:
- Devolva apenas as linhas da Atualização rápida, sem explicações, sem markdown e sem numeração.
- Cada registro deve ficar em uma única linha.
- Não use o campo S.
- S.F e L.F devem ficar dentro do campo CL, junto do cliente.
- FI deve conter somente horário.
- O não deve ser usado para HP, última ocorrência, finalizado ou em andamento.
- Normalize nomes conhecidos quando possível: Jean, Wilson, Luis, Gabriel, Jones, Fabio, Argemiro ou Valdemir.

Exemplo de saída:
DATA 15/06/2026 M JEAN D 3787805566 P 117 CL ASSAÍ PARIPE V 1021,05 L 08:08 C 09:31 FI 13:44
""".strip()


def interpretar_folha_com_gemini(imagem_bytes, mime_type="image/png"):
    api_key = obter_gemini_api_key()

    if not api_key:
        raise ValueError("GEMINI_API_KEY não configurada em st.secrets.")

    regras = carregar_regras_operacionais()
    prompt = f"""
Leia a imagem da folha operacional e transforme os registros encontrados em texto para a Atualização rápida.

REGRAS OPERACIONAIS:
{regras}

SAÍDA OBRIGATÓRIA:
Devolva somente as linhas no formato da Atualização rápida. Não inclua explicações.
""".strip()

    client = genai.Client(api_key=api_key)
    resposta, modelo_usado = consultar_gemini(
        client,
        contents=[
            prompt,
            types.Part.from_bytes(data=imagem_bytes, mime_type=mime_type),
        ],
    )

    return texto(resposta.text), modelo_usado

def trocar_ano_data(valor, ano=2026):
    s = texto(valor)
    if not s:
        return None

    data = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(data):
        return valor

    try:
        data = data.replace(year=ano)
    except ValueError:
        data = data.replace(month=2, day=28, year=ano)

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", s):
        return data.strftime("%Y-%m-%d")

    return data.strftime("%d/%m/%Y")


def atualizar_datas_para_2026():
    df_datas = listar()
    total = 0

    if df_datas.empty or "id" not in df_datas.columns:
        return total

    for _, row in df_datas.iterrows():
        atualizacao = {"atualizado_em": datetime.now().isoformat()}

        for coluna in ["data", "data_finalizacao"]:
            if coluna in df_datas.columns:
                valor_atual = row.get(coluna)
                novo_valor = trocar_ano_data(valor_atual, 2026)

                if novo_valor != valor_atual:
                    atualizacao[coluna] = novo_valor

        if len(atualizacao) > 1:
            supabase.table("deliveries").update(atualizacao).eq("id", row["id"]).execute()
            total += 1

    return total


def numero(v):
    if v is None:
        return None

    s = str(v).strip()

    if s == "" or s.lower() in ["nan", "none", "null", "—", "-"]:
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
    res = supabase.table("deliveries").select("*").execute()
    return ordenar_visualizacao(pd.DataFrame(res.data or []))


def ordenar_visualizacao(df):
    if df.empty:
        return df

    ordenado = df.copy()

    if "data" in ordenado.columns:
        ordenado["_data_ordem"] = pd.to_datetime(
            ordenado["data"],
            errors="coerce",
            dayfirst=True,
        )
    else:
        ordenado["_data_ordem"] = pd.NaT

    if "id" in ordenado.columns:
        ordenado["_id_ordem"] = pd.to_numeric(ordenado["id"], errors="coerce")
    else:
        ordenado["_id_ordem"] = pd.NA

    ordenado = ordenado.sort_values(
        by=["_data_ordem", "_id_ordem"],
        ascending=[False, False],
        na_position="last",
        kind="mergesort",
    )

    return ordenado.drop(columns=["_data_ordem", "_id_ordem"])


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
        elif k in ["fi", "f", "f_horario", "final", "finalizacao", "finalização"]:
            mapa[c] = "f_horario"
        elif k in ["tipo", "tipo_operacao"]:
            mapa[c] = "tipo"
        elif k in ["status"]:
            mapa[c] = "status"
        elif k in ["observacao", "observação", "observacoes", "observações", "obs", "o"]:
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


def normalizar_horario(v):
    s = texto(v)
    if not s or s in ["—", "-"]:
        return ""

    # FI deve receber apenas horário. Se vier status/texto, ignora.
    m = re.search(r"\b([0-2]?\d)[:hH]([0-5]\d)\b", s)
    if not m:
        return ""

    return f"{m.group(1).zfill(2)}:{m.group(2)}"


def normalizar_cliente_rapido(v):
    s_original = texto(v)
    s = s_original.upper()

    if not s:
        return ""

    s_limpo = limpar_busca(s)

    sufixo = ""
    if re.search(r"\bS\.?F\.?\b", s, flags=re.IGNORECASE):
        sufixo = " S.F"
    elif re.search(r"\bL\.?F\.?\b", s, flags=re.IGNORECASE):
        sufixo = " L.F"

    # remove S.F/L.F antes de corrigir o nome, depois recoloca no cliente
    s_sem_local = re.sub(r"\bS\.?F\.?\b", "", s, flags=re.IGNORECASE)
    s_sem_local = re.sub(r"\bL\.?F\.?\b", "", s_sem_local, flags=re.IGNORECASE).strip()
    s_limpo_sem_local = limpar_busca(s_sem_local)

    if "JDE" in s_sem_local:
        base = "JDE CAFÉ"
    elif "SC" in s_sem_local and ("DIST" in s_sem_local or "DISTRIB" in s_sem_local or "CAMACARI" in s_limpo_sem_local):
        base = "SC DIST. CAMAÇARI"
    elif "ATACADAO" in s_limpo_sem_local and ("CT" in s_sem_local or "SUL" in s_sem_local):
        base = "ATACADÃO CT SUL"
    elif "DROGARIA" in s_sem_local and "SAO PAULO" in s_limpo_sem_local:
        base = "DROGARIA SÃO PAULO"
    elif "RAIA" in s_sem_local or "DROGASIL" in s_sem_local:
        if "SALVADOR" in s_sem_local:
            base = "RAIA DROGASIL SALVADOR"
        else:
            base = "RAIA DROGASIL"
    elif "ASSAI" in s_limpo_sem_local:
        base = s_limpo_sem_local.replace("ASSAI", "ASSAÍ").strip()
    elif "WMS" in s_sem_local or "WMX" in s_sem_local or "ATAKADO" in s_sem_local:
        base = "WMS MAX ATACADO"
    else:
        base = s_sem_local.strip()

    return (base + sufixo).strip()


def normalizar_observacao(v):
    obs = texto(v)
    if not obs or obs in ["—", "-"]:
        return None

    obs_limpo = limpar_busca(obs)

    # Não salvar essas observações inúteis
    ignorar = [
        "HP",
        "ULTIMA OCORRENCIA",
        "ULTIMA OCORRÊNCIA",
        "EM ANDAMENTO",
        "FINALIZADO",
        "STATUS",
    ]
    if any(x in obs_limpo for x in ignorar):
        if not any(x in obs_limpo for x in ["DESLOC", "BLOQ", "CS", "C OK", "L OK", "MOTIVO", "NOK"]):
            return None

    # O só deve ser usado para deslocamento, bloqueio, motivo ou remessa
    permitido = ["DESLOC", "BLOQ", "CS", "C OK", "L OK", "MOTIVO", "NOK"]
    if not any(x in obs_limpo for x in permitido):
        return None

    return obs.upper().strip()


def montar_registro(row):
    delivery = texto(row.get("delivery", ""))
    sr = texto(row.get("sr", ""))

    if not delivery and not sr:
        return None

    registro = {
        "data": texto(row.get("data", "")) or None,
        "data_finalizacao": texto(row.get("data_finalizacao", "")) or None,
        "motorista": normalizar_motorista(row.get("motorista", "")) or None,
        "delivery": delivery or None,
        "sr": sr or None,
        "cliente": normalizar_cliente_rapido(row.get("cliente", "")) or None,
        "unidade": texto(row.get("unidade", "")) or None,
        "paletes": numero(row.get("paletes", "")),
        "valor_frete": numero(row.get("valor_frete", "")),
        "l_horario": normalizar_horario(row.get("l_horario", "")) or None,
        "c_horario": normalizar_horario(row.get("c_horario", "")) or None,
        "f_horario": normalizar_horario(row.get("f_horario", "")) or None,
        "tipo": texto(row.get("tipo", "")) or None,
        "status": texto(row.get("status", "")) or None,
        "observacoes": normalizar_observacao(row.get("observacoes", "")),
        "inconsistencias": texto(row.get("inconsistencias", "")) or None,
        "confianca": texto(row.get("confianca", "")) or None,
        "cpf": texto(row.get("cpf", "")) or None,
        "cavalo": texto(row.get("cavalo", "")) or None,
        "carreta": texto(row.get("carreta", "")) or None,
        "atualizado_em": datetime.now().isoformat(),
    }

    return completar_dados_motorista(registro)


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


def parse_atualizacao_rapida(linha):
    original = texto(linha)
    if not original:
        return None, "linha vazia"

    # REGRA NOVA:
    # Aceita FI no lugar de F.
    # Não aceita mais campo S.
    # S.F e L.F devem vir dentro do CL, não no O nem no FI.
    padrao = re.compile(r"\b(DATA|DF|SR|FI|CL|M|D|P|V|L|C|O)\b\s*:?\s*", re.IGNORECASE)
    matches = list(padrao.finditer(original))

    if not matches:
        return None, "nenhuma abreviação encontrada"

    dados = {}

    for i, m in enumerate(matches):
        chave = m.group(1).upper()
        inicio = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(original)
        valor = original[inicio:fim].strip(" :-")

        if chave and valor:
            dados[chave] = valor

    delivery = texto(dados.get("D", ""))
    sr = texto(dados.get("SR", ""))

    if not delivery and not sr:
        return None, "sem delivery ou SR"

    campos = {
        "atualizado_em": datetime.now().isoformat(),
    }

    if dados.get("DATA"):
        campos["data"] = texto(dados.get("DATA")) or None
    if dados.get("DF"):
        campos["data_finalizacao"] = texto(dados.get("DF")) or None
    if dados.get("M"):
        campos["motorista"] = normalizar_motorista(dados.get("M")) or None
    if delivery:
        campos["delivery"] = delivery
    if sr:
        campos["sr"] = sr
    if dados.get("CL"):
        campos["cliente"] = normalizar_cliente_rapido(dados.get("CL")) or None
    if dados.get("P"):
        campos["paletes"] = numero(dados.get("P"))
    if dados.get("V"):
        campos["valor_frete"] = numero(dados.get("V"))
    if dados.get("L"):
        campos["l_horario"] = normalizar_horario(dados.get("L")) or None
    if dados.get("C"):
        campos["c_horario"] = normalizar_horario(dados.get("C")) or None
    if dados.get("FI"):
        campos["f_horario"] = normalizar_horario(dados.get("FI")) or None

    obs = normalizar_observacao(dados.get("O", ""))
    if obs:
        campos["observacoes"] = obs

    if campos.get("observacoes"):
        obs_lower = campos["observacoes"].lower()
        if "desloc" in obs_lower or "bloq" in obs_lower or "nok" in obs_lower:
            # Deslocamento e bloqueio não devem preencher C.
            campos["c_horario"] = None

    campos = completar_dados_motorista(campos)

    chave_busca = "delivery" if delivery else "sr"
    valor_busca = delivery if delivery else sr

    return {
        "campos": campos,
        "chave_busca": chave_busca,
        "valor_busca": valor_busca,
    }, None


def atualizar_rapido_no_supabase(parsed):
    campos = parsed["campos"]
    chave = parsed["chave_busca"]
    valor = parsed["valor_busca"]

    existente = supabase.table("deliveries").select("id").eq(chave, valor).limit(1).execute()

    if existente.data:
        supabase.table("deliveries").update(campos).eq(chave, valor).execute()
        return "atualizado"

    supabase.table("deliveries").insert(campos).execute()
    return "criado"


def excel_bytes(df):
    out = BytesIO()

    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Mestre")

    return out.getvalue()


admin = autenticar_admin()

tab_busca, tab_rapida, tab_ler_folha, tab_importar, tab_admin = st.tabs(
    [
        "Buscar / visualizar",
        "Atualização rápida",
        "Ler folha",
        "Importar Excel mestre",
        "Administração",
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

    if not admin:
        st.info("Entre como administrador para editar ou excluir registros.")
        id_digitado = ""
    else:
        st.subheader("Editar / excluir")

        id_digitado = st.text_input("Digite o ID do registro para editar")

    if admin and id_digitado:
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
                    f_h = c12.text_input("FI", texto(item.get("f_horario")))

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
                            "cliente": normalizar_cliente_rapido(cliente) or None,
                            "unidade": unidade or None,
                            "paletes": numero(paletes),
                            "valor_frete": numero(valor),
                            "l_horario": normalizar_horario(l_h) or None,
                            "c_horario": normalizar_horario(c_h) or None,
                            "f_horario": normalizar_horario(f_h) or None,
                            "tipo": tipo or None,
                            "status": status or None,
                            "confianca": confianca or None,
                            "cpf": cpf or None,
                            "cavalo": cavalo or None,
                            "carreta": carreta or None,
                            "observacoes": normalizar_observacao(observacoes),
                            "inconsistencias": inconsistencias or None,
                            "atualizado_em": datetime.now().isoformat(),
                        }

                        registro = completar_dados_motorista(registro)

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


with tab_rapida:
    st.subheader("Atualização rápida")

    if not admin:
        st.warning("Apenas administradores podem usar a atualização rápida.")
    else:
        st.info(
            """
Use uma atualização por linha.

Abreviações:
M = Motorista
D = Delivery
SR = SR
CL = Cliente
P = Paletes
V = Valor do frete
L = Chegada
C = Coleta
FI = Finalização
O = Observação
DATA = Data
DF = Data finalização

O site completa automaticamente CPF, cavalo e carreta quando o motorista for:
Jean, Wilson, Luis, Gabriel, Jones, Fabio, Argemiro ou Valdemir.

Regras importantes:
- S.F e L.F ficam no CL, junto do cliente.
- FI recebe somente horário.
- Não usar campo S.
- O só deve ser usado para deslocamento, bloqueio, motivo ou remessa.
- Não usar O para HP, última ocorrência, finalizado ou em andamento.

Exemplos corretos:
M Jean D 3787760670 P 100 CL Atacadão CT Sul V 1021,05 L 08:51 C 10:51 FI —
M Jones D 3787780078 P 272 CL Drogaria São Paulo L.F V 992,17 L 07:33 C 09:59 FI —
M Fabio D 3787760662 P 200 CL Assaí Froes da Mota S.F V 1468,13 L 10:34 C 12:22 FI —
M Luis D 3402132015 P 476 CL JDE CAFÉ V 1276,13 O CS OK C OK L OK
D 3787762754 FI 11:03
"""
        )

        texto_rapido = st.text_area(
            "Digite uma ou mais atualizações",
            height=260,
            placeholder="D 3787762754 FI 11:03",
        )

        if st.button("Atualizar registros", type="primary"):
            linhas = [linha.strip() for linha in texto_rapido.splitlines() if linha.strip()]

            if not linhas:
                st.warning("Digite pelo menos uma atualização.")
            else:
                atualizados = 0
                criados = 0
                erros = []

                for idx, linha in enumerate(linhas, start=1):
                    try:
                        parsed, erro = parse_atualizacao_rapida(linha)

                        if erro:
                            erros.append(f"Linha {idx}: {erro} — {linha}")
                            continue

                        resultado = atualizar_rapido_no_supabase(parsed)

                        if resultado == "criado":
                            criados += 1
                        else:
                            atualizados += 1

                    except Exception as e:
                        erros.append(f"Linha {idx}: {e} — {linha}")

                if atualizados:
                    st.success(f"{atualizados} registro(s) atualizado(s).")
                if criados:
                    st.success(f"{criados} registro(s) criado(s).")
                if erros:
                    st.error("Algumas linhas não foram processadas:")
                    for erro in erros:
                        st.write(f"- {erro}")

                st.caption("Atualize a página ou volte na aba Buscar / editar para conferir os dados.")


with tab_ler_folha:
    st.subheader("Ler folha")

    if not admin:
        st.warning("Apenas administradores podem acessar a leitura de folha.")
    else:
        st.info(
            "Envie uma foto da folha operacional. O Gemini 2.5 Flash vai gerar "
            "uma prévia no formato da Atualização rápida, e o Supabase só será "
            "atualizado depois da sua confirmação."
        )

        arquivo_folha = st.file_uploader(
            "Enviar foto da folha operacional",
            type=["jpg", "jpeg", "png"],
            key="upload_ler_folha",
        )

        if st.button("Testar Gemini"):
            testar_gemini()

        if arquivo_folha:
            imagem_bytes, _, erro_imagem = validar_imagem_gemini(arquivo_folha)

            if erro_imagem:
                st.error(erro_imagem)
            else:
                st.image(imagem_bytes, caption="Imagem enviada", use_container_width=True)

        imagem_final_bytes = None
        imagem_final_mime = "image/png"

        if arquivo_folha and not erro_imagem:
            imagem_original = ImageOps.exif_transpose(Image.open(BytesIO(imagem_bytes))).convert("RGB")

            st.markdown("**Preparar imagem antes da leitura**")
            rotacao = st.radio(
                "Girar imagem",
                options=[0, 90, -90, 180],
                format_func=lambda valor: {
                    0: "Não girar",
                    90: "90° para esquerda",
                    -90: "90° para direita",
                    180: "180°",
                }[valor],
                horizontal=True,
                key="rotacao_ler_folha",
            )

            imagem_girada = imagem_original.rotate(rotacao, expand=True) if rotacao else imagem_original
            chave_corte = f"{arquivo_folha.name}_{arquivo_folha.size}_{rotacao}"
            chave_imagem_usada = f"imagem_cortada_ler_folha_{chave_corte}"

            st.caption(
                "Arraste uma caixa sobre a imagem para selecionar um corte. "
                "Se você não clicar em Usar imagem cortada, a imagem inteira girada será usada."
            )

            col_original, col_corte = st.columns(2)
            with col_original:
                st.image(imagem_girada, caption="Imagem original/girada", use_container_width=True)

            with col_corte:
                if ST_CROPPER_DISPONIVEL:
                    imagem_cortada_preview = st_cropper(
                        imagem_girada,
                        realtime_update=True,
                        box_color="#1f77b4",
                        aspect_ratio=None,
                        return_type="image",
                        key=f"cropper_ler_folha_{chave_corte}",
                    )
                else:
                    st.warning(
                        "O streamlit-cropper não está instalado neste ambiente. "
                        "Instale as dependências do requirements.txt para habilitar o corte por arrastar."
                    )
                    largura, altura = imagem_girada.size
                    x_inicio = st.slider("Corte esquerdo", 0, max(largura - 1, 0), 0)
                    y_inicio = st.slider("Corte superior", 0, max(altura - 1, 0), 0)
                    x_fim = st.slider("Corte direito", 1, largura, largura)
                    y_fim = st.slider("Corte inferior", 1, altura, altura)
                    imagem_cortada_preview = imagem_girada.crop((x_inicio, y_inicio, x_fim, y_fim))

                st.image(
                    imagem_cortada_preview,
                    caption="Imagem cortada (prévia)",
                    use_container_width=True,
                )

                if st.button("Usar imagem cortada", key=f"usar_imagem_cortada_{chave_corte}"):
                    buffer_corte = BytesIO()
                    imagem_cortada_preview.convert("RGB").save(buffer_corte, format="PNG")
                    st.session_state[chave_imagem_usada] = buffer_corte.getvalue()
                    st.success("Imagem cortada selecionada para a leitura.")

            if chave_imagem_usada in st.session_state:
                imagem_final_bytes = st.session_state[chave_imagem_usada]
                imagem_final = Image.open(BytesIO(imagem_final_bytes)).convert("RGB")
                legenda_final = "Imagem final cortada que será analisada pelo Gemini"
            else:
                imagem_final = imagem_girada
                buffer_imagem_final = BytesIO()
                imagem_final.save(buffer_imagem_final, format="PNG")
                imagem_final_bytes = buffer_imagem_final.getvalue()
                legenda_final = "Imagem final inteira que será analisada pelo Gemini"

            st.image(imagem_final, caption=legenda_final, use_container_width=True)

        imagem_pronta = imagem_final_bytes is not None

        if st.button("Ler com Gemini", disabled=not imagem_pronta):
            if not imagem_pronta:
                st.warning("Envie e prepare uma imagem antes de interpretar.")
            elif not texto(st.secrets.get("GEMINI_API_KEY", "")):
                st.error("Configure GEMINI_API_KEY em st.secrets para usar a leitura automática.")
            elif erro_imagem:
                st.error(erro_imagem)
            elif not st.session_state.get("gemini_teste_ok", False):
                st.warning("Clique em Testar Gemini e confirme que o teste simples funciona antes de ler a imagem.")
            else:
                with st.spinner("Interpretando a folha com Gemini 2.5 Flash..."):
                    try:
                        texto_interpretado, modelo_usado = interpretar_folha_com_gemini(
                            imagem_final_bytes,
                            imagem_final_mime,
                        )
                    except Exception as e:
                        mostrar_erro_gemini(e)
                    else:
                        st.session_state["previa_ler_folha"] = texto_interpretado
                        st.success(f"Folha interpretada com {modelo_usado}.")

        previa_ler_folha = st.text_area(
            "Prévia editável no formato da Atualização rápida",
            value=st.session_state.get("previa_ler_folha", ""),
            height=280,
            key="texto_ler_folha",
            placeholder="DATA 15/06/2026 M JEAN D 3787805566 P 117 CL ASSAÍ PARIPE V 1021,05 L 08:08 C 09:31 FI 13:44",
        )

        if st.button("Confirmar e atualizar", type="primary"):
            linhas = [linha.strip() for linha in previa_ler_folha.splitlines() if linha.strip()]

            if not linhas:
                st.warning("Não há linhas para atualizar.")
            else:
                criados = 0
                atualizados = 0
                erros = []

                for idx, linha in enumerate(linhas, start=1):
                    parsed, erro = parse_atualizacao_rapida(linha)

                    if erro:
                        erros.append(f"Linha {idx}: {erro} — {linha}")
                        continue

                    try:
                        resultado = atualizar_rapido_no_supabase(parsed)
                    except Exception as e:
                        erros.append(f"Linha {idx}: {e} — {linha}")
                        continue

                    if resultado == "criado":
                        criados += 1
                    else:
                        atualizados += 1

                st.success("Processamento concluído.")
                st.write(f"Registros criados: {criados}")
                st.write(f"Registros atualizados: {atualizados}")
                st.write(f"Linhas com erro: {len(erros)}")

                if erros:
                    st.error("Erros encontrados:")
                    for erro in erros:
                        st.write(f"- {erro}")


with tab_importar:
    st.subheader("Importar Excel mestre")

    if not admin:
        st.warning("Apenas administradores podem importar Excel.")
    else:
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


with tab_admin:
    st.subheader("Administração")

    if not admin:
        st.warning("Entre como administrador para acessar as funções administrativas.")
    else:
        df_atual = listar()

        st.write(f"Registros na nuvem: {len(df_atual)}")

        st.download_button(
            "⬇️ Baixar Excel mestre",
            data=excel_bytes(df_atual),
            file_name="excel_mestre_operacional.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.divider()
        st.subheader("Trocar ano das datas para 2026")
        st.caption("Atualiza somente os campos de data existentes, sem alterar a estrutura do banco e sem reorganizar IDs.")

        if st.button("Trocar ano das datas para 2026", type="primary"):
            total = atualizar_datas_para_2026()
            st.success(f"{total} registro(s) com datas ajustadas para 2026.")

        st.dataframe(df_atual, use_container_width=True, hide_index=True)
