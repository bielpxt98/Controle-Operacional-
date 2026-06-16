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
- Quando aparecer B(HORÁRIO) ou D(HORÁRIO) na folha manuscrita, converta para FI HORÁRIO e gere a observação correspondente: B significa BLOQUEIO e deve gerar O BLOQUEIO HORÁRIO; D significa DESLOCAMENTO e deve gerar O DESLOCAMENTO HORÁRIO.
- Se existir FI normal e também B(HORÁRIO) ou D(HORÁRIO), priorize o horário de B ou D no FI.
- O não deve ser usado para HP, última ocorrência, finalizado ou em andamento.
- Normalize nomes conhecidos quando possível: Jean, Wilson, Luis, Gabriel, Jones, Fabio, Argemiro ou Valdemir.

Regras para agrupamento por motorista:
- Quando aparecer "MOTORISTA: NOME VALOR", todas as coletas abaixo pertencem a esse motorista até aparecer outro "MOTORISTA:".
- Se o valor aparecer no cabeçalho do motorista, aplique esse mesmo valor em todas as coletas daquele bloco.
- Se o cabeçalho do motorista trouxer "VALOR x2", "VALORx2" ou "VALOR X 2", trate o valor como valor individual de cada coleta daquele bloco, não como valor total ou valor a dividir.
- Se houver várias coletas uma embaixo da outra sem repetir o motorista, mantenha o mesmo motorista e o mesmo valor do bloco.
- Para JEAN na imagem, as 4 coletas abaixo dele pertencem a JEAN e usam o valor 992,17.
- Para FABIO na imagem, as 2 coletas abaixo dele pertencem a FABIO e usam o valor 1468,13.
- Sempre devolva uma coleta por linha no formato da Atualização rápida.
- Não omita coletas. Se alguma informação estiver ilegível, coloque REVISAR no campo correspondente em vez de descartar a coleta.

Exemplo de agrupamento:
Entrada na folha:
MOTORISTA: FABIO 1468,13x2
D 3787803355 P 200 CL ASSAÍ TOMBA F.S L 10:50 C 12:40 FI 08:32 DF 16/06
D 3787807939 P 272 CL C. SEIS IRMÃOS L 12:23 O SEM ACESSO

Saída esperada:
M FABIO D 3787803355 P 200 CL ASSAÍ TOMBA F.S V 1468,13 L 10:50 C 12:40 FI 08:32 DF 16/06
M FABIO D 3787807939 P 272 CL C. SEIS IRMÃOS V 1468,13 L 12:23 O SEM ACESSO

Exemplo de saída:
DATA 15/06/2026 M JEAN D 3787805566 P 117 CL ASSAÍ PARIPE V 1021,05 L 08:08 C 09:31 FI 13:44

Exemplos de B/D manuscrito:
Entrada na folha:
3787805422 MERCANTIL L.F L(15:51) B(19:49)
Saída esperada:
M JEAN D 3787805422 CL MERCANTIL L.F V 992,17 L 15:51 FI 19:49 O BLOQUEIO 19:49

Entrada na folha:
3787807939 C SEIS IRMÃOS L(12:23) D(16:04)
Saída esperada:
M FABIO D 3787807939 CL C. SEIS IRMÃOS V 1468,13 L 12:23 FI 16:04 O DESLOCAMENTO 16:04
""".strip()




def redimensionar_imagem_para_cropper(imagem, largura_maxima=900):
    largura, altura = imagem.size

    if largura <= largura_maxima:
        return imagem.copy(), 1.0

    escala = largura_maxima / largura
    nova_altura = max(1, int(altura * escala))
    imagem_redimensionada = imagem.resize(
        (largura_maxima, nova_altura),
        Image.Resampling.LANCZOS,
    )

    return imagem_redimensionada, escala


def recortar_imagem_original_por_caixa(imagem_original, caixa_cropper, escala):
    if not caixa_cropper or escala <= 0:
        return imagem_original

    try:
        esquerda = int(caixa_cropper.get("left", 0) / escala)
        superior = int(caixa_cropper.get("top", 0) / escala)
        largura = int(caixa_cropper.get("width", imagem_original.width * escala) / escala)
        altura = int(caixa_cropper.get("height", imagem_original.height * escala) / escala)
    except (AttributeError, TypeError, ValueError):
        return imagem_original

    direita = esquerda + largura
    inferior = superior + altura

    esquerda = max(0, min(esquerda, imagem_original.width - 1))
    superior = max(0, min(superior, imagem_original.height - 1))
    direita = max(esquerda + 1, min(direita, imagem_original.width))
    inferior = max(superior + 1, min(inferior, imagem_original.height))

    return imagem_original.crop((esquerda, superior, direita, inferior))

def interpretar_folha_com_gemini(imagem_bytes, mime_type="image/png"):
    api_key = obter_gemini_api_key()

    if not api_key:
        raise ValueError("GEMINI_API_KEY não configurada em st.secrets.")

    regras = carregar_regras_operacionais()
    prompt = f"""
Leia a imagem da folha operacional e transforme TODOS os registros/coletas encontrados em texto para a Atualização rápida.

REGRAS OPERACIONAIS:
{regras}

REGRAS OBRIGATÓRIAS PARA A LEITURA DA FOLHA:
- Nunca resuma a folha.
- Nunca retorne apenas exemplos.
- Não omita nenhuma coleta identificada.
- Retorne uma linha separada para cada coleta encontrada na imagem.
- Se um bloco começa com "MOTORISTA:", todas as linhas abaixo pertencem ao mesmo motorista até aparecer outro "MOTORISTA:".
- Se o motorista possui um valor ao lado, por exemplo "JEAN 992,17", aplique esse valor em todas as coletas do bloco desse motorista.
- Se aparecer "1468,13x2", cada uma das 2 coletas do bloco deve receber o valor 1468,13.
- Se aparecer "992,17" e existirem 4 coletas abaixo, as 4 coletas devem receber 992,17.
- Quando aparecer B(HORÁRIO) ou D(HORÁRIO) na folha manuscrita, use esse HORÁRIO no campo FI e preencha O automaticamente: B(HORÁRIO) vira FI HORÁRIO O BLOQUEIO HORÁRIO; D(HORÁRIO) vira FI HORÁRIO O DESLOCAMENTO HORÁRIO.
- Se a mesma coleta tiver FI normal e também B(HORÁRIO) ou D(HORÁRIO), priorize B ou D para o FI e para a observação.
- Se alguma informação estiver ilegível, preencha o campo correspondente com REVISAR.
- Confira a imagem inteira antes de responder e inclua todas as linhas/coletas visíveis.

SAÍDA OBRIGATÓRIA:
Devolva somente as linhas no formato da Atualização rápida, sem explicações, cabeçalhos, Markdown ou exemplos.
""".strip()

    client = genai.Client(api_key=api_key)
    resposta, modelo_usado = consultar_gemini(
        client,
        contents=[
            prompt,
            types.Part.from_bytes(data=imagem_bytes, mime_type=mime_type),
        ],
    )

    return resposta.text if resposta.text is not None else "", modelo_usado

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


def extrair_regra_bloqueio_deslocamento(linha):
    original = texto(linha)
    if not original:
        return original, None, None

    padrao_bd = re.compile(
        r"(?<!\w)([BD])\s*\(\s*([0-2]?\d[:hH][0-5]\d)\s*\)",
        re.IGNORECASE,
    )
    ocorrencias = list(padrao_bd.finditer(original))
    if not ocorrencias:
        return original, None, None

    # Se houver mais de uma ocorrência manuscrita na mesma linha, a última tende a
    # ser a anotação operacional mais recente da coleta.
    marcador = ocorrencias[-1].group(1).upper()
    horario = normalizar_horario(ocorrencias[-1].group(2))
    tipo_observacao = "BLOQUEIO" if marcador == "B" else "DESLOCAMENTO"
    observacao = f"{tipo_observacao} {horario}" if horario else None

    linha_sem_marcadores = padrao_bd.sub(" ", original)
    return linha_sem_marcadores, horario or None, observacao


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

    original_parse, horario_bd, observacao_bd = extrair_regra_bloqueio_deslocamento(original)

    # REGRA NOVA:
    # Aceita FI no lugar de F.
    # Não aceita mais campo S.
    # S.F e L.F devem vir dentro do CL, não no O nem no FI.
    padrao = re.compile(r"\b(DATA|DF|SR|FI|CL|M|D|P|V|L|C|O)\b\s*:?\s*", re.IGNORECASE)
    matches = list(padrao.finditer(original_parse))

    if not matches:
        return None, "nenhuma abreviação encontrada"

    dados = {}

    for i, m in enumerate(matches):
        chave = m.group(1).upper()
        inicio = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(original_parse)
        valor = original_parse[inicio:fim].strip(" :-")

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
    if horario_bd:
        campos["f_horario"] = horario_bd

    obs = normalizar_observacao(dados.get("O", ""))
    if obs:
        campos["observacoes"] = obs
    if observacao_bd:
        campos["observacoes"] = observacao_bd

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




ACOES_CONVERSA = {
    "FINALIZACAO": ["FINALIZOU", "FINALIZADO", "FINAL", "FI", "F"],
    "BLOQUEIO": ["BLOQUEIO", "BLOQUEADO", "B"],
    "DESLOCAMENTO": ["DESLOCAMENTO", "DESLOCOU", "D"],
}


def parse_atualizacao_conversa(frase):
    original = texto(frase)
    if not original:
        return None, "Digite uma frase para interpretar."

    horario_match = re.search(r"\b([0-2]?\d[:hH][0-5]\d)\b", original)
    horario = normalizar_horario(horario_match.group(1)) if horario_match else ""
    if not horario:
        return None, "Não encontrei horário no formato HH:MM."

    motorista = ""
    for nome in MOTORISTAS_FIXOS:
        primeiro_nome = nome.split()[0]
        if re.search(rf"\b{re.escape(primeiro_nome)}\b", limpar_busca(original)):
            motorista = nome
            break

    if not motorista:
        motorista_normalizado = normalizar_motorista(original)
        if motorista_normalizado in MOTORISTAS_FIXOS:
            motorista = motorista_normalizado

    if not motorista:
        return None, "Não encontrei o motorista na frase."

    acao = ""
    texto_limpo = limpar_busca(original)
    for acao_candidata, aliases in ACOES_CONVERSA.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", texto_limpo) for alias in aliases):
            acao = acao_candidata
            break

    if not acao:
        return None, "Não encontrei ação válida: finalizou, bloqueio ou deslocamento."

    numeros = re.findall(r"\b\d{4,}\b", original)
    final_delivery = numeros[-1] if numeros else ""
    if not final_delivery:
        return None, "Não encontrei final do delivery com 4 ou mais números."

    texto_cliente = re.sub(r"\b[0-2]?\d[:hH][0-5]\d\b", " ", original)
    texto_cliente = re.sub(r"\b\d{4,}\b", " ", texto_cliente)

    palavras_remover = {
        "A", "AS", "ÀS", "O", "OS", "DE", "DO", "DA", "DOS", "DAS", "EM", "NO", "NA",
        "NOS", "NAS", "AO", "AOS", "ATE", "ATÉ",
    }
    palavras_remover.update(limpar_busca(motorista).split())
    for aliases in ACOES_CONVERSA.values():
        palavras_remover.update(aliases)

    palavras_cliente = [
        palavra
        for palavra in re.findall(r"[\wÀ-ÿ.]+", texto_cliente, flags=re.UNICODE)
        if limpar_busca(palavra) not in palavras_remover
    ]
    cliente = normalizar_cliente_rapido(" ".join(palavras_cliente))

    if not cliente:
        return None, "Não encontrei cliente na frase."

    observacoes = None
    if acao == "BLOQUEIO":
        observacoes = f"BLOQUEIO {horario}"
    elif acao == "DESLOCAMENTO":
        observacoes = f"DESLOCAMENTO {horario}"

    return {
        "motorista": motorista,
        "horario": horario,
        "final_delivery": final_delivery,
        "cliente": cliente,
        "acao": acao,
        "observacoes": observacoes,
    }, None


def cliente_combina(cliente_registro, cliente_busca):
    registro = limpar_busca(cliente_registro)
    busca = limpar_busca(cliente_busca)

    if not busca:
        return True
    if busca in registro or registro in busca:
        return True

    palavras = [p for p in busca.split() if len(p) > 1]
    if not palavras:
        return False

    return all(p in registro for p in palavras)


def buscar_coletas_por_conversa(df_base, parsed):
    if df_base.empty:
        return pd.DataFrame()

    resultado = df_base.copy()
    for coluna in ["motorista", "delivery", "cliente", "f_horario"]:
        if coluna not in resultado.columns:
            resultado[coluna] = ""

    resultado = resultado[
        resultado["motorista"].apply(lambda v: normalizar_motorista(v) == parsed["motorista"])
        & resultado["delivery"].apply(
            lambda v: re.sub(r"\D", "", texto(v)).endswith(parsed["final_delivery"])
        )
        & resultado["cliente"].apply(lambda v: cliente_combina(v, parsed["cliente"]))
    ].copy()

    if resultado.empty:
        return resultado

    resultado["_sem_fi"] = resultado["f_horario"].apply(lambda v: not bool(texto(v)))
    resultado = resultado.sort_values("_sem_fi", ascending=False, kind="mergesort")
    return resultado.drop(columns=["_sem_fi"])


def campos_atualizacao_conversa(parsed):
    campos = {
        "f_horario": parsed["horario"],
        "atualizado_em": datetime.now().isoformat(),
    }
    if parsed.get("observacoes"):
        campos["observacoes"] = parsed["observacoes"]
    return campos


def atualizar_conversa_no_supabase(id_registro, parsed):
    supabase.table("deliveries").update(campos_atualizacao_conversa(parsed)).eq(
        "id",
        int(id_registro),
    ).execute()


def excel_bytes(df):
    out = BytesIO()

    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Mestre")

    return out.getvalue()


admin = autenticar_admin()

tab_busca, tab_rapida, tab_conversa, tab_ler_folha, tab_importar, tab_admin = st.tabs(
    [
        "Buscar / visualizar",
        "Atualização rápida",
        "Atualização por conversa",
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
- B(HORÁRIO) na folha manuscrita vira FI HORÁRIO e O BLOQUEIO HORÁRIO.
- D(HORÁRIO) na folha manuscrita vira FI HORÁRIO e O DESLOCAMENTO HORÁRIO.
- Se existir FI normal e também B(HORÁRIO) ou D(HORÁRIO), B/D tem prioridade.
- Não usar campo S.
- O só deve ser usado para deslocamento, bloqueio, motivo ou remessa.
- Não usar O para HP, última ocorrência, finalizado ou em andamento.

Exemplos corretos:
M Jean D 3787760670 P 100 CL Atacadão CT Sul V 1021,05 L 08:51 C 10:51 FI —
M Jones D 3787780078 P 272 CL Drogaria São Paulo L.F V 992,17 L 07:33 C 09:59 FI —
M Fabio D 3787760662 P 200 CL Assaí Froes da Mota S.F V 1468,13 L 10:34 C 12:22 FI —
M Luis D 3402132015 P 476 CL JDE CAFÉ V 1276,13 O CS OK C OK L OK
D 3787762754 FI 11:03
M Jean D 3787805422 CL Mercantil L.F V 992,17 L 15:51 B(19:49)
M Fabio D 3787807939 CL C. Seis Irmãos V 1468,13 L 12:23 D(16:04)
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


with tab_conversa:
    st.subheader("Atualização por conversa")

    if not admin:
        st.warning("Apenas administradores podem usar a atualização por conversa.")
    else:
        st.info(
            "Digite uma frase natural. A interpretação usa somente regras locais "
            "e a atualização só acontece depois da confirmação."
        )
        frase_conversa = st.text_input(
            "Frase da atualização",
            placeholder="Jean finalizou 5422 mercantil às 19:49",
        )

        if st.button("Buscar coleta", type="primary"):
            parsed, erro = parse_atualizacao_conversa(frase_conversa)
            st.session_state.pop("conversa_parsed", None)
            st.session_state.pop("conversa_resultados", None)

            if erro:
                st.error(erro)
            else:
                resultados = buscar_coletas_por_conversa(df, parsed)
                if resultados.empty:
                    st.warning(
                        "Nenhuma coleta encontrada. Informe mais detalhes, como final do delivery, cliente ou data."
                    )
                else:
                    st.session_state["conversa_parsed"] = parsed
                    st.session_state["conversa_resultados"] = resultados.to_dict("records")

        parsed_conversa = st.session_state.get("conversa_parsed")
        resultados_conversa = st.session_state.get("conversa_resultados") or []

        if parsed_conversa and resultados_conversa:
            st.write(
                f"**Interpretação:** motorista {parsed_conversa['motorista']}, "
                f"delivery final {parsed_conversa['final_delivery']}, "
                f"cliente {parsed_conversa['cliente']}, FI {parsed_conversa['horario']}."
            )

            if len(resultados_conversa) == 1:
                item = resultados_conversa[0]
                st.code(f"D {texto(item.get('delivery'))} FI {parsed_conversa['horario']}")
                if parsed_conversa.get("observacoes"):
                    st.caption(f"Observações: {parsed_conversa['observacoes']}")

                if st.button("Confirmar atualização", key="confirmar_conversa_unica"):
                    atualizar_conversa_no_supabase(item["id"], parsed_conversa)
                    st.success("Coleta atualizada.")
                    st.session_state.pop("conversa_parsed", None)
                    st.session_state.pop("conversa_resultados", None)
                    st.rerun()
            else:
                opcoes = {
                    f"ID {texto(item.get('id'))} | {texto(item.get('data'))} | {texto(item.get('motorista'))} | "
                    f"D {texto(item.get('delivery'))} | {texto(item.get('cliente'))} | "
                    f"L {texto(item.get('l_horario'))} | C {texto(item.get('c_horario'))} | FI {texto(item.get('f_horario'))}": item["id"]
                    for item in resultados_conversa
                }
                st.dataframe(
                    pd.DataFrame(resultados_conversa)[
                        [col for col in ["id", "data", "motorista", "delivery", "cliente", "l_horario", "c_horario", "f_horario"] if col in pd.DataFrame(resultados_conversa).columns]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                escolha = st.selectbox("Selecione a coleta para atualizar", list(opcoes.keys()))
                st.code(f"FI {parsed_conversa['horario']}")
                if parsed_conversa.get("observacoes"):
                    st.caption(f"Observações: {parsed_conversa['observacoes']}")

                if st.button("Confirmar atualização", key="confirmar_conversa_multipla"):
                    atualizar_conversa_no_supabase(opcoes[escolha], parsed_conversa)
                    st.success("Coleta atualizada.")
                    st.session_state.pop("conversa_parsed", None)
                    st.session_state.pop("conversa_resultados", None)
                    st.rerun()


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
                "Primeiro confira a imagem completa abaixo. Depois, se precisar, "
                "arraste uma caixa no cropper. A imagem é reduzida apenas para caber "
                "na tela; o corte enviado ao Gemini é feito na resolução original."
            )

            st.image(
                imagem_girada,
                caption="Imagem original completa",
                use_container_width=True,
            )

            imagem_cropper, escala_cropper = redimensionar_imagem_para_cropper(
                imagem_girada,
                largura_maxima=900,
            )

            st.markdown("**Cropper (imagem completa visível, sem zoom automático)**")
            st.caption(
                f"Imagem no cropper: {imagem_cropper.width} × {imagem_cropper.height} px. "
                f"Imagem original: {imagem_girada.width} × {imagem_girada.height} px."
            )

            if ST_CROPPER_DISPONIVEL:
                caixa_cropper = st_cropper(
                    imagem_cropper,
                    realtime_update=True,
                    box_color="#1f77b4",
                    aspect_ratio=None,
                    return_type="box",
                    key=f"cropper_ler_folha_{chave_corte}",
                )
                imagem_cortada_preview = recortar_imagem_original_por_caixa(
                    imagem_girada,
                    caixa_cropper,
                    escala_cropper,
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
                caption="Imagem cortada (prévia em boa resolução)",
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
                        st.session_state["resposta_original_gemini_ler_folha"] = texto_interpretado
                        st.session_state["previa_ler_folha"] = texto_interpretado
                        st.success(f"Folha interpretada com {modelo_usado}.")

        resposta_original_gemini = st.session_state.get("resposta_original_gemini_ler_folha", "")
        if resposta_original_gemini:
            with st.expander("Resposta original do Gemini"):
                st.code(resposta_original_gemini, language="text")

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
