import base64
import hashlib
import hmac
import importlib
import json
import logging
import re
import secrets
import time
import traceback
from html import escape
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from PIL import Image, ImageOps
from datetime import datetime, timedelta
from supabase import create_client
from google import genai
from google.genai import types
from perguntas import responder_pergunta_df


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ST_CROPPER_DISPONIVEL = importlib.util.find_spec("streamlit_cropper") is not None
ST_COOKIES_DISPONIVEL = importlib.util.find_spec("extra_streamlit_components") is not None
st_cropper = (
    importlib.import_module("streamlit_cropper").st_cropper
    if ST_CROPPER_DISPONIVEL
    else None
)
stx = importlib.import_module("extra_streamlit_components") if ST_COOKIES_DISPONIVEL else None

LOGO_PATH = Path(__file__).resolve().parent / "logo.png"
LOGO_IMAGEM = Image.open(LOGO_PATH)
LOGO_DATA_URI = f"data:image/png;base64,{base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii')}"

st.set_page_config(page_title="Controle Operacional", page_icon=LOGO_IMAGEM, layout="wide")

SUPABASE_URL = "https://zkqzejnflpzknuuirlav.supabase.co"
SUPABASE_KEY = "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


PERGUNTAS_PROGRAMADAS = [
    "Quantas coletas JEAN teve hoje?",
    "Quantas coletas JEAN teve este mês?",
    "Quantas coletas cada motorista teve este mês?",
    "Quais coletas estão sem FI?",
    "Quais coletas estão sem C?",
    "Quais coletas tiveram bloqueio?",
    "Quais coletas tiveram deslocamento?",
    "Quantas remessas tiveram no mês?",
    "Qual valor total por motorista no mês?",
    "Qual motorista teve mais coletas?",
    "Quantos SR teve hoje?",
    "Quantos SR teve este mês?",
    "Quantos deslocamentos por motorista?",
    "Quantos deslocamentos por motivo?",
    "Quantos bloqueios por motorista?",
    "Quantos bloqueios por motivo?",
]


MOTORISTAS_FIXOS = {
    "WILSON REIS": {"cpf": "806.984.765-49", "cavalo": "JJF1856", "carreta": "NVQ8447"},
    "FABIO SOUZA": {"cpf": "007.714.335-30", "cavalo": "PEL4695", "carreta": "NLB7814"},
    "LUIS CARLOS": {"cpf": "934.560.345-04", "cavalo": "KLB5018", "carreta": "NKZ6545"},
    "ARGEMIRO BORGES": {"cpf": "041.604.865-09", "cavalo": "PEG7666", "carreta": "DTD8506"},
    "JEAN ROBSON": {"cpf": "032.795.865-00", "cavalo": "HWB9F22", "carreta": "TRUCK"},
    "JONES ROSARIO": {"cpf": "538.594.654-00", "cavalo": "JHX3C33", "carreta": "KKT9007"},
    "GABRIEL BORGES": {"cpf": "809.066.155-87", "cavalo": "KJV8204", "carreta": "KG61152"},
    "VALDEMIR DE JESUS": {"cpf": "044.327.095-37", "cavalo": "KFL0115", "carreta": "TRUCK"},
    "ARIEL NASCIMENTO": {"cpf": "050.153.565-95", "cavalo": "JVL8A44", "carreta": "TRUCK"},
}

MAPA_MOTORISTAS_ANTIGOS = {
    "JEAN": "JEAN ROBSON",
    "FABIO": "FABIO SOUZA",
    "JONES": "JONES ROSARIO",
    "LUIS": "LUIS CARLOS",
    "ARIEL": "ARIEL NASCIMENTO",
    "ARGEMIRO": "ARGEMIRO BORGES",
    "WILSON": "WILSON REIS",
    "GABRIEL": "GABRIEL BORGES",
}


def texto(v):
    if v is None or pd.isna(v):
        return ""
    if str(v).strip().lower() in ["", "nan", "none", "null", "<na>"]:
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
    mapa_motoristas_antigos = globals().get("MAPA_MOTORISTAS_ANTIGOS", {
        "JEAN": "JEAN ROBSON",
        "FABIO": "FABIO SOUZA",
        "JONES": "JONES ROSARIO",
        "LUIS": "LUIS CARLOS",
        "ARIEL": "ARIEL NASCIMENTO",
        "ARGEMIRO": "ARGEMIRO BORGES",
        "WILSON": "WILSON REIS",
        "GABRIEL": "GABRIEL BORGES",
    })

    if n in mapa_motoristas_antigos:
        return mapa_motoristas_antigos[n]
    if n == "VALDEMIR":
        return "VALDEMIR DE JESUS"

    return texto(v).upper()



def normalizar_motorista_antigo_sem_sobrenome(v):
    nome = limpar_busca(v)
    return MAPA_MOTORISTAS_ANTIGOS.get(nome)


def preview_padronizacao_motoristas(df_base):
    if df_base.empty or "motorista" not in df_base.columns:
        return pd.DataFrame(columns=["id", "antes", "depois", "delivery", "cliente", "data"])

    registros = []

    for _, row in df_base.iterrows():
        antes = texto(row.get("motorista"))
        depois = normalizar_motorista_antigo_sem_sobrenome(antes)

        if not depois or limpar_busca(antes) == limpar_busca(depois):
            continue

        registros.append({
            "id": row.get("id"),
            "antes": antes,
            "depois": depois,
            "delivery": row.get("delivery", ""),
            "cliente": row.get("cliente", ""),
            "data": row.get("data", ""),
        })

    return pd.DataFrame(registros)


def aplicar_padronizacao_motoristas(df_preview):
    total = 0

    if df_preview.empty:
        return total

    for _, row in df_preview.iterrows():
        id_registro = row.get("id")
        novo_motorista = texto(row.get("depois"))

        if pd.isna(id_registro) or not novo_motorista:
            continue

        atualizacao = {
            "motorista": novo_motorista,
            "atualizado_em": datetime.now().isoformat(),
        }
        atualizacao = completar_dados_motorista(atualizacao)

        supabase.table("deliveries").update(atualizacao).eq("id", int(id_registro)).execute()
        total += 1

    return total


def calcular_status_automatico(observacoes, f_horario=None):
    """Calcula STATUS pela prioridade oficial: O, BLOQUEIO, FI e EM ABERTO."""
    obs = limpar_busca(observacoes)

    if "DESLOC" in obs:
        return "DESLOCAMENTO"
    if re.search(r"\bBLOQ(?:UEIO)?\b", obs):
        return "BLOQUEIO"
    if texto(f_horario):
        return "FINALIZADO"
    return "EM ABERTO"


def preview_atualizacao_status(df_base):
    colunas = ["id", "status_atual", "status_novo", "delivery", "cliente", "f_horario", "observacoes"]
    if df_base.empty:
        return pd.DataFrame(columns=colunas)

    registros = []
    for _, row in df_base.iterrows():
        novo_status = calcular_status_automatico(row.get("observacoes", ""), row.get("f_horario", ""))
        registros.append({
            "id": row.get("id"),
            "status_atual": texto(row.get("status")),
            "status_novo": novo_status,
            "delivery": row.get("delivery", ""),
            "cliente": row.get("cliente", ""),
            "f_horario": row.get("f_horario", ""),
            "observacoes": row.get("observacoes", ""),
        })

    return pd.DataFrame(registros, columns=colunas)


def resumo_preview_status(df_preview):
    status_possiveis = ["DESLOCAMENTO", "BLOQUEIO", "FINALIZADO", "EM ABERTO"]
    contagem = df_preview["status_novo"].value_counts() if not df_preview.empty else pd.Series(dtype=int)
    return {status: int(contagem.get(status, 0)) for status in status_possiveis}


def aplicar_atualizacao_status(df_preview):
    total = 0
    if df_preview.empty:
        return total

    for _, row in df_preview.iterrows():
        id_registro = row.get("id")
        novo_status = texto(row.get("status_novo"))
        if pd.isna(id_registro) or not novo_status:
            continue

        supabase.table("deliveries").update({
            "status": novo_status,
            "atualizado_em": datetime.now().isoformat(),
        }).eq("id", int(id_registro)).execute()
        total += 1

    return total

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


def obter_gemini_api_keys():
    chaves = []

    for nome, rotulo in [
        ("GEMINI_API_KEY", "API 1 usada"),
        ("GEMINI_API_KEY_2", "API 2 usada"),
    ]:
        try:
            api_key = texto(st.secrets[nome])
        except Exception:
            api_key = ""

        if api_key:
            chaves.append({"api_key": api_key, "rotulo": rotulo})

    return chaves


def obter_gemini_api_key():
    chaves = obter_gemini_api_keys()
    return chaves[0]["api_key"] if chaves else ""


def erro_limite_gemini(erro):
    texto_erro = f"{type(erro).__name__} {repr(erro)}".lower()
    termos_limite = [
        "limite",
        "quota",
        "429",
        "resource exhausted",
        "rate limit",
        "ratelimit",
        "too many requests",
    ]
    return any(termo in texto_erro for termo in termos_limite)


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
    modelo = "gemini-2.5-flash"
    resposta = client.models.generate_content(model=modelo, **kwargs)
    return resposta, modelo


def consultar_gemini_com_fallback(**kwargs):
    chaves = obter_gemini_api_keys()

    if not chaves:
        raise ValueError("Configure GEMINI_API_KEY ou GEMINI_API_KEY_2 em st.secrets.")

    erros = []

    for indice, chave in enumerate(chaves):
        try:
            client = genai.Client(api_key=chave["api_key"])
            resposta, modelo_usado = consultar_gemini(client, **kwargs)
            return resposta, modelo_usado, chave["rotulo"]
        except Exception as e:
            erros.append((chave["rotulo"], e))
            primeira_chave = indice == 0
            existe_proxima_chave = indice + 1 < len(chaves)

            if primeira_chave and existe_proxima_chave and erro_limite_gemini(e):
                continue

            if len(erros) > 1:
                break

            raise

    detalhes = "; ".join(f"{rotulo}: {repr(erro)}" for rotulo, erro in erros)
    raise RuntimeError(f"As APIs Gemini configuradas falharam. {detalhes}")


def mostrar_erro_gemini(erro):
    st.error(
        "Não foi possível consultar o Gemini agora. "
        "Verifique se as APIs estão configuradas, aguarde se houver limite de uso "
        "e tente novamente."
    )

    with st.expander("Detalhes do erro"):
        st.code(repr(erro))


def testar_gemini():
    try:
        resposta, _, api_usada = consultar_gemini_com_fallback(
            contents="Responda apenas OK",
        )
    except Exception as e:
        mostrar_erro_gemini(e)
        return False

    st.success(f"Teste Gemini concluído. {api_usada}.")
    st.write(texto(resposta.text))
    st.session_state["gemini_teste_ok"] = True
    return True

def senha_admin_configurada():
    try:
        return bool(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        return False


SESSAO_ADMIN_COOKIE = "controle_operacional_admin_session"
SESSAO_ADMIN_USUARIO = "ADMIN"
SESSAO_ADMIN_TTL_SEGUNDOS = 60 * 60


@st.cache_resource(show_spinner=False)
def gerenciador_cookies():
    if not ST_COOKIES_DISPONIVEL:
        return None
    return stx.CookieManager()


def chave_assinatura_sessao():
    senha = texto(st.secrets.get("ADMIN_PASSWORD", "")) if senha_admin_configurada() else ""
    base = senha or SUPABASE_KEY
    return hashlib.sha256(base.encode("utf-8")).digest()


def assinar_payload_sessao(payload):
    dados = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(chave_assinatura_sessao(), dados, hashlib.sha256).hexdigest()


def codificar_payload_sessao(payload):
    dados = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def decodificar_payload_sessao(dados):
    padding = "=" * (-len(dados) % 4)
    return json.loads(base64.urlsafe_b64decode((dados + padding).encode("ascii")).decode("utf-8"))


def criar_token_sessao_admin(usuario=SESSAO_ADMIN_USUARIO):
    agora = int(time.time())
    payload = {
        "usuario": usuario,
        "iat": agora,
        "last_activity": agora,
        "nonce": secrets.token_urlsafe(16),
    }
    corpo = codificar_payload_sessao(payload)
    return f"{corpo}.{assinar_payload_sessao(payload)}"


def validar_token_sessao_admin(token):
    if not token or "." not in token:
        return False, None
    try:
        corpo, assinatura = token.rsplit(".", 1)
        payload = decodificar_payload_sessao(corpo)
        assinatura_esperada = assinar_payload_sessao(payload)
    except Exception:
        return False, None
    if not hmac.compare_digest(assinatura, assinatura_esperada):
        return False, None
    ultima_atividade = int(payload.get("last_activity", 0))
    if int(time.time()) - ultima_atividade > SESSAO_ADMIN_TTL_SEGUNDOS:
        return False, None
    return True, payload


def renovar_token_sessao_admin(token):
    valido, payload = validar_token_sessao_admin(token)
    if not valido:
        return None
    payload["last_activity"] = int(time.time())
    corpo = codificar_payload_sessao(payload)
    return f"{corpo}.{assinar_payload_sessao(payload)}"


def salvar_cookie_sessao(token):
    cookies = gerenciador_cookies()
    if not cookies:
        return
    cookies.set(
        SESSAO_ADMIN_COOKIE,
        token,
        expires_at=datetime.now() + timedelta(seconds=SESSAO_ADMIN_TTL_SEGUNDOS),
        key="salvar_sessao_admin",
    )


def remover_cookie_sessao():
    cookies = gerenciador_cookies()
    if not cookies:
        return
    cookies.delete(SESSAO_ADMIN_COOKIE, key="remover_sessao_admin")


def recuperar_sessao_persistente_admin():
    cookies = gerenciador_cookies()
    if not cookies:
        return False, None
    token = cookies.get(SESSAO_ADMIN_COOKIE)
    valido, payload = validar_token_sessao_admin(token)
    if not valido:
        if token:
            remover_cookie_sessao()
        return False, None
    token_renovado = renovar_token_sessao_admin(token)
    salvar_cookie_sessao(token_renovado)
    return True, payload


def modal_login_admin():
    @st.dialog("Acesso administrativo")
    def exibir_modal():
        st.markdown("**Senha administrativa**")

        if not senha_admin_configurada():
            st.warning("Configure ADMIN_PASSWORD em st.secrets para liberar o modo administrador.")
            if st.button("Cancelar", key="admin_modal_cancelar_sem_senha"):
                st.session_state.admin_login_modal_aberto = False
                st.rerun()
            return

        with st.form("admin_login_form", clear_on_submit=True):
            senha = st.text_input("Senha administrativa", type="password", label_visibility="collapsed")
            col_entrar, col_cancelar = st.columns(2)
            entrar = col_entrar.form_submit_button("Entrar", type="primary", use_container_width=True)
            cancelar = col_cancelar.form_submit_button("Cancelar", use_container_width=True)

        if cancelar:
            st.session_state.admin_login_modal_aberto = False
            st.rerun()

        if entrar:
            if senha == st.secrets["ADMIN_PASSWORD"]:
                token = criar_token_sessao_admin()
                salvar_cookie_sessao(token)
                st.session_state.admin_autenticado = True
                st.session_state.admin_usuario = SESSAO_ADMIN_USUARIO
                st.session_state.admin_token = token
                st.session_state.admin_login_modal_aberto = False
                st.session_state.admin_menu_aberto = False
                st.rerun()
            else:
                st.error("Senha administrativa inválida.")

    exibir_modal()


def autenticar_admin():
    if "admin_autenticado" not in st.session_state:
        st.session_state.admin_autenticado = False
    if "admin_usuario" not in st.session_state:
        st.session_state.admin_usuario = ""
    if "admin_login_modal_aberto" not in st.session_state:
        st.session_state.admin_login_modal_aberto = False
    if "admin_menu_aberto" not in st.session_state:
        st.session_state.admin_menu_aberto = False

    sessao_valida, payload = recuperar_sessao_persistente_admin()
    if sessao_valida:
        st.session_state.admin_autenticado = True
        st.session_state.admin_usuario = payload.get("usuario", SESSAO_ADMIN_USUARIO)
    elif st.session_state.admin_autenticado:
        st.session_state.admin_autenticado = False
        st.session_state.admin_usuario = ""

    with st.sidebar:
        st.markdown('<div class="sidebar-auth-anchor">', unsafe_allow_html=True)

        if st.session_state.admin_autenticado:
            if st.button("👤", key="admin_status_toggle", help="Administrador autenticado", use_container_width=False):
                st.session_state.admin_menu_aberto = not st.session_state.admin_menu_aberto

            if st.session_state.admin_menu_aberto:
                st.markdown(
                    f'<div class="admin-status-card"><strong>{escape(st.session_state.admin_usuario)} autenticado</strong><br><small>Sessão renovada com atividade.</small></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Sair do modo administrador", key="admin_logout", use_container_width=True):
                    remover_cookie_sessao()
                    st.session_state.admin_autenticado = False
                    st.session_state.admin_usuario = ""
                    st.session_state.admin_token = ""
                    st.session_state.admin_menu_aberto = False
                    st.rerun()
        else:
            if not ST_COOKIES_DISPONIVEL:
                st.caption("Sessão persistente indisponível: instale extra-streamlit-components.")
            if st.button("🔒", key="admin_login_toggle", help="Entrar como administrador", use_container_width=False):
                st.session_state.admin_login_modal_aberto = True

        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.admin_login_modal_aberto and not st.session_state.admin_autenticado:
        modal_login_admin()

    return st.session_state.admin_autenticado



REGRAS_OPERACIONAIS_PATH = Path(__file__).resolve().parent / "REGRAS_OPERACIONAIS.md"
REGRAS_OPERACIONAIS_HISTORICO_PATH = Path(__file__).resolve().parent / "REGRAS_OPERACIONAIS_HISTORICO.csv"

REGRAS_OPERACIONAIS_INICIAIS = """
REGRAS OPERACIONAIS

FORMATAÇÃO

* TODAS AS INFORMAÇÕES DEVEM SER RETORNADAS EM MAIÚSCULAS.
* UMA COLETA POR LINHA.
* NUNCA ALTERAR NÚMEROS INFORMADOS.
* NUNCA INVENTAR INFORMAÇÕES.
* NUNCA RESUMIR OU CORTAR NOMES DE CLIENTES.
* O NOME DO CLIENTE DEVE SER COPIADO EXATAMENTE COMO ESTÁ ESCRITO NA FOLHA.
* SOMENTE ALTERAR O NOME DE UM CLIENTE QUANDO O USUÁRIO INFORMAR EXPLICITAMENTE UMA REGRA DE SUBSTITUIÇÃO.

FORMATO PADRÃO

DATA DD/MM/AAAA M MOTORISTA D DELIVERY/REMESSA P PALLETS CL CLIENTE V VALOR L HH:MM C HH:MM FI HH:MM O OBSERVAÇÃO

CAMPOS

DATA = DATA DA OPERAÇÃO

M = MOTORISTA

D = DELIVERY OU REMESSA

* DELIVERIES NORMALMENTE INICIAM COM 378
* REMESSAS NORMALMENTE INICIAM COM 340

P = QUANTIDADE DE PALLETS

CL = CLIENTE

V = VALOR

L = HORÁRIO DE CHEGADA

C = HORÁRIO DE COLETA

FI = HORÁRIO DE FINALIZAÇÃO

O = OBSERVAÇÃO

REGRAS DE DESLOCAMENTO

QUANDO EXISTIR:

D(HH:MM)

CONVERTER PARA:

FI HH:MM
O DESLOCAMENTO AS HH:MM

EXEMPLO:

D(11:53)

RETORNO:

FI 11:53
O DESLOCAMENTO AS 11:53

REGRAS DE BLOQUEIO

QUANDO EXISTIR:

B(HH:MM)

CONVERTER PARA:

FI HH:MM
O BLOQUEIO AS HH:MM

EXEMPLO:

B(16:20)

RETORNO:

FI 16:20
O BLOQUEIO AS 16:20

OBSERVAÇÕES

TODA FRASE OU ANOTAÇÃO QUE NÃO REPRESENTE:

L
C
FI
B
D

DEVE SER INSERIDA EM O.

EXEMPLOS:

O MOTORISTA TERCEIRIZADO
O SEM AGENDAMENTO
O CS OK
O AGUARDANDO DESCARGA

REMESSAS

REMESSAS PODEM POSSUIR APENAS FI E OBSERVAÇÕES.

ATUALIZAÇÕES

QUANDO O USUÁRIO ENVIAR UMA ATUALIZAÇÃO DE UMA COLETA JÁ EXISTENTE, RETORNAR APENAS OS DADOS QUE FORAM ALTERADOS.

EXEMPLO:

JEAN FINALIZOU ASSAI PARIPE AS 13:44

RETORNO:

D 378XXXXXXX FI 13:44

NUNCA REPETIR TODA A LINHA QUANDO A SOLICITAÇÃO FOR APENAS UMA ATUALIZAÇÃO.
""".strip()


def carregar_regras_operacionais():
    if not REGRAS_OPERACIONAIS_PATH.exists():
        REGRAS_OPERACIONAIS_PATH.write_text(REGRAS_OPERACIONAIS_INICIAIS, encoding="utf-8")
        registrar_historico_regras("SISTEMA", "VERSÃO INICIAL", REGRAS_OPERACIONAIS_INICIAIS)

    regras = REGRAS_OPERACIONAIS_PATH.read_text(encoding="utf-8").strip()
    return regras or REGRAS_OPERACIONAIS_INICIAIS


def registrar_historico_regras(usuario, acao, conteudo):
    registro = pd.DataFrame([{
        "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "usuario": usuario,
        "acao": acao,
        "tamanho": len(conteudo or ""),
        "conteudo": conteudo or "",
    }])
    if REGRAS_OPERACIONAIS_HISTORICO_PATH.exists():
        historico = pd.read_csv(REGRAS_OPERACIONAIS_HISTORICO_PATH)
        historico = pd.concat([historico, registro], ignore_index=True)
    else:
        historico = registro
    historico.to_csv(REGRAS_OPERACIONAIS_HISTORICO_PATH, index=False)


def salvar_regras_operacionais(conteudo, usuario="ADMIN"):
    conteudo_final = texto(conteudo).strip()
    REGRAS_OPERACIONAIS_PATH.write_text(conteudo_final, encoding="utf-8")
    registrar_historico_regras(usuario, "SALVOU REGRAS OPERACIONAIS", conteudo_final)


def carregar_historico_regras():
    if not REGRAS_OPERACIONAIS_HISTORICO_PATH.exists():
        return pd.DataFrame(columns=["data_hora", "usuario", "acao", "tamanho", "conteudo"])
    return pd.read_csv(REGRAS_OPERACIONAIS_HISTORICO_PATH)


def restaurar_ultima_versao_regras(usuario="ADMIN"):
    historico = carregar_historico_regras()
    if historico.empty:
        return False, "Nenhuma versão anterior encontrada."
    versoes = historico[historico["conteudo"].fillna("").astype(str).str.strip() != ""]
    if len(versoes) < 2:
        return False, "Não existe uma versão anterior para restaurar."
    conteudo_anterior = str(versoes.iloc[-2]["conteudo"])
    REGRAS_OPERACIONAIS_PATH.write_text(conteudo_anterior, encoding="utf-8")
    registrar_historico_regras(usuario, "RESTAUROU ÚLTIMA VERSÃO", conteudo_anterior)
    return True, "Última versão anterior restaurada com sucesso."


def render_regras_operacionais(admin):
    st.subheader("Regras Operacionais")
    st.caption("Regras usadas para interpretar fotos e gerar linhas operacionais, funcionando como o Excel Mestre.")
    regras_atuais = carregar_regras_operacionais()

    if admin:
        usuario = st.text_input("Usuário responsável pela alteração", value="ADMIN", key="regras_usuario")
        conteudo = st.text_area(
            "Conteúdo das regras operacionais",
            value=regras_atuais,
            height=560,
            key="regras_operacionais_editor",
            help="Campo preparado para textos longos. A última versão salva é carregada automaticamente.",
        )
        col_salvar, col_baixar, col_restaurar = st.columns(3)
        if col_salvar.button("💾 SALVAR", type="primary", use_container_width=True):
            salvar_regras_operacionais(conteudo, usuario or "ADMIN")
            st.success("Regras operacionais salvas como última versão.")
            st.rerun()
        col_baixar.download_button(
            "⬇️ BAIXAR REGRAS",
            data=conteudo.encode("utf-8"),
            file_name="regras_operacionais.md",
            mime="text/markdown",
            use_container_width=True,
        )
        if col_restaurar.button("↩️ RESTAURAR ÚLTIMA VERSÃO", use_container_width=True):
            ok, mensagem = restaurar_ultima_versao_regras(usuario or "ADMIN")
            st.success(mensagem) if ok else st.warning(mensagem)
            if ok:
                st.rerun()
    else:
        st.info("Usuários comuns podem visualizar as regras. Apenas administradores podem editar.")
        st.download_button(
            "⬇️ BAIXAR REGRAS",
            data=regras_atuais.encode("utf-8"),
            file_name="regras_operacionais.md",
            mime="text/markdown",
            use_container_width=True,
        )
        st.markdown(f'<div class="section-card"><pre style="white-space: pre-wrap; margin: 0; color: #fff;">{escape(regras_atuais)}</pre></div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("Histórico de alterações das regras")
    historico = carregar_historico_regras()
    if historico.empty:
        st.info("Nenhuma alteração registrada ainda.")
    else:
        st.dataframe(historico.drop(columns=["conteudo"], errors="ignore").tail(50).iloc[::-1], use_container_width=True, hide_index=True)

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



def recortar_imagem_por_percentuais(imagem, topo=0, baixo=0, esquerda=0, direita=0):
    """Recorta a imagem usando percentuais de 0 a 50% em cada borda."""
    largura, altura = imagem.size

    corte_topo = int(altura * (topo / 100))
    corte_baixo = int(altura * (baixo / 100))
    corte_esquerda = int(largura * (esquerda / 100))
    corte_direita = int(largura * (direita / 100))

    x_inicio = max(0, min(corte_esquerda, largura - 1))
    y_inicio = max(0, min(corte_topo, altura - 1))
    x_fim = max(x_inicio + 1, min(largura - corte_direita, largura))
    y_fim = max(y_inicio + 1, min(altura - corte_baixo, altura))

    return imagem.crop((x_inicio, y_inicio, x_fim, y_fim))


def detectar_modo_celular_ler_folha():
    """Retorna preferências de layout para a aba Ler folha.

    Streamlit não expõe uma largura de viewport confiável no backend em todas as
    versões. Por isso, combinamos CSS responsivo para telas pequenas com um
    controle explícito de modo celular para garantir uma experiência previsível.
    """
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlock"]:has(.ler-folha-mobile-css) .stButton > button {
            width: 100%;
            min-height: 3.2rem;
            font-size: 1.05rem;
            font-weight: 700;
            border-radius: 0.8rem;
            margin: 0.15rem 0;
        }
        div[data-testid="stVerticalBlock"]:has(.ler-folha-mobile-css) img {
            max-width: 100%;
            height: auto;
            object-fit: contain;
        }
        @media (max-width: 760px) {
            div[data-testid="stVerticalBlock"]:has(.ler-folha-mobile-css) {
                gap: 0.55rem;
            }
            div[data-testid="stVerticalBlock"]:has(.ler-folha-mobile-css) .stButton > button {
                min-height: 3.6rem;
                font-size: 1.1rem;
            }
            div[data-testid="stVerticalBlock"]:has(.ler-folha-mobile-css) [data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
            }
        }
        </style>
        <span class="ler-folha-mobile-css"></span>
        """,
        unsafe_allow_html=True,
    )

    modo_celular = st.toggle(
        "Modo Celular",
        value=st.session_state.get("modo_celular_ler_folha", False),
        key="modo_celular_ler_folha",
        help=(
            "Ative no celular ou quando a tela estiver estreita. O layout fica em "
            "coluna única, com botões grandes e a imagem inteira como padrão."
        ),
    )

    if modo_celular:
        largura_cropper = 360
        st.caption(
            "Modo Celular ativo: uma imagem por vez, corte abaixo da foto e "
            "imagem inteira priorizada para leitura."
        )
    else:
        largura_cropper = 900

    return modo_celular, largura_cropper


def imagem_para_png_bytes(imagem):
    buffer = BytesIO()
    imagem.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()

def interpretar_folha_com_gemini(imagem_bytes, mime_type="image/png"):
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

    resposta, modelo_usado, api_usada = consultar_gemini_com_fallback(
        contents=[
            prompt,
            types.Part.from_bytes(data=imagem_bytes, mime_type=mime_type),
        ],
    )

    return resposta.text if resposta.text is not None else "", modelo_usado, api_usada

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

        if "," in s:
            # Formato brasileiro: 2.189,60 / 992,17.
            # O ponto é separador de milhar somente quando há vírgula decimal.
            s = s.replace(".", "").replace(",", ".")
        elif "." in s:
            partes = s.split(".")
            # Sem vírgula, preserve ponto decimal vindo do banco (2189.6).
            # Remova pontos apenas quando o padrão parecer milhar (2.189 ou 2.189.600).
            if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
                s = s.replace(".", "")

        return float(s)
    except Exception:
        return None


TABELA_DELIVERIES = "deliveries"
TABELA_CLIENTES = "clientes_cnpj"
TABELA_AUDITORIA = "historico_alteracoes"


def registrar_historico_alteracao(tabela, registro_id, campo, valor_antigo, valor_novo, usuario="SISTEMA"):
    if str(valor_antigo) == str(valor_novo):
        return
    payload = {
        "tabela": tabela,
        "registro_id": str(registro_id or ""),
        "campo": campo,
        "valor_antigo": None if valor_antigo is None else str(valor_antigo),
        "valor_novo": None if valor_novo is None else str(valor_novo),
        "usuario": usuario or "SISTEMA",
        "data_hora": datetime.now().isoformat(),
    }
    try:
        supabase.table(TABELA_AUDITORIA).insert(payload).execute()
    except Exception as exc:
        logger.warning("Não foi possível gravar auditoria em %s: %s", TABELA_AUDITORIA, exc)


def registrar_historico_campos(tabela, registro_id, antes, depois, usuario="SISTEMA"):
    antes = antes or {}
    for campo, valor_novo in (depois or {}).items():
        registrar_historico_alteracao(tabela, registro_id, campo, antes.get(campo), valor_novo, usuario)


def listar_clientes():
    try:
        res = supabase.table(TABELA_CLIENTES).select("*").order("cliente").execute()
        return pd.DataFrame(res.data or [])
    except Exception as exc:
        logger.warning("Tabela de clientes indisponível: %s", exc)
        return pd.DataFrame(columns=["id", "cliente", "cidade", "endereco", "cnpj", "razao_social", "observacao", "data_cadastro", "data_ultima_atualizacao"])



def normalizar_chave_cliente_cnpj(*partes):
    """Gera chave comparável para localizar CNPJ sem alterar o fluxo operacional."""
    return " ".join(limpar_busca(parte) for parte in partes if texto(parte)).strip()


def formatar_cnpj_cliente(valor):
    cnpj = texto(valor)
    if not cnpj:
        return ""
    digitos = re.sub(r"\D", "", cnpj)
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return cnpj


def aplicar_cnpjs_clientes_cadastrados(df_base, clientes):
    """Preenche CNPJ nas consultas usando a tabela existente clientes_cnpj.

    Quando não há cadastro correspondente, mantém o campo vazio para que a
    resposta operacional oculte o CNPJ sem mensagens extras.
    """
    if df_base is None or df_base.empty or clientes is None or clientes.empty:
        return df_base

    df_enriquecido = df_base.copy()
    if "cnpj" not in df_enriquecido.columns:
        df_enriquecido["cnpj"] = ""

    mapa_cliente_cidade = {}
    mapa_cliente = {}
    for _, cliente_row in clientes.iterrows():
        cnpj = formatar_cnpj_cliente(cliente_row.get("cnpj"))
        if not cnpj:
            continue
        cliente = cliente_row.get("cliente")
        cidade = cliente_row.get("cidade")
        chave_cliente = normalizar_chave_cliente_cnpj(cliente)
        chave_cliente_cidade = normalizar_chave_cliente_cnpj(cliente, cidade)
        if chave_cliente_cidade:
            mapa_cliente_cidade.setdefault(chave_cliente_cidade, cnpj)
        if chave_cliente:
            mapa_cliente.setdefault(chave_cliente, cnpj)

    if not mapa_cliente_cidade and not mapa_cliente:
        return df_enriquecido

    for idx, row in df_enriquecido.iterrows():
        cnpj_atual = formatar_cnpj_cliente(row.get("cnpj"))
        if cnpj_atual:
            df_enriquecido.at[idx, "cnpj"] = cnpj_atual
            continue
        cliente = row.get("cliente")
        cidade = row.get("cidade")
        chave_cliente_cidade = normalizar_chave_cliente_cnpj(cliente, cidade)
        chave_cliente = normalizar_chave_cliente_cnpj(cliente)
        cnpj = mapa_cliente_cidade.get(chave_cliente_cidade) or mapa_cliente.get(chave_cliente)
        if cnpj:
            df_enriquecido.at[idx, "cnpj"] = cnpj

    return df_enriquecido

def render_clientes_cnpj(admin):
    st.subheader("Clientes e CNPJ")
    clientes = listar_clientes()
    q_cliente = st.text_input("Pesquisar por cliente")
    q_cnpj = st.text_input("Pesquisar por CNPJ")
    q_cidade = st.text_input("Pesquisar por cidade")
    q_endereco = st.text_input("Pesquisar por endereço")
    filtrado = clientes.copy()
    for coluna, valor in [("cliente", q_cliente), ("cnpj", q_cnpj), ("cidade", q_cidade), ("endereco", q_endereco)]:
        if valor and coluna in filtrado.columns:
            filtrado = filtrado[filtrado[coluna].fillna("").astype(str).str.upper().str.contains(valor.upper(), na=False)]
    st.dataframe(filtrado, use_container_width=True, hide_index=True)
    if not admin:
        st.info("Entre como administrador para adicionar, editar ou excluir clientes.")
        return
    with st.form("form_cliente_cnpj"):
        st.markdown("### Adicionar / editar cliente")
        id_cliente = st.text_input("ID para editar (deixe vazio para adicionar)")
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente")
        cidade = c2.text_input("Cidade")
        endereco = st.text_input("Endereço")
        cnpj = c1.text_input("CNPJ")
        razao = c2.text_input("Razão Social")
        observacao = st.text_area("Observação")
        salvar_cliente = st.form_submit_button("Salvar cliente", type="primary")
    if salvar_cliente:
        agora = datetime.now().isoformat()
        payload = {"cliente": cliente.upper(), "cidade": cidade.upper(), "endereco": endereco.upper(), "cnpj": cnpj, "razao_social": razao.upper(), "observacao": observacao, "data_ultima_atualizacao": agora}
        if id_cliente.strip():
            atual = supabase.table(TABELA_CLIENTES).select("*").eq("id", int(id_cliente)).limit(1).execute()
            antes = atual.data[0] if atual.data else {}
            supabase.table(TABELA_CLIENTES).update(payload).eq("id", int(id_cliente)).execute()
            registrar_historico_campos(TABELA_CLIENTES, id_cliente, antes, payload, "ADMIN")
        else:
            payload["data_cadastro"] = agora
            supabase.table(TABELA_CLIENTES).insert(payload).execute()
            registrar_historico_campos(TABELA_CLIENTES, payload.get("cnpj"), {}, payload, "ADMIN")
        st.success("Cliente salvo.")
        st.rerun()
    excluir_id = st.text_input("ID do cliente para excluir")
    if st.button("Excluir cliente") and excluir_id.strip():
        atual = supabase.table(TABELA_CLIENTES).select("*").eq("id", int(excluir_id)).limit(1).execute()
        antes = atual.data[0] if atual.data else {}
        supabase.table(TABELA_CLIENTES).delete().eq("id", int(excluir_id)).execute()
        registrar_historico_campos(TABELA_CLIENTES, excluir_id, antes, {"excluido": True}, "ADMIN")
        st.warning("Cliente excluído.")
        st.rerun()



def listar():
    res = supabase.table(TABELA_DELIVERIES).select("*").execute()
    return ordenar_visualizacao(pd.DataFrame(res.data or []))


def atualizar_dataframe_principal():
    """Recarrega a base principal usada por Buscar/visualizar e Conversação."""
    df_atualizado = listar()
    if "st" in globals():
        st.session_state["df_principal"] = df_atualizado
        st.session_state["excel_mestre_bytes"] = excel_bytes(df_atualizado)
        st.session_state["excel_mestre_atualizado_em"] = datetime.now().isoformat()
    globals()["df"] = df_atualizado
    return df_atualizado


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
        elif k in ["paletes", "pallets", "pallet", "p", "paletes agendados"]:
            mapa[c] = "paletes"
        elif k in ["pc", "paletes_coletados", "paletes coletados", "pallets coletados", "pallet coletado"]:
            mapa[c] = "paletes_coletados"
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

    horario = normalizar_horario(ocorrencias[-1].group(2))
    linha_sem_marcadores = padrao_bd.sub(" ", original).strip(" :-")
    motivo = normalizar_observacao(linha_sem_marcadores)
    if motivo and motivo.startswith("O "):
        motivo = motivo[2:]
    else:
        motivo = linha_sem_marcadores.upper().strip()
    observacao = f"F {horario} O {motivo + ' ' if motivo else ''}BLOQUEIO ÀS {horario}" if horario else None
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
        # WMS pode ter complemento/localidade no nome do cliente
        # (ex.: "WMS MAX ATACADO AV. SANTOS DUMONT").
        # A normalização aqui deve preservar o texto completo para salvar;
        # qualquer forma simplificada deve ser usada somente em busca/comparação.
        base = s_sem_local.strip()
    else:
        base = s_sem_local.strip()

    return (base + sufixo).strip()


def normalizar_observacao(v):
    obs = texto(v)
    if not obs or obs in ["—", "-"]:
        return None

    obs_limpo = limpar_busca(obs)
    motivos_deslocamento = [
        "SEM CARGA",
        "CLIENTE FECHADO",
        "AGUARDANDO AGENDAMENTO",
        "FALTA DE MERCADORIA",
        "RECUSA DE RECEBIMENTO",
    ]
    motivos_bloqueio = [
        "CLIENTE FECHADO",
        "AGUARDANDO AGENDAMENTO",
        "SEM JANELA DE RECEBIMENTO",
        "RECUSA DE RECEBIMENTO",
        "FALTA DE MERCADORIA",
    ]

    sr_numero = re.search(r"\bSR\s*(\d{3,})\b", obs_limpo)
    if sr_numero and "REEMB" in obs_limpo:
        return f"O SR {sr_numero.group(1)} REEMBOLSO"
    if re.search(r"\bS\.?R\b", obs_limpo) or "REEMB" in obs_limpo or "SOLICITACAO DE REEMBOLSO" in obs_limpo:
        return "O SR/REEMBOLSO"

    if re.search(r"\bBLOQ(?:UEIO)?\b", obs_limpo) or any(m in obs_limpo for m in motivos_bloqueio):
        for motivo in motivos_bloqueio:
            if motivo in obs_limpo:
                return f"O BLOQUEIO {motivo}"
        return "O BLOQUEIO"

    if "DESLOC" in obs_limpo or any(m in obs_limpo for m in motivos_deslocamento):
        for motivo in motivos_deslocamento:
            if motivo in obs_limpo:
                return f"O DESLOCAMENTO {motivo}"
        return "O DESLOCAMENTO"

    # Não salvar essas observações inúteis
    ignorar = ["HP", "ULTIMA OCORRENCIA", "ULTIMA OCORRÊNCIA", "EM ANDAMENTO", "FINALIZADO", "STATUS"]
    if any(x in obs_limpo for x in ignorar):
        if not any(x in obs_limpo for x in ["CS", "C OK", "L OK", "MOTIVO", "NOK"]):
            return None

    permitido = ["CS", "C OK", "L OK", "MOTIVO", "NOK"]
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
        "paletes_coletados": numero(row.get("paletes_coletados", "")),
        "valor_frete": numero(row.get("valor_frete", "")),
        "l_horario": normalizar_horario(row.get("l_horario", "")) or None,
        "c_horario": normalizar_horario(row.get("c_horario", "")) or None,
        "f_horario": normalizar_horario(row.get("f_horario", "")) or None,
        "tipo": texto(row.get("tipo", "")) or None,
        "status": calcular_status_automatico(row.get("observacoes", ""), row.get("f_horario", "")),
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

    # Aceita a linha copiada do status no formato:
    # DATA | MOTORISTA | DELIVERY | CLIENTE L HH:MM C HH:MM ...
    # O prefixo com barras verticais é convertido para as abreviações oficiais
    # antes do parser por marcadores, preservando os demais campos digitados.
    marcador_operacional = re.search(
        r"(?<!\S)(FI|DF|PC|F|L|C)\s*:?\s*([0-2]?\d[:hH][0-5]\d|\d{1,2}/\d{1,2}(?:/\d{2,4})?|[0-9]+(?:[,.][0-9]+)?)\b",
        original_parse,
        flags=re.IGNORECASE,
    )
    prefixo_pipe = original_parse[:marcador_operacional.start()].strip() if marcador_operacional else original_parse.strip()
    sufixo_pipe = original_parse[marcador_operacional.start():].strip() if marcador_operacional else ""
    partes_pipe = [parte.strip() for parte in prefixo_pipe.split("|")]
    if len(partes_pipe) >= 4:
        data_pipe, motorista_pipe, delivery_pipe = partes_pipe[:3]
        cliente_pipe = " | ".join(partes_pipe[3:]).strip()
        delivery_pipe_limpo = limpar_codigo_delivery(delivery_pipe)
        if re.fullmatch(r"(?:378|340)\d{7}", delivery_pipe_limpo):
            original_parse = (
                f"DATA {data_pipe} M {motorista_pipe} D {delivery_pipe_limpo} "
                f"CL {cliente_pipe} {sufixo_pipe}"
            ).strip()

    # REGRA NOVA:
    # Aceita FI e F para horário de finalização.
    # Não aceita mais campo S.
    # S.F e L.F devem vir dentro do CL, não no O nem no FI.
    padrao = re.compile(
        r"(?<!\S)(DATA|DF|SR|FI|F|CL|PC|M|D|P|V|L|C|O)(?=\s*:|\s+)\s*:?\s*",
        re.IGNORECASE,
    )
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

    if not delivery:
        delivery_implicita = re.search(r"\b((?:378|340)\d{7})\b", original_parse)
        if delivery_implicita:
            delivery = delivery_implicita.group(1)

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
    if dados.get("PC"):
        campos["paletes_coletados"] = numero(dados.get("PC"))
    if dados.get("V"):
        campos["valor_frete"] = numero(dados.get("V"))
    if dados.get("L"):
        campos["l_horario"] = normalizar_horario(dados.get("L")) or None
    if dados.get("C"):
        campos["c_horario"] = normalizar_horario(dados.get("C")) or None
    if dados.get("FI") or dados.get("F"):
        campos["f_horario"] = normalizar_horario(dados.get("FI") or dados.get("F")) or None
    if horario_bd:
        campos["f_horario"] = horario_bd

    obs = normalizar_observacao(dados.get("O", ""))
    if obs:
        campos["observacoes"] = obs
    if observacao_bd:
        campos["observacoes"] = observacao_bd

    campos["status"] = calcular_status_automatico(campos.get("observacoes", ""), campos.get("f_horario"))

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

    existente = supabase.table(TABELA_DELIVERIES).select("id").eq(chave, valor).limit(1).execute()

    if existente.data:
        antes = supabase.table(TABELA_DELIVERIES).select("*").eq(chave, valor).limit(1).execute().data[0]
        supabase.table(TABELA_DELIVERIES).update(campos).eq(chave, valor).execute()
        registrar_historico_campos(TABELA_DELIVERIES, antes.get("id") or valor, antes, campos, "ADMIN")
        atualizar_dataframe_principal()
        return "atualizado"

    supabase.table(TABELA_DELIVERIES).insert(campos).execute()
    registrar_historico_campos(TABELA_DELIVERIES, valor, {}, campos, "ADMIN")
    atualizar_dataframe_principal()
    return "criado"


def numero_operacional_visual(valor):
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return texto(valor)


def resumo_atualizacao_rapida(parsed, resultado):
    campos = parsed.get("campos", {})
    delivery = campos.get("delivery") or parsed.get("valor_busca", "")
    status = "OK" if resultado in ["atualizado", "criado"] else texto(resultado).upper()
    linhas = [f"D {delivery} {status}"]

    for rotulo, coluna in [
        ("L", "l_horario"),
        ("C", "c_horario"),
        ("FI", "f_horario"),
        ("DF", "data_finalizacao"),
        ("PC", "paletes_coletados"),
    ]:
        valor = campos.get(coluna)
        if valor:
            linhas.append(f"{rotulo} {numero_operacional_visual(valor)}")

    return "\n".join(linhas)





ACOES_CONVERSA = {
    "FINALIZACAO": ["FINALIZOU", "FINALIZADO", "FINAL", "FI", "F"],
    "BLOQUEIO": ["BLOQUEIO", "BLOQUEADO", "B"],
    "DESLOCAMENTO": ["DESLOCAMENTO", "DESLOCOU", "D"],
}

PALAVRAS_COMANDO_CONVERSA = {
    "A", "AS", "ÀS", "O", "OS", "DE", "DO", "DA", "DOS", "DAS", "EM", "NO", "NA",
    "NOS", "NAS", "AO", "AOS", "ATE", "ATÉ", "PARA", "POR", "NA", "NO", "E", "AGORA",
    "MUDAR", "TROCAR", "ALTERAR", "CORRIGIR", "MOTORISTA", "CLIENTE", "CL", "M",
}


def limpar_codigo_delivery(v):
    return re.sub(r"\D", "", texto(v))


def parece_delivery_completo(codigo):
    codigo_limpo = limpar_codigo_delivery(codigo)
    return len(codigo_limpo) >= 8 and codigo_limpo.startswith(("378", "340"))


def normalizar_data_conversa(v):
    s = texto(v)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", s)
    if not m:
        return ""
    dia = m.group(1).zfill(2)
    mes = m.group(2).zfill(2)
    ano = m.group(3)
    if not ano:
        return f"{dia}/{mes}"
    if len(ano) == 2:
        ano = "20" + ano
    return f"{dia}/{mes}/{ano}"


def extrair_campos_operacionais_conversa(frase):
    """Extrai marcadores operacionais L, C, FI, DF e PC da conversa em qualquer ordem."""
    original = texto(frase)
    campos = {"l_horario": "", "c_horario": "", "f_horario": "", "data_finalizacao": "", "paletes_coletados": ""}

    for marcador, valor in re.findall(
        r"(?<!\w)(L|C|FI|PC)\s*:?\s*([0-2]?\d[:hH][0-5]\d|[0-9]+(?:[,.][0-9]+)?)\b",
        original,
        flags=re.IGNORECASE | re.UNICODE,
    ):
        chave = limpar_busca(marcador)
        horario = normalizar_horario(valor)
        if chave == "PC":
            campos["paletes_coletados"] = numero(valor)
            continue
        if chave == "L":
            campos["l_horario"] = horario
        elif chave == "C":
            campos["c_horario"] = horario
        elif chave == "FI":
            campos["f_horario"] = horario

    data_match = re.search(
        r"\b(?:DT|DF|DATA)\s*:?\s*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
        original,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if data_match:
        campos["data_finalizacao"] = normalizar_data_conversa(data_match.group(1))

    return campos

def identificar_acao_conversa(frase):
    texto_sem_marcador_delivery = re.sub(
        r"(?<!\w)(?:D|DELIVERY|REMESSA)\s*:?\s*\d{4,}\b",
        " ",
        texto(frase),
        flags=re.IGNORECASE | re.UNICODE,
    )
    texto_limpo = limpar_busca(texto_sem_marcador_delivery)
    for acao_candidata, aliases in ACOES_CONVERSA.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", texto_limpo) for alias in aliases):
            return acao_candidata
    return ""


def extrair_motorista_conversa(frase):
    texto_limpo = limpar_busca(frase)

    for nome in MOTORISTAS_FIXOS:
        primeiro_nome = nome.split()[0]
        if re.search(rf"\b{re.escape(primeiro_nome)}\b", texto_limpo):
            return nome

    padroes = [
        r"\bM\s+([A-ZÀ-ÿ][\wÀ-ÿ]*(?:\s+[A-ZÀ-ÿ][\wÀ-ÿ]*){0,3})",
        r"\bMOTORISTA\s*:?\s*([A-ZÀ-ÿ][\wÀ-ÿ]*(?:\s+[A-ZÀ-ÿ][\wÀ-ÿ]*){0,3})",
    ]
    for padrao in padroes:
        match = re.search(padrao, frase, flags=re.IGNORECASE | re.UNICODE)
        if match:
            motorista = limpar_busca(match.group(1))
            motorista = re.split(
                r"\b(?:FINALIZOU|FINALIZADO|FINAL|FI|BLOQUEIO|BLOQUEADO|DESLOCAMENTO|DESLOCOU|PARA|CLIENTE|NA|NO)\b",
                motorista,
                maxsplit=1,
            )[0].strip()
            if motorista:
                return normalizar_motorista(motorista)

    acao_match = re.search(
        r"\b(?:FINALIZOU|FINALIZADO|FINAL|FI|BLOQUEIO|BLOQUEADO|DESLOCAMENTO|DESLOCOU)\b",
        texto_limpo,
    )
    if acao_match:
        antes_acao = texto_limpo[: acao_match.start()].strip()
        palavras = [
            p
            for p in re.findall(r"[\wÀ-ÿ]+", antes_acao, flags=re.UNICODE)
            if p not in {"M", "MOTORISTA"}
        ]
        if palavras:
            return normalizar_motorista(" ".join(palavras[-4:]))

    return ""


def extrair_codigo_conversa(frase):
    original = texto(frase)
    marcador = re.search(
        r"(?<!\w)(?:D|DELIVERY|REMESSA)\s*:?\s*(\d{4,})\b",
        original,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if marcador:
        return marcador.group(1)

    numeros = re.findall(r"\b\d{4,}\b", original)
    completos = [n for n in numeros if parece_delivery_completo(n)]
    if completos:
        return completos[0]
    return numeros[0] if numeros else ""


def extrair_contexto_linha_busca(frase, codigo):
    """Extrai motorista/cliente de linhas copiadas da busca: M | D | CL | ..."""
    original = texto(frase)
    if "|" not in original:
        return "", ""

    partes = [p.strip() for p in original.split("|") if p.strip()]
    if not partes:
        return "", ""

    idx_codigo = -1
    codigo_limpo = limpar_codigo_delivery(codigo)
    for i, parte in enumerate(partes):
        numeros = re.findall(r"\b\d{4,}\b", parte)
        if codigo_limpo and any(limpar_codigo_delivery(n) == codigo_limpo for n in numeros):
            idx_codigo = i
            break
        if any(parece_delivery_completo(n) for n in numeros):
            idx_codigo = i
            break

    motorista = ""
    cliente = ""
    if idx_codigo > 0:
        motorista = normalizar_motorista(partes[idx_codigo - 1])
    elif partes and not re.search(r"\b\d{4,}\b", partes[0]):
        motorista = normalizar_motorista(partes[0])

    if idx_codigo >= 0 and idx_codigo + 1 < len(partes):
        cliente_bruto = partes[idx_codigo + 1]
        cliente_bruto = re.split(
            r"\b(?:FI|FINALIZOU|FINALIZADO|FINAL|DF|DT|DATA|BLOQUEIO|BLOQUEADO|DESLOCAMENTO|DESLOCOU)\b",
            cliente_bruto,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        cliente = normalizar_cliente_rapido(cliente_bruto)

    return motorista, cliente


def extrair_valores_alteracao_conversa(frase, codigo):
    original = texto(frase)
    frase_sem_codigo = re.sub(rf"\b{re.escape(codigo)}\b", " ", original) if codigo else original
    frase_sem_codigo = re.sub(
        r"(?<!\w)(?:DELIVERY|REMESSA|D(?=\s*:?\s*\d))\s*:?",
        " ",
        frase_sem_codigo,
        flags=re.IGNORECASE | re.UNICODE,
    )
    texto_limpo = limpar_busca(frase_sem_codigo)

    motorista = ""
    cliente = ""

    def limpar_valor_alteracao(valor):
        valor_limpo = limpar_busca(valor)
        valor_limpo = re.sub(
            r"^(?:MUDAR|TROCAR|ALTERAR|CORRIGIR|PARA|DE|DO|DA|DOS|DAS)\s+",
            "",
            valor_limpo,
        ).strip(" :-|\n\t")
        return valor_limpo

    marcador_re = re.compile(
        r"(?<!\w)(CL|CLIENTE|MOTORISTA|M)\s*:?\s+(.+?)(?=(?:\n|\s+)(?:CL|CLIENTE|MOTORISTA|M)\s*:?\s+|$)",
        flags=re.IGNORECASE | re.UNICODE | re.DOTALL,
    )
    for marcador in marcador_re.finditer(frase_sem_codigo):
        chave = limpar_busca(marcador.group(1))
        valor = limpar_valor_alteracao(marcador.group(2))
        if not valor:
            continue
        if chave in {"M", "MOTORISTA"}:
            motorista = normalizar_motorista(valor)
        elif chave in {"CL", "CLIENTE"}:
            cliente = normalizar_cliente_rapido(valor)


    m = re.search(r"\bMOTORISTA\s+(?:DA\s+|DO\s+|DE\s+)?(?:\d{4,}\s+)?PARA\s+(.+?)(?:\s+E\s+CLIENTE\s+PARA\s+|\s+NA\s+|\s+NO\s+|$)", texto_limpo)
    if m:
        motorista = normalizar_motorista(m.group(1))

    m = re.search(r"\bCLIENTE\s+(?:DA\s+|DO\s+|DE\s+)?(?:\d{4,}\s+)?PARA\s+(.+?)(?:\s+E\s+MOTORISTA\s+PARA\s+|\s+NA\s+|\s+NO\s+|$)", texto_limpo)
    if m:
        cliente = normalizar_cliente_rapido(m.group(1))

    m = re.search(r"\bTROCAR\s+(.+?)\s+POR\s+(.+?)(?:\s+NA\s+|\s+NO\s+|$)", texto_limpo)
    if m and not motorista:
        motorista = normalizar_motorista(m.group(2))

    m = re.search(r"\bAGORA\s+E\s+(.+)$", texto_limpo)
    if m:
        valor_agora = m.group(1).strip()
        partes_agora = [p.strip() for p in re.split(r"\s+E\s+", valor_agora, maxsplit=1) if p.strip()]
        if len(partes_agora) == 2:
            motorista = motorista or normalizar_motorista(partes_agora[0])
            cliente = normalizar_cliente_rapido(partes_agora[1])
        elif any(re.search(rf"\b{re.escape(nome.split()[0])}\b", valor_agora) for nome in MOTORISTAS_FIXOS):
            motorista = motorista or normalizar_motorista(valor_agora)
        else:
            cliente = normalizar_cliente_rapido(valor_agora)
        antes = texto_limpo[:m.start()].strip()
        palavras = [p for p in antes.split() if p not in PALAVRAS_COMANDO_CONVERSA and not p.isdigit()]
        if palavras and not motorista:
            motorista = normalizar_motorista(" ".join(palavras[-4:]))
    else:
        m = re.search(r"\bAGORA\s+(.+)$", texto_limpo)
        if m:
            valor = m.group(1).strip()
            if any(re.search(rf"\b{re.escape(nome.split()[0])}\b", valor) for nome in MOTORISTAS_FIXOS):
                motorista = normalizar_motorista(valor)
            else:
                cliente = normalizar_cliente_rapido(valor)

    return motorista.strip(), cliente.strip()



def extrair_observacao_livre_conversa(frase):
    """Extrai texto livre informado no marcador O até o fim da frase."""
    original = texto(frase)
    if not original:
        return ""

    matches = list(re.finditer(r"(?<!\w)O\s+(.+)$", original, flags=re.IGNORECASE | re.UNICODE))
    if not matches:
        return ""

    observacao = matches[-1].group(1).strip(" :-|")
    return limpar_busca(observacao).strip()


def remover_observacao_livre_conversa(frase):
    """Remove o marcador O e sua observação para não contaminar cliente/motorista."""
    original = texto(frase)
    if not original:
        return ""
    return re.sub(r"(?<!\w)O\s+.+$", " ", original, count=1, flags=re.IGNORECASE | re.UNICODE).strip()


def combinar_observacoes_conversa(*observacoes):
    partes = []
    for obs in observacoes:
        obs_limpa = texto(obs).strip(" |")
        if obs_limpa:
            partes.append(obs_limpa.upper())
    return " | ".join(partes) if partes else None


COMANDOS_CONSULTA_CONVERSA = {
    "RELATORIO",
    "RELATÓRIO",
    "QUANTOS",
    "QUANTAS",
    "QUAIS",
    "COMO",
    "LISTAR",
    "MOSTRAR",
    "TOTAL",
    "RESUMO",
    "STATUS",
    "PENDENTES",
    "COLETAS",
    "EM",
    "TODAS",
    "SEM",
    "DESLOCAMENTO",
    "DESLOCAMENTOS",
    "BLOQUEIO",
    "BLOQUEIOS",
    "REEMBOLSO",
    "REEMBOLSOS",
}

PADROES_RELATORIO_CONVERSA = [
    r"\bDESLOCAMENTOS?\s+(?:DO\s+DIA|DE)\b",
    r"\bBLOQUEIOS?\s+(?:DO\s+DIA|DE)\b",
    r"\bREEMBOLSOS?\s+(?:DO\s+DIA|DE)\b",
    r"\bSEM\s+FI\s+(?:DO\s+DIA|DE)\b",
    r"\bSTATUS\s+(?:DO\s+DIA|DE)\b",
]


def detectar_modo_conversa(frase):
    """Classifica a frase da aba conversa sem misturar consulta e atualização."""
    frase_texto = texto(frase)
    frase_norm = limpar_busca(frase_texto)

    # Pedidos explícitos de relatório por data não são atualização e não devem
    # exigir HH:MM, mesmo quando contêm termos operacionais como DESLOCAMENTO.
    if any(re.search(padrao, frase_norm) for padrao in PADROES_RELATORIO_CONVERSA):
        return "CONSULTA"

    primeira_palavra = re.match(r"^\s*([\wÀ-ÿ]+)", frase_texto, flags=re.UNICODE)
    if not primeira_palavra:
        return "ATUALIZACAO"

    comando = limpar_busca(primeira_palavra.group(1))
    return "CONSULTA" if comando in COMANDOS_CONSULTA_CONVERSA else "ATUALIZACAO"


def parse_atualizacao_conversa(frase):
    original = texto(frase)
    if not original:
        return None, "Digite uma frase para interpretar."

    observacao_livre = extrair_observacao_livre_conversa(original)
    original_sem_observacao = remover_observacao_livre_conversa(original) if observacao_livre else original

    campos_operacionais = extrair_campos_operacionais_conversa(original_sem_observacao)
    horario_match = re.search(r"\b([0-2]?\d[:hH][0-5]\d)\b", original_sem_observacao)
    horario_generico = normalizar_horario(horario_match.group(1)) if horario_match else ""
    horario = campos_operacionais.get("f_horario") or horario_generico
    data_finalizacao = campos_operacionais.get("data_finalizacao", "")

    codigo = extrair_codigo_conversa(original_sem_observacao)
    acao = identificar_acao_conversa(original_sem_observacao)
    motorista_alteracao, cliente_alteracao = extrair_valores_alteracao_conversa(original_sem_observacao, codigo)
    eh_alteracao = bool(
        re.search(r"\b(MUDAR|TROCAR|ALTERAR|CORRIGIR|AGORA)\b", limpar_busca(original))
        or (not acao and (motorista_alteracao or cliente_alteracao))
    )

    if not eh_alteracao:
        motorista_alteracao, cliente_alteracao = "", ""
    motorista_linha, cliente_linha = extrair_contexto_linha_busca(original_sem_observacao, codigo)
    motorista = motorista_alteracao or motorista_linha or extrair_motorista_conversa(original_sem_observacao)

    tem_campos_operacionais = any(campos_operacionais.get(chave) for chave in ["l_horario", "c_horario", "f_horario", "data_finalizacao", "paletes_coletados"])

    if not acao and campos_operacionais.get("f_horario"):
        acao = "FINALIZACAO"
    elif not acao and horario_generico and not tem_campos_operacionais:
        acao = "FINALIZACAO"

    if not acao and not eh_alteracao and not codigo and not campos_operacionais.get("paletes_coletados"):
        return None, "Não encontrei ação válida: finalizou, bloqueio, deslocamento, mudar, trocar ou PC."

    if acao and not horario:
        return None, "Não encontrei horário no formato HH:MM."

    texto_cliente = re.sub(r"\b[0-2]?\d[:hH][0-5]\d\b", " ", original_sem_observacao)
    texto_cliente = re.sub(r"\b\d{4,}\b", " ", texto_cliente)
    texto_cliente = re.sub(r"\b(?:L|C|FI)\s*:?\s*[0-2]?\d[:hH][0-5]\d\b", " ", texto_cliente, flags=re.IGNORECASE)
    texto_cliente = re.sub(r"\b(?:DT|DF|DATA)\s*:?\s*\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", texto_cliente, flags=re.IGNORECASE)

    palavras_remover = set(PALAVRAS_COMANDO_CONVERSA)
    if motorista:
        palavras_remover.update(limpar_busca(motorista).split())
    for aliases in ACOES_CONVERSA.values():
        palavras_remover.update(aliases)

    palavras_cliente = [
        palavra
        for palavra in re.findall(r"[\wÀ-ÿ.]+", texto_cliente, flags=re.UNICODE)
        if limpar_busca(palavra) not in palavras_remover
    ]
    cliente_contexto = cliente_linha or normalizar_cliente_rapido(" ".join(palavras_cliente))
    cliente = cliente_alteracao or ("" if eh_alteracao else cliente_contexto)

    if not codigo:
        return None, "Não encontrei delivery/remessa com pelo menos 4 dígitos."

    if eh_alteracao and not acao and not (motorista_alteracao or cliente_alteracao):
        return None, "Não encontrei motorista ou cliente para alterar."

    observacao_acao = None
    if acao == "BLOQUEIO":
        observacao_acao = f"BLOQUEIO {horario}"
    elif acao == "DESLOCAMENTO":
        observacao_acao = f"DESLOCAMENTO {horario}"
    observacoes = combinar_observacoes_conversa(observacao_acao, observacao_livre)

    return {
        "motorista": motorista,
        "horario": campos_operacionais.get("f_horario") or (horario if acao else ""),
        "l_horario": campos_operacionais.get("l_horario", ""),
        "c_horario": campos_operacionais.get("c_horario", ""),
        "final_delivery": codigo,
        "cliente": cliente_contexto,
        "novo_motorista": motorista_alteracao,
        "novo_cliente": cliente_alteracao,
        "acao": acao,
        "observacoes": observacoes,
        "data_finalizacao": data_finalizacao,
        "paletes_coletados": campos_operacionais.get("paletes_coletados"),
        "tipo_atualizacao": "alteracao" if eh_alteracao and not acao else "finalizacao",
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


def motorista_combina(motorista_registro, motorista_busca):
    registro = normalizar_motorista(motorista_registro)
    busca = normalizar_motorista(motorista_busca)

    if not busca:
        return True
    if busca in registro or registro in busca:
        return True

    palavras = [p for p in limpar_busca(busca).split() if len(p) > 1]
    if not palavras:
        return False

    return all(p in limpar_busca(registro) for p in palavras)


def buscar_coletas_por_conversa(df_base, parsed):
    if df_base.empty:
        return pd.DataFrame()

    resultado = df_base.copy()
    if "delivery" not in resultado.columns and "D" in resultado.columns:
        resultado["delivery"] = resultado["D"]
    for coluna in ["motorista", "delivery", "cliente", "f_horario", "data", "data_finalizacao"]:
        if coluna not in resultado.columns:
            resultado[coluna] = ""

    codigo_busca = limpar_codigo_delivery(parsed.get("final_delivery"))
    if codigo_busca:
        resultado["delivery"] = resultado["delivery"].astype("string").fillna("")
        entregas = resultado["delivery"].apply(limpar_codigo_delivery)
        if parece_delivery_completo(codigo_busca):
            mascara_codigo = entregas == codigo_busca
        else:
            completos = entregas.apply(parece_delivery_completo)
            mascara_codigo = completos & entregas.str.endswith(codigo_busca)
            if not mascara_codigo.any():
                mascara_codigo = entregas.str.endswith(codigo_busca[-4:])
    else:
        mascara_codigo = pd.Series(True, index=resultado.index)

    logger.info("DELIVERY EXTRAÍDO: %s", parsed.get("final_delivery"))
    logger.info("REGISTROS ENCONTRADOS: %s", int(mascara_codigo.sum()))
    logger.info("DELIVERY UTILIZADO: %s", codigo_busca)

    if codigo_busca and mascara_codigo.any():
        return resultado[mascara_codigo].copy()

    mascara = mascara_codigo
    if parsed.get("tipo_atualizacao") != "alteracao":
        mascara = mascara & resultado["f_horario"].apply(lambda v: not bool(texto(v)))
        if parsed.get("motorista"):
            mascara = mascara & resultado["motorista"].apply(lambda v: motorista_combina(v, parsed["motorista"]))
        if parsed.get("cliente"):
            mascara = mascara & resultado["cliente"].apply(lambda v: cliente_combina(v, parsed["cliente"]))

    return resultado[mascara].copy()


def campos_atualizacao_conversa(parsed, f_horario_atual=None):
    campos = {
        "atualizado_em": datetime.now().isoformat(),
    }
    if parsed.get("l_horario"):
        campos["l_horario"] = parsed["l_horario"]
    if parsed.get("c_horario"):
        campos["c_horario"] = parsed["c_horario"]
    if parsed.get("horario"):
        campos["f_horario"] = parsed["horario"]
    if parsed.get("data_finalizacao"):
        campos["data_finalizacao"] = parsed["data_finalizacao"]
    if parsed.get("paletes_coletados") is not None and parsed.get("paletes_coletados") != "":
        campos["paletes_coletados"] = parsed["paletes_coletados"]
    if parsed.get("novo_motorista"):
        campos["motorista"] = normalizar_motorista(parsed["novo_motorista"])
    if parsed.get("novo_cliente"):
        campos["cliente"] = normalizar_cliente_rapido(parsed["novo_cliente"])
    if parsed.get("observacoes"):
        campos["observacoes"] = parsed["observacoes"]
    if parsed.get("observacoes") or parsed.get("horario"):
        campos["status"] = calcular_status_automatico(
            campos.get("observacoes", ""),
            campos.get("f_horario") or f_horario_atual,
        )
    return completar_dados_motorista(campos) if campos.get("motorista") else campos


def atualizar_conversa_no_supabase(id_registro, parsed):
    colunas_log = "id,delivery,l_horario,c_horario,f_horario,data_finalizacao"
    atual = supabase.table(TABELA_DELIVERIES).select(colunas_log).eq("id", int(id_registro)).limit(1).execute()
    dados_atuais = atual.data[0] if atual.data else {}
    logger.info(
        "DELIVERY ENCONTRADA\nANTES:\nL=%s\nC=%s\nFI=%s",
        texto(dados_atuais.get("l_horario")),
        texto(dados_atuais.get("c_horario")),
        texto(dados_atuais.get("f_horario")),
    )
    campos = campos_atualizacao_conversa(parsed, dados_atuais.get("f_horario"))
    supabase.table(TABELA_DELIVERIES).update(campos).eq(
        "id",
        int(id_registro),
    ).execute()
    registrar_historico_campos(TABELA_DELIVERIES, id_registro, dados_atuais, campos, "ADMIN")
    salvo = supabase.table(TABELA_DELIVERIES).select("*").eq("id", int(id_registro)).limit(1).execute()
    dados_salvos = salvo.data[0] if salvo.data else {}
    logger.info(
        "DEPOIS:\nL=%s\nC=%s\nFI=%s\nREGISTRO SALVO COM SUCESSO",
        texto(dados_salvos.get("l_horario")),
        texto(dados_salvos.get("c_horario")),
        texto(dados_salvos.get("f_horario")),
    )
    atualizar_dataframe_principal()
    return dados_salvos


def resumo_confirmacao_conversa(item, parsed):
    linhas = ["COLETA ENCONTRADA", "", f"D {texto(item.get('delivery'))}"]
    if texto(item.get("motorista")):
        linhas.append(f"M {texto(item.get('motorista'))}")
    if texto(item.get("cliente")):
        linhas.append(f"CL {texto(item.get('cliente'))}")

    alteracoes = []
    if parsed.get("novo_motorista"):
        alteracoes.append(f"M -> {normalizar_motorista(parsed['novo_motorista'])}")
    if parsed.get("novo_cliente"):
        alteracoes.append(f"CL -> {normalizar_cliente_rapido(parsed['novo_cliente'])}")
    if parsed.get("l_horario"):
        alteracoes.append(f"L -> {parsed['l_horario']}")
    if parsed.get("c_horario"):
        alteracoes.append(f"C -> {parsed['c_horario']}")
    if parsed.get("horario"):
        alteracoes.append(f"FI -> {parsed['horario']}")
    if parsed.get("data_finalizacao"):
        alteracoes.append(f"DF -> {parsed['data_finalizacao']}")
    if parsed.get("paletes_coletados") is not None and parsed.get("paletes_coletados") != "":
        alteracoes.append(f"PC -> {numero_operacional_visual(parsed['paletes_coletados'])}")
    if parsed.get("observacoes"):
        alteracoes.append(f"O -> {parsed['observacoes']}")
    if alteracoes:
        linhas.extend(["", "ALTERAÇÕES:", *alteracoes])
    linhas.extend(["", "CONFIRMAR?"])
    return "\n".join(linhas)


def resumo_registro_salvo_conversa(item):
    return (
        "REGISTRO SALVO NO BANCO PRINCIPAL\n"
        f"D {texto(item.get('delivery'))}\n"
        f"L {texto(item.get('l_horario')) or '—'}\n"
        f"C {texto(item.get('c_horario')) or '—'}\n"
        f"FI {texto(item.get('f_horario')) or '—'}\n"
        f"DF {texto(item.get('data_finalizacao')) or '—'}"
    )




COLUNAS_PRINCIPAIS_VISUAL = [
    "id", "data", "motorista", "delivery", "cliente", "paletes", "paletes_coletados", "valor_frete",
    "l_horario", "c_horario", "f_horario", "status", "observacoes",
]
ROTULOS_COLUNAS_VISUAL = {"id": "ID", "data": "DATA", "motorista": "MOTORISTA", "delivery": "DELIVERY", "cliente": "CLIENTE", "paletes": "PALETES", "paletes_coletados": "PC", "valor_frete": "VALOR", "l_horario": "LOCAL", "c_horario": "COLETADO", "f_horario": "FINALIZADO", "status": "STATUS", "observacoes": "OBSERVAÇÕES"}
COLUNAS_DETALHES_VISUAL = ["id", "cpf", "cavalo", "carreta", "sr", "data_finalizacao"]
ROTULOS_DETALHES_VISUAL = {"id": "ID", "cpf": "CPF", "cavalo": "CAVALO", "carreta": "CARRETA", "sr": "SR", "data_finalizacao": "DATA FINALIZAÇÃO"}

def valor_visual(v):
    return texto(v)

def moeda_visual(v):
    valor = numero(v)
    if valor is None:
        return ""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def status_visual(row):
    return calcular_status_automatico(row.get("observacoes", ""), row.get("f_horario", ""))

def preparar_tabela_principal(df_base):
    if df_base.empty:
        return pd.DataFrame(columns=list(ROTULOS_COLUNAS_VISUAL.values()))
    tabela = df_base.copy()
    for coluna in COLUNAS_PRINCIPAIS_VISUAL:
        if coluna not in tabela.columns:
            tabela[coluna] = ""
    tabela["status"] = tabela.apply(status_visual, axis=1)
    tabela = tabela[COLUNAS_PRINCIPAIS_VISUAL].copy()
    for coluna in tabela.columns:
        tabela[coluna] = tabela[coluna].apply(moeda_visual if coluna == "valor_frete" else valor_visual)
    return tabela.rename(columns=ROTULOS_COLUNAS_VISUAL)

def preparar_tabela_detalhes(df_base):
    if df_base.empty:
        return pd.DataFrame(columns=list(ROTULOS_DETALHES_VISUAL.values()))
    detalhes = df_base.copy()
    for coluna in COLUNAS_DETALHES_VISUAL:
        if coluna not in detalhes.columns:
            detalhes[coluna] = ""
    detalhes = detalhes[COLUNAS_DETALHES_VISUAL].copy()
    for coluna in detalhes.columns:
        detalhes[coluna] = detalhes[coluna].apply(valor_visual)
    return detalhes.rename(columns=ROTULOS_DETALHES_VISUAL)

def estilo_tabela_excel(df_visual):
    status_cores = {
        "FINALIZADO": "background-color: #dcfce7; color: #166534; font-weight: 800;",
        "EM ANDAMENTO": "background-color: #dbeafe; color: #1d4ed8; font-weight: 800;",
        "DESLOCAMENTO": "background-color: #ffedd5; color: #c2410c; font-weight: 800;",
        "BLOQUEIO": "background-color: #fee2e2; color: #b91c1c; font-weight: 800;",
        "PENDENTE": "background-color: #e5e7eb; color: #374151; font-weight: 800;",
    }
    def pintar_linha(row):
        return ["background-color: #eef6ff; color: #0f172a; border: 1px solid #cbdff5;"] * len(row)
    def pintar_status(valor):
        valor_norm = texto(valor).upper()
        for chave, estilo in status_cores.items():
            if chave in valor_norm:
                return estilo + " border-radius: 999px; text-align: center;"
        return "background-color: #f1f5f9; color: #334155; font-weight: 800;"
    styler = df_visual.style.apply(pintar_linha, axis=1)
    if "STATUS" in df_visual.columns:
        styler = styler.map(pintar_status, subset=["STATUS"])
    return styler.set_table_styles([
        {"selector": "th", "props": [("background-color", "#0f2f5f"), ("color", "#ffffff"), ("font-weight", "900"), ("border", "1px solid #234a7d"), ("text-align", "center")]},
        {"selector": "td", "props": [("padding", "8px 10px"), ("border", "1px solid #cbdff5")]},
        {"selector": "tbody tr:nth-child(even) td", "props": [("background-color", "#dbeeff")]},
    ])

def exibir_tabela_operacional(df_base, key_prefix="operacional"):
    tabela = preparar_tabela_principal(df_base)
    st.dataframe(estilo_tabela_excel(tabela), use_container_width=True, hide_index=True, key=f"{key_prefix}_principal")
    with st.expander("📋 DETALHES", expanded=False):
        st.dataframe(preparar_tabela_detalhes(df_base), use_container_width=True, hide_index=True, key=f"{key_prefix}_detalhes")

def botao_copiar_resposta(texto_resposta, key):
    import streamlit.components.v1 as components
    conteudo = texto(texto_resposta).replace("`", "\\`").replace("$", "\\$")
    components.html(
        f"""<button id='copy-{key}' style='padding:10px 14px;border-radius:10px;border:1px solid #38bdf8;background:#075985;color:white;font-weight:800;cursor:pointer;'>📋 COPIAR RESPOSTA</button>
<script>
const btn = document.getElementById('copy-{key}');
btn.onclick = async () => {{
  await navigator.clipboard.writeText(`{conteudo}`);
  btn.innerText = '✅ COPIADO';
  setTimeout(() => btn.innerText = '📋 COPIAR RESPOSTA', 1600);
}};
</script>""",
        height=52,
    )


def excel_bytes(df):
    out = BytesIO()

    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Mestre")

    return out.getvalue()


def responder_conversacao(pergunta, dados):
    if not pergunta or not pergunta.strip():
        return None, "Escolha ou digite uma pergunta para consultar o histórico."

    if dados.empty:
        return None, "Ainda não existem dados carregados para responder a pergunta."

    try:
        logger.info("Consulta da Conversação iniciada: %s", pergunta)
        dados_consulta = aplicar_cnpjs_clientes_cadastrados(dados, listar_clientes())
        return responder_pergunta_df(pergunta, dados_consulta), None
    except Exception:
        tb = traceback.format_exc()
        logger.error("Consulta da Conversação falhou: %s\n%s", pergunta, tb)
        return None, f"Erro ao responder a pergunta. Traceback completo:\n{tb}"




def renderizar_resposta_operacional(texto_mensagem: str, chave: str = "resposta_operacional") -> None:
    """Renderiza resposta operacional em caixa clara com botão para copiar."""
    texto_resposta = str(texto_mensagem or "")
    linhas_html = []
    for linha in texto_resposta.splitlines() or [""]:
        classe_linha = "operational-line"
        if re.match(r"^D\s", linha):
            classe_linha += " operational-delivery"
        elif re.match(r"^(L|C|FI)\s", linha):
            classe_linha += " operational-time-line"
        linhas_html.append(f'<div class="{classe_linha}">{escape(linha) or "&nbsp;"}</div>')
    texto_html = "".join(linhas_html)
    texto_js = texto_resposta.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    altura = max(170, min(520, 120 + 30 * max(1, texto_resposta.count("\n") + 1)))
    components.html(
        f"""
        <div class="operational-answer-box" id="{escape(chave)}">
            <button class="copy-operational-answer" type="button" onclick="navigator.clipboard.writeText(`{texto_js}`); this.textContent='✅ COPIADO'; setTimeout(() => this.textContent='📋 COPIAR', 1400);">📋 COPIAR</button>
            <div class="operational-answer-text">{texto_html}</div>
        </div>
        <style>
            .operational-answer-box {{
                box-sizing: border-box;
                width: 100%;
                margin: 0 0 10px;
                padding: 18px 18px 16px;
                border: 1px solid #D7E2F0;
                border-left: 6px solid #0B3A75;
                border-radius: 14px;
                background: #FFFFFF;
                color: #111827;
                box-shadow: 0 12px 28px rgba(15, 23, 42, 0.12);
                font-family: Arial, Helvetica, sans-serif;
            }}
            .operational-answer-text {{
                margin: 12px 0 0;
                color: #111827;
                font-family: Arial, Helvetica, sans-serif;
                font-size: 20px;
                font-weight: 800;
                line-height: 1.55;
            }}
            .operational-line {{ color: #111827; white-space: pre-wrap; overflow-wrap: anywhere; }}
            .operational-delivery, .operational-time-line {{ color: #0B3A75; }}
            .copy-operational-answer {{
                cursor: pointer;
                border: 0;
                border-radius: 10px;
                background: #0B3A75;
                color: #FFFFFF;
                padding: 10px 16px;
                font-size: 14px;
                font-weight: 900;
                letter-spacing: .02em;
            }}
        </style>
        """,
        height=altura,
    )

def renderizar_mensagem_conversacao(tipo: str, texto_mensagem: str, quando: str = "") -> None:
    """Renderiza perguntas e respostas com quebra de linha preservada."""
    if tipo != "user":
        renderizar_resposta_operacional(texto_mensagem, f"resposta_{abs(hash(str(texto_mensagem)))}")
        return
    titulo = "Pergunta"
    classe = "conversation-question"
    horario = f'<div class="conversation-time">{escape(quando)}</div>' if quando else ""
    st.markdown(
        f"""
        <div class="conversation-card {classe}">
            <div class="conversation-title">{titulo}</div>
            <div class="conversation-text">{escape(str(texto_mensagem))}</div>
            {horario}
        </div>
        """,
        unsafe_allow_html=True,
    )


def aplicar_css_profissional():
    st.markdown(
        """
        <style>
        :root {{
            --bg: #081A3A;
            --panel: rgba(10, 20, 40, 0.45);
            --panel-soft: rgba(255, 255, 255, 0.08);
            --border: rgba(255, 255, 255, 0.24);
            --text: #FFFFFF;
            --muted: #FFFFFF;
            --accent: #6ec6ff;
            --accent-2: #31d07c;
            --warning: #f59e0b;
            --danger: #ef4444;
        }}
        .stApp {{
            background:
                linear-gradient(rgba(5, 20, 50, 0.30), rgba(5, 20, 50, 0.30)),
                url("{logo_data_uri}");
            background-position: center center;
            background-repeat: no-repeat;
            background-size: min(94vw, 1320px) auto;
            background-attachment: fixed;
            background-color: #061733;
            color: var(--text);
        }}
        .stApp > header,
        .stApp [data-testid="stSidebar"],
        .stApp .main {{
            position: relative;
            z-index: 1;
        }}
        .stApp .main .block-container {{
            position: relative;
            z-index: 1;
            isolation: isolate;
        }}
        .stApp .main .block-container::before {{
            content: "";
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            background: radial-gradient(circle at center, rgba(20, 92, 176, 0.08), transparent 66%);
        }}
        .stApp .main .block-container > div {{
            position: relative;
            z-index: 1;
        }}
        [data-testid="stHeader"] {{ background: transparent; backdrop-filter: none; height: 1.45rem; }}

        /*
         * Streamlit mostra um estado global de execução durante reruns.
         * Mantemos apenas o widget discreto no topo direito e neutralizamos
         * qualquer camada/efeito visual que escureça ou bloqueie a página.
         */
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewBlockContainer"],
        .main,
        .main .block-container {{
            opacity: 1 !important;
            filter: none !important;
        }}
        [data-testid="stAppViewContainer"]::before,
        [data-testid="stAppViewContainer"]::after,
        [data-testid="stAppViewBlockContainer"]::before,
        [data-testid="stAppViewBlockContainer"]::after,
        .stApp::before,
        .stApp::after {{
            pointer-events: none !important;
            filter: none !important;
            box-shadow: none !important;
        }}
        [data-testid="stStatusWidget"] {{
            position: fixed !important;
            top: .48rem !important;
            right: .72rem !important;
            z-index: 999999 !important;
            width: auto !important;
            min-width: 2.35rem !important;
            height: 2.05rem !important;
            padding: .28rem .42rem !important;
            border-radius: 999px !important;
            border: 1px solid rgba(110,198,255,.28) !important;
            background: rgba(6,23,51,.52) !important;
            backdrop-filter: blur(8px) !important;
            -webkit-backdrop-filter: blur(8px) !important;
            box-shadow: 0 8px 22px rgba(0,0,0,.20) !important;
        }}
        [data-testid="stStatusWidget"] * {{
            color: #E0F2FE !important;
            background: transparent !important;
            box-shadow: none !important;
        }}
        [data-testid="stDecoration"] {{
            background: linear-gradient(90deg, transparent, rgba(110,198,255,.92), transparent) !important;
            height: 2px !important;
        }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, rgba(5,16,36,0.58) 0%, rgba(7,25,54,0.48) 58%, rgba(10,37,82,0.42) 100%);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-right: 1px solid rgba(125, 185, 255, 0.30);
            box-shadow: 12px 0 34px rgba(0, 0, 0, 0.18);
            min-width: 13.5rem !important;
            max-width: 13.5rem !important;
        }}
        [data-testid="stSidebar"] section {{ padding-top: .65rem; }}
        [data-testid="stSidebar"] .block-container {{ padding: .65rem .7rem 1rem; }}
        .main .block-container {{ padding: .75rem 1.15rem 1.25rem; max-width: 1480px; }}
        .block-container h1, .block-container h2, .block-container h3, .block-container p, .block-container label, .block-container span {{ color: #FFFFFF; text-shadow: 0 2px 5px rgba(0,0,0,.62); }}
        .block-container h1 {{ font-weight: 900; }}
        .block-container h2, .block-container h3 {{ letter-spacing: -.02em; margin-top: .65rem; margin-bottom: .45rem; font-weight: 850; background: transparent !important; }}
        .block-container h2 {{ font-size: 1.45rem; }}
        .block-container h3 {{ font-size: 1.16rem; }}
        div[data-testid="stVerticalBlock"] {{ gap: .55rem; }}
        div[data-testid="stHorizontalBlock"] {{ gap: .55rem; }}
        .app-hero {{
            display: flex; align-items: center; gap: .85rem;
            padding: .75rem .95rem; margin-bottom: .55rem;
            border: 1px solid var(--border); border-radius: .9rem;
            background: var(--panel);
            box-shadow: 0 18px 42px rgba(3,18,45,0.22);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
        }}
        .app-hero img {{ width: 3.2rem; height: 3.2rem; object-fit: contain; border-radius: .75rem; background: rgba(255,255,255,.96); padding: .28rem; box-shadow: 0 8px 22px rgba(3,18,45,.22); }}
        .app-hero h1 {{ margin: 0; font-size: clamp(1.25rem, 2.5vw, 1.75rem); letter-spacing: -0.04em; line-height: 1.15; }}
        .app-hero p {{ margin: .15rem 0 0; color: var(--muted); font-size: .86rem; }}
        .logged-user {{
            margin-left: auto;
            padding: .42rem .62rem;
            border: 1px solid rgba(49, 208, 124, .30);
            border-radius: 999px;
            background: rgba(15, 118, 110, .18);
            color: #ecfdf5;
            font-size: .82rem;
            white-space: nowrap;
        }}
        .metric-card, .nav-card {{
            height: 100%; padding: .72rem .78rem; border: 1px solid var(--border); border-radius: .85rem;
            background: var(--panel);
            box-shadow: 0 16px 34px rgba(3,18,45,0.18);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
        }}
        .metric-card .icon, .nav-card .icon {{ font-size: 1.05rem; line-height: 1; }}
        .metric-card .label {{ color: var(--muted); font-size: .74rem; margin-top: .25rem; line-height: 1.15; }}
        .metric-card .value {{ font-size: 1.55rem; font-weight: 900; margin-top: .05rem; color: #FFFFFF; line-height: 1.05; }}
        .metric-card .hint {{ color: #cbd5e1; font-size: .68rem; margin-top: .15rem; line-height: 1.2; }}
        .nav-card h3 {{ font-size: .92rem; margin: .32rem 0 .18rem; }}
        .nav-card p {{ color: var(--muted); font-size: .72rem; line-height: 1.25; margin: 0; min-height: 2.7em; }}

        .conversation-card {{
            margin: .55rem 0;
            padding: .85rem 1rem;
            border: 1px solid rgba(148, 203, 255, 0.30);
            border-radius: 1rem;
            background: rgba(5, 15, 35, 0.70);
            color: #FFFFFF;
            box-shadow: 0 18px 38px rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            overflow-wrap: anywhere;
        }}
        .conversation-question {{
            border-left: 4px solid rgba(110, 198, 255, 0.86);
        }}
        .conversation-answer {{
            border-left: 4px solid rgba(49, 208, 124, 0.86);
        }}
        .conversation-title {{
            margin-bottom: .38rem;
            color: #FFFFFF;
            font-weight: 900;
            letter-spacing: .01em;
            text-transform: uppercase;
            text-shadow: 0 2px 8px rgba(0, 0, 0, .74);
        }}
        .conversation-text {{
            color: #FFFFFF;
            font-size: .98rem;
            font-weight: 650;
            line-height: 1.65;
            white-space: pre-wrap;
            text-shadow: 0 2px 7px rgba(0, 0, 0, .72);
        }}
        .conversation-time {{
            margin-top: .48rem;
            color: rgba(226, 232, 240, .92);
            font-size: .78rem;
            font-weight: 700;
        }}

        .section-card {{ padding: .75rem; border: 1px solid var(--border); border-radius: .9rem; background: var(--panel); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); box-shadow: 0 16px 34px rgba(3,18,45,0.20); }}
        div.stButton > button {{
            border-radius: .68rem; min-height: 2.25rem; padding: .32rem .62rem; font-size: .86rem; font-weight: 700; border: 1px solid rgba(56,189,248,.22);
            background: linear-gradient(135deg, rgba(28, 84, 159, .72), rgba(12, 48, 105, .66)); color: #FFFFFF;
        }}
        div.stButton > button p {{ font-size: .86rem; }}
        [data-testid="stSidebar"] div.stButton > button {{ min-height: 2.05rem; justify-content: flex-start; border-radius: .62rem; font-size: .8rem; }}
        [data-testid="stSidebar"] div.stButton > button p {{ font-size: .8rem; }}
        .sidebar-auth-anchor {{
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: .35rem;
            margin: 0 0 .35rem;
            padding: 0;
        }}
        .sidebar-auth-anchor + div {{ margin-top: 0 !important; }}
        [data-testid="stSidebar"] div.stButton:has(button[aria-label="Entrar como administrador"]),
        [data-testid="stSidebar"] div.stButton:has(button[aria-label="Administrador autenticado"]) {{
            width: fit-content;
        }}
        [data-testid="stSidebar"] button[aria-label="Entrar como administrador"],
        [data-testid="stSidebar"] button[aria-label="Administrador autenticado"] {{
            width: 2rem;
            min-width: 2rem;
            min-height: 2rem;
            padding: 0;
            justify-content: center;
            border-radius: 999px;
            background: rgba(255, 255, 255, .08);
            border: 1px solid rgba(148, 163, 184, .34);
            box-shadow: none;
        }}
        [data-testid="stSidebar"] button[aria-label="Entrar como administrador"] p,
        [data-testid="stSidebar"] button[aria-label="Administrador autenticado"] p {{
            font-size: .88rem;
            line-height: 1;
            text-shadow: none;
        }}
        .admin-status-card {{
            margin: .1rem 0 .25rem;
            padding: .52rem .6rem;
            border-radius: .72rem;
            border: 1px solid rgba(49, 208, 124, .28);
            background: rgba(15, 118, 110, .16);
            color: #ecfdf5;
            font-size: .78rem;
            line-height: 1.2;
        }}
        div.stButton > button:hover {{ border-color: var(--accent); color: white; box-shadow: 0 0 0 2px rgba(56,189,248,.10); }}
        div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, #0284c7, #0369a1); border-color: #38bdf8; }}
        [data-testid="stDataFrame"] {{
            border: 1px solid rgba(110,198,255,.30) !important;
            border-radius: .86rem !important;
            overflow: hidden !important;
            box-shadow: 0 10px 26px rgba(0,0,0,.16) !important;
            background: rgba(5,16,36,.28) !important;
            backdrop-filter: blur(7px);
            -webkit-backdrop-filter: blur(7px);
        }}
        [data-testid="stDataFrame"] > div,
        [data-testid="stDataFrame"] section,
        [data-testid="stDataFrame"] div[class*="stDataFrame"],
        [data-testid="stDataFrame"] div[class*="dataframe"],
        [data-testid="stDataFrame"] div[class*="glide"],
        [data-testid="stDataFrame"] div[class*="dvn"],
        [data-testid="stDataFrame"] div[class*="data-grid"],
        [data-testid="stDataFrame"] [role="grid"],
        [data-testid="stDataFrame"] [role="rowgroup"],
        [data-testid="stDataFrame"] [role="row"],
        [data-testid="stDataFrame"] [role="gridcell"],
        [data-testid="stDataFrame"] [role="columnheader"] {{
            background-color: transparent !important;
            color: rgba(241,245,249,.96) !important;
            border-color: rgba(110,198,255,.15) !important;
        }}
        [data-testid="stDataFrame"] canvas {{
            background: rgba(5,16,36,.18) !important;
            color-scheme: dark !important;
        }}
        [data-testid="stDataFrame"] [class*="dvn-scroller"],
        [data-testid="stDataFrame"] [class*="scroll"],
        [data-testid="stDataFrame"] [data-testid*="scroll"] {{
            background: rgba(5,16,36,.16) !important;
            scrollbar-color: rgba(110,198,255,.48) rgba(5,16,36,.30) !important;
        }}
        [data-testid="stDataFrame"] input,
        [data-testid="stDataFrame"] textarea,
        [data-testid="stDataFrame"] [contenteditable="true"] {{
            background: rgba(8,35,78,.72) !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(110,198,255,.34) !important;
        }}

        /* Campos de pesquisa e formulários com vidro escuro para revelar a identidade ao fundo. */
        input, textarea, select,
        .stTextInput input, .stTextArea textarea, .stNumberInput input, .stDateInput input,
        div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{
            background: rgba(10,20,40,0.45) !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(110,198,255,0.42) !important;
            border-radius: .68rem !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 8px 24px rgba(0,0,0,0.12);
            caret-color: #FFFFFF;
            backdrop-filter: blur(7px);
            -webkit-backdrop-filter: blur(7px);
        }}
        input:focus, textarea:focus, select:focus,
        .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus, .stDateInput input:focus {{
            border-color: rgba(110,198,255,0.78) !important;
            box-shadow: 0 0 0 2px rgba(110,198,255,0.16), 0 8px 24px rgba(0,0,0,0.16) !important;
        }}
        input::placeholder, textarea::placeholder,
        .stTextInput input::placeholder, .stTextArea textarea::placeholder {{ color: rgba(226,232,240,0.82) !important; }}
        .stTextInput label, .stTextArea label, .stNumberInput label, .stDateInput label {{ color: #FFFFFF !important; font-weight: 800; }}
        div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"] {{
            background: rgba(10,20,40,0.96) !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(110,198,255,0.32) !important;
        }}
        div[role="option"] {{ color: #FFFFFF !important; background: transparent !important; }}
        div[role="option"]:hover {{ background: rgba(110,198,255,0.18) !important; }}

        /* Tabelas escuras e translúcidas, mantendo contraste em células e cabeçalhos. */
        [data-testid="stTable"], [data-testid="stDataFrame"], table {{ color: #FFFFFF !important; }}
        [data-testid="stTable"], .stDataFrame {{
            background: rgba(5,16,36,.24) !important;
            border-radius: .86rem !important;
        }}
        [data-testid="stTable"] table, table {{
            width: 100%;
            background: rgba(5,16,36,.22) !important;
            border-collapse: separate;
            border-spacing: 0;
            border: 1px solid rgba(110,198,255,.24);
            border-radius: .86rem;
            overflow: hidden;
            box-shadow: 0 10px 26px rgba(0,0,0,.14);
        }}
        [data-testid="stTable"] thead tr, [data-testid="stTable"] th, table thead tr, table th {{
            background: rgba(8,35,78,.68) !important;
            color: #FFFFFF !important;
            font-weight: 850;
            border-color: rgba(110,198,255,.22) !important;
        }}
        [data-testid="stTable"] tbody tr, table tbody tr {{ background: rgba(10,20,40,.34) !important; }}
        [data-testid="stTable"] tbody tr:nth-child(even), table tbody tr:nth-child(even) {{ background: rgba(15,31,58,.26) !important; }}
        [data-testid="stTable"] td, table td {{ color: rgba(241,245,249,.95) !important; border-color: rgba(110,198,255,.16) !important; }}
        .stDataFrame [role="grid"] {{ background-color: rgba(5,16,36,.18) !important; }}
        .stDataFrame [role="row"], .stDataFrame [role="gridcell"] {{
            background-color: rgba(10,20,40,.18) !important;
            color: rgba(241,245,249,.95) !important;
            border-color: rgba(110,198,255,.14) !important;
        }}
        .stDataFrame [role="row"]:nth-child(even), .stDataFrame [role="gridcell"]:nth-child(even) {{
            background-color: rgba(15,31,58,.14) !important;
        }}
        .stDataFrame [role="columnheader"] {{
            background-color: rgba(8,35,78,.70) !important;
            color: #FFFFFF !important;
            border-color: rgba(110,198,255,.22) !important;
            font-weight: 850 !important;
        }}
        .stAlert {{ border-radius: .8rem; border: 1px solid var(--border); padding: .55rem .75rem; background: rgba(10,20,40,.38); color: #FFFFFF; }}
        @media (max-width: 760px) {{
            .main .block-container {{ padding-left: .7rem; padding-right: .7rem; }}
            .app-hero {{ padding: .7rem .78rem; }}
            .app-hero h1 {{ font-size: 1.28rem; }}
            div[data-testid="column"] {{ width: 100% !important; flex: 1 1 100% !important; }}
            div.stButton > button {{ width: 100%; min-height: 2.75rem; font-size: .95rem; }}
            div.stButton > button p {{ font-size: .95rem; }}
            [data-testid="stDataFrame"] {{ overflow-x: auto; }}
        }}
        </style>
        """.format(logo_data_uri=LOGO_DATA_URI),
        unsafe_allow_html=True,
    )


PAGINAS = {
    "dashboard": {"label": "Dashboard", "icon": "📊", "grupo": "principal"},
    "busca": {"label": "Buscar / visualizar", "icon": "🔎", "grupo": "principal"},
    "conversacao": {"label": "Conversação", "icon": "💬", "grupo": "principal"},
    "rapida": {"label": "Atualização rápida", "icon": "⚡", "grupo": "principal"},
    "conversa": {"label": "Atualização por conversa", "icon": "🗣️", "grupo": "principal"},
    "ler_folha": {"label": "Ler folha", "icon": "📄", "grupo": "principal"},
    "importar": {"label": "Importar Excel mestre", "icon": "📥", "grupo": "principal"},
    "admin": {"label": "Excel Mestre", "icon": "📥", "grupo": "admin"},
    "regras_operacionais": {"label": "Regras Operacionais", "icon": "📋", "grupo": "admin"},
    "historico_alteracoes": {"label": "Backup / Histórico", "icon": "🕘", "grupo": "admin"},
    "clientes_cnpj": {"label": "Clientes e CNPJ", "icon": "🏢", "grupo": "admin"},
}


def ir_para_pagina(pagina):
    st.session_state["pagina_atual"] = pagina


def render_header():
    usuario_logado = texto(st.session_state.get("admin_usuario")) if st.session_state.get("admin_autenticado") else ""
    badge_usuario = (
        f'<div class="logged-user">Usuário logado: <strong>{escape(usuario_logado)}</strong></div>'
        if usuario_logado
        else ""
    )
    st.markdown(
        """
        <div class="app-hero">
            <img src="{LOGO_DATA_URI}" alt="Logo Controle Operacional">
            <div>
                <h1>Controle Operacional</h1>
                <p>Gestão de coletas, entregas, finalizações e observações</p>
            </div>
            {BADGE_USUARIO}
        </div>
        """.format(LOGO_DATA_URI=LOGO_DATA_URI, BADGE_USUARIO=badge_usuario),
        unsafe_allow_html=True,
    )


def render_menu(pagina_atual):
    with st.sidebar:
        st.markdown("### Navegação")
        for chave, pagina in PAGINAS.items():
            if pagina.get("grupo") != "principal":
                continue
            prefixo = "● " if chave == pagina_atual else ""
            if st.button(f"{prefixo}{pagina['icon']} {pagina['label']}", key=f"nav_{chave}", use_container_width=True):
                ir_para_pagina(chave)
                st.rerun()

        st.markdown("### ADMIN")
        for chave, pagina in PAGINAS.items():
            if pagina.get("grupo") != "admin":
                continue
            prefixo = "● " if chave == pagina_atual else ""
            if st.button(f"{prefixo}{pagina['icon']} {pagina['label']}", key=f"nav_{chave}", use_container_width=True):
                ir_para_pagina(chave)
                st.rerun()


def calcular_resumos(df_base):
    if df_base.empty:
        return {"total": 0, "sem_fi": 0, "bloqueio": 0, "deslocamento": 0, "sr": 0}, pd.Series(dtype="int64")
    obs = df_base.get("observacoes", pd.Series([""] * len(df_base))).fillna("").astype(str).str.upper()
    fi = df_base.get("f_horario", pd.Series([""] * len(df_base))).fillna("").astype(str).str.strip()
    sr = df_base.get("sr", pd.Series([""] * len(df_base))).fillna("").astype(str).str.strip()
    motoristas = df_base.get("motorista", pd.Series(dtype="object")).fillna("Sem motorista").replace("", "Sem motorista").value_counts()
    return {
        "total": len(df_base),
        "sem_fi": int((fi == "").sum()),
        "bloqueio": int(obs.str.contains("BLOQ", na=False).sum()),
        "deslocamento": int(obs.str.contains("DESLOC", na=False).sum()),
        "sr": int((sr != "").sum()),
    }, motoristas


def metric_card(icon, label, value, hint=""):
    st.markdown(
        f'<div class="metric-card"><div class="icon">{icon}</div><div class="label">{label}</div><div class="value">{value}</div><div class="hint">{hint}</div></div>',
        unsafe_allow_html=True,
    )


aplicar_css_profissional()
admin = autenticar_admin()
df = listar()
if "pagina_atual" not in st.session_state:
    st.session_state["pagina_atual"] = "dashboard"
pagina_atual = st.session_state["pagina_atual"]
render_menu(pagina_atual)
render_header()


if pagina_atual == "dashboard":
    resumo, total_por_motorista = calcular_resumos(df)

    st.markdown("### Visão geral da operação")
    cols = st.columns(5)
    with cols[0]:
        metric_card("🚚", "Total de coletas", resumo["total"], "Registros na base")
    with cols[1]:
        metric_card("⏱️", "Coletas sem FI", resumo["sem_fi"], "Pendentes de finalização")
    with cols[2]:
        metric_card("⛔", "Coletas com bloqueio", resumo["bloqueio"], "Observações de bloqueio")
    with cols[3]:
        metric_card("↔️", "Coletas com deslocamento", resumo["deslocamento"], "Ocorrências de deslocamento")
    with cols[4]:
        metric_card("🧾", "Coletas com SR", resumo["sr"], "Solicitações registradas")

    st.markdown("### Acesso rápido")
    nav_items = [
        ("busca", "🔎", "Buscar / visualizar", "Consultar, filtrar, editar e excluir registros."),
        ("conversacao", "💬", "Conversação", "Perguntas livres sobre os dados operacionais."),
        ("rapida", "⚡", "Atualização rápida", "Atualizar registros por abreviações."),
        ("conversa", "🗣️", "Atualização por conversa", "Interpretar frase natural e confirmar alteração."),
        ("ler_folha", "📄", "Ler folha", "Extrair dados de foto da folha operacional."),
        ("importar", "📥", "Importar Excel mestre", "Carregar planilha base para a nuvem."),
        ("admin", "📥", "Excel Mestre", "Exportação e rotinas administrativas."),
        ("regras_operacionais", "📋", "Regras Operacionais", "Consultar e manter regras de interpretação."),
        ("historico_alteracoes", "🕘", "Histórico de Alterações", "Auditar alterações das regras operacionais."),
    ]
    for linha in range(0, len(nav_items), 4):
        cols_nav = st.columns(4)
        for col, (chave, icon, titulo, desc) in zip(cols_nav, nav_items[linha:linha + 4]):
            with col:
                st.markdown(
                    f'<div class="nav-card"><div class="icon">{icon}</div><h3>{titulo}</h3><p>{desc}</p></div>',
                    unsafe_allow_html=True,
                )
                if st.button(f"Abrir {titulo}", key=f"card_{chave}", use_container_width=True):
                    ir_para_pagina(chave)
                    st.rerun()

    st.markdown("### Total por motorista")
    if total_por_motorista.empty:
        st.info("Nenhum registro encontrado para resumir por motorista.")
    else:
        df_motoristas = total_por_motorista.rename_axis("Motorista").reset_index(name="Total de coletas")
        st.dataframe(df_motoristas, use_container_width=True, hide_index=True)



if pagina_atual == "busca":
    st.subheader("Buscar na nuvem")

    q = st.text_input(
        "Pesquisar por delivery, SR, motorista, cliente, data ou unidade"
    )

    resultado = df.copy()

    if q and not df.empty:
        q_limpo = limpar_busca(q)
        parece_pergunta = q.strip().endswith("?") or any(
            termo in q_limpo
            for termo in [
                "QUANT", "QUAL", "QUAIS", "QUEM", "COLETAS", "REMESS", "SEM FI", "SEM C"
            ]
        )

        if parece_pergunta:
            try:
                resposta_pergunta = responder_pergunta_df(q, df)
                st.success(resposta_pergunta)
            except Exception:
                tb = traceback.format_exc()
                logger.error("Consulta da busca falhou: %s\n%s", q, tb)
                st.error("Erro ao interpretar pergunta. Traceback completo:")
                st.code(tb)
        else:
            q_upper = q.upper()
            resultado = df[
                df.apply(
                    lambda r: q_upper in " ".join([str(x).upper() for x in r.values]),
                    axis=1,
                )
            ]

    exibir_tabela_operacional(resultado, key_prefix="busca")

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
                    paletes_coletados = c8.text_input("PC", texto(item.get("paletes_coletados")), help="Paletes coletados")

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
                            "paletes_coletados": numero(paletes_coletados),
                            "valor_frete": numero(valor),
                            "l_horario": normalizar_horario(l_h) or None,
                            "c_horario": normalizar_horario(c_h) or None,
                            "f_horario": normalizar_horario(f_h) or None,
                            "tipo": tipo or None,
                            "status": calcular_status_automatico(observacoes, f_h),
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
                        registrar_historico_campos(TABELA_DELIVERIES, id_selecionado, item, registro, "ADMIN")

                        st.success("Registro atualizado.")

                if st.button("Excluir registro"):
                    supabase.table("deliveries").delete().eq(
                        "id",
                        id_selecionado
                    ).execute()
                    registrar_historico_campos(TABELA_DELIVERIES, id_selecionado, item, {"excluido": True}, "ADMIN")

                    st.warning("Registro excluído.")

        except Exception as e:
            st.error(f"Erro ao editar: {e}")


if pagina_atual == "conversacao":
    st.subheader("Conversação")
    st.info(
        "Digite uma pergunta livre para o assistente operacional calcular a resposta "
        "com base nos dados carregados. As perguntas programadas continuam como atalhos rápidos."
    )

    if "historico_conversacao" not in st.session_state:
        st.session_state["historico_conversacao"] = []

    pergunta_programada = st.selectbox(
        "Atalhos rápidos",
        PERGUNTAS_PROGRAMADAS,
    )

    pergunta_livre = st.text_input(
        "Pergunte ao assistente operacional",
        placeholder="Ex.: Mostre todas as coletas do cliente ASSAÍ.",
    )

    pergunta_escolhida = pergunta_livre.strip() or pergunta_programada

    col_responder, col_limpar, col_exemplo = st.columns([1, 1, 3])
    with col_responder:
        consultar = st.button("Responder", type="primary")
    with col_limpar:
        limpar_historico = st.button("Limpar histórico")
    with col_exemplo:
        st.caption(f"Pergunta que será enviada: {pergunta_escolhida}")

    if limpar_historico:
        st.session_state["historico_conversacao"] = []

    if consultar:
        resposta, erro = responder_conversacao(pergunta_escolhida, df)
        if erro:
            if erro.startswith("Erro ao responder a pergunta"):
                st.error("Erro ao responder a pergunta. Traceback completo:")
                st.code(erro)
            else:
                st.warning(erro)
        else:
            st.session_state["historico_conversacao"].append(
                {
                    "pergunta": pergunta_escolhida,
                    "resposta": resposta,
                    "quando": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                }
            )

    st.divider()
    st.caption("Histórico da conversa nesta sessão")
    if not st.session_state["historico_conversacao"]:
        st.write("Nenhuma pergunta feita nesta sessão.")
    for item in st.session_state["historico_conversacao"]:
        renderizar_mensagem_conversacao("user", item["pergunta"], item["quando"])
        renderizar_mensagem_conversacao("assistant", item["resposta"])
        botao_copiar_resposta(item["resposta"], f"conv_{abs(hash(item['quando'] + item['pergunta']))}")


if pagina_atual == "rapida":
    st.subheader("Atualização rápida")

    if not admin:
        st.warning("Apenas administradores podem usar a atualização rápida.")
    else:
        st.markdown(
            """
<style>
div[data-testid="stExpander"] details {
    background: rgba(0, 0, 0, 0.28);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
}
</style>
""",
            unsafe_allow_html=True,
        )
        with st.expander("ℹ️ Legendas e regras", expanded=False):
            st.markdown(
                """
Use uma atualização por linha.

#### Abreviações
- **M** = Motorista
- **D** = Delivery
- **SR** = SR
- **CL** = Cliente
- **P** = Paletes agendados
- **PC** = Paletes coletados
- **V** = Valor do frete
- **L** = Chegada
- **C** = Coleta
- **FI** = Finalização
- **O** = Observação
- **DATA** = Data
- **DF** = Data finalização

O site completa automaticamente CPF, cavalo e carreta quando o motorista for:
Jean, Wilson, Luis, Gabriel, Jones, Fabio, Argemiro ou Valdemir.

#### Regras importantes
- S.F e L.F ficam no CL, junto do cliente.
- FI recebe somente horário.
- B(HORÁRIO) na folha manuscrita vira FI HORÁRIO e O BLOQUEIO HORÁRIO.
- D(HORÁRIO) na folha manuscrita vira FI HORÁRIO e O DESLOCAMENTO HORÁRIO.
- Se existir FI normal e também B(HORÁRIO) ou D(HORÁRIO), B/D tem prioridade.
- Não usar campo S.
- O só deve ser usado para deslocamento, bloqueio, motivo ou remessa.
- Não usar O para HP, última ocorrência, finalizado ou em andamento.

#### Exemplos corretos
```text
M Jean D 3787760670 P 100 CL Atacadão CT Sul V 1021,05 L 08:51 C 10:51 FI —
M Jones D 3787780078 P 272 CL Drogaria São Paulo L.F V 992,17 L 07:33 C 09:59 FI —
M Fabio D 3787760662 P 200 CL Assaí Froes da Mota S.F V 1468,13 L 10:34 C 12:22 FI —
M Luis D 3402132015 P 476 CL JDE CAFÉ V 1276,13 O CS OK C OK L OK
D 3787762754 FI 11:03
M Jean D 3787805422 CL Mercantil L.F V 992,17 L 15:51 B(19:49)
M Fabio D 3787807939 CL C. Seis Irmãos V 1468,13 L 12:23 D(16:04)
```
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
                resumos = []

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

                        resumos.append(resumo_atualizacao_rapida(parsed, resultado))

                    except Exception as e:
                        erros.append(f"Linha {idx}: {e} — {linha}")

                if atualizados:
                    st.success(f"{atualizados} registro(s) atualizado(s).")
                if criados:
                    st.success(f"{criados} registro(s) criado(s).")
                if resumos:
                    st.write("Resumo por delivery:")
                    st.code("\n\n".join(resumos))
                if erros:
                    st.error("Algumas linhas não foram processadas:")
                    for erro in erros:
                        st.write(f"- {erro}")

                st.caption("Atualize a página ou volte na aba Buscar / editar para conferir os dados.")


if pagina_atual == "conversa":
    st.subheader("Atualização por conversa")

    if not admin:
        st.warning("Apenas administradores podem usar a atualização por conversa.")
    else:
        st.info(
            "Digite uma frase natural. A interpretação usa somente regras locais "
            "e a atualização só acontece depois da confirmação."
        )
        if st.session_state.get("conversa_registro_salvo"):
            st.success("Coleta atualizada com dados confirmados no banco principal.")
            st.code(st.session_state.pop("conversa_registro_salvo"))
        frase_conversa = st.text_input(
            "Frase da atualização ou consulta",
            placeholder="Jean finalizou 5422 mercantil às 19:49",
        )

        if st.button("Executar", type="primary"):
            st.session_state.pop("conversa_parsed", None)
            st.session_state.pop("conversa_resultados", None)
            st.session_state.pop("conversa_resposta_consulta", None)
            st.session_state.pop("conversa_modo", None)

            modo_conversa = detectar_modo_conversa(frase_conversa)
            st.session_state["conversa_modo"] = modo_conversa

            if modo_conversa == "CONSULTA":
                resposta, erro = responder_conversacao(frase_conversa, df)
                if erro:
                    st.error(erro)
                else:
                    st.session_state["conversa_resposta_consulta"] = resposta
            else:
                parsed, erro = parse_atualizacao_conversa(frase_conversa)
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
        modo_conversa = st.session_state.get("conversa_modo")
        resposta_consulta_conversa = st.session_state.get("conversa_resposta_consulta")

        if modo_conversa == "CONSULTA" and resposta_consulta_conversa:
            st.markdown("### MODO CONSULTA")
            renderizar_resposta_operacional(resposta_consulta_conversa, "consulta_conversa")

        if parsed_conversa and resultados_conversa:
            st.markdown("### MODO ATUALIZAÇÃO")
            campos_previstos = campos_atualizacao_conversa(parsed_conversa)
            resumo_campos = []
            if campos_previstos.get("motorista"):
                resumo_campos.append(f"M → {campos_previstos['motorista']}")
            if campos_previstos.get("cliente"):
                resumo_campos.append(f"CL → {campos_previstos['cliente']}")
            if campos_previstos.get("l_horario"):
                resumo_campos.append(f"L → {campos_previstos['l_horario']}")
            if campos_previstos.get("c_horario"):
                resumo_campos.append(f"C → {campos_previstos['c_horario']}")
            if campos_previstos.get("f_horario"):
                resumo_campos.append(f"FI → {campos_previstos['f_horario']}")
            if campos_previstos.get("data_finalizacao"):
                resumo_campos.append(f"DF → {campos_previstos['data_finalizacao']}")
            if campos_previstos.get("paletes_coletados") is not None and campos_previstos.get("paletes_coletados") != "":
                resumo_campos.append(f"PC → {numero_operacional_visual(campos_previstos['paletes_coletados'])}")
            st.write(
                "**Interpretação:** "
                f"delivery/remessa {parsed_conversa['final_delivery']} | "
                f"{'; '.join(resumo_campos)}."
            )

            if len(resultados_conversa) == 1:
                item = resultados_conversa[0]
                st.code(resumo_confirmacao_conversa(item, parsed_conversa))
                if parsed_conversa.get("observacoes"):
                    st.caption(f"Observações: {parsed_conversa['observacoes']}")

                if st.button("Confirmar alteração", key="confirmar_conversa_unica"):
                    registro_salvo = atualizar_conversa_no_supabase(item["id"], parsed_conversa)
                    st.session_state["conversa_registro_salvo"] = resumo_registro_salvo_conversa(registro_salvo)
                    st.session_state.pop("conversa_parsed", None)
                    st.session_state.pop("conversa_resultados", None)
                    st.rerun()
            else:
                df_resultados_conversa = pd.DataFrame(resultados_conversa)
                colunas_escolha = [
                    col
                    for col in ["delivery", "motorista", "cliente", "data", "f_horario"]
                    if col in df_resultados_conversa.columns
                ]
                tabela_escolha = df_resultados_conversa[colunas_escolha].rename(
                    columns={
                        "delivery": "D",
                        "motorista": "MOTORISTA",
                        "cliente": "CLIENTE",
                        "data": "DATA",
                        "f_horario": "FI ATUAL",
                    }
                )
                st.warning("Mais de uma coleta encontrada. Escolha uma antes de atualizar.")
                st.dataframe(tabela_escolha, use_container_width=True, hide_index=True)

                opcoes = {
                    f"D {texto(item.get('delivery'))} | {texto(item.get('motorista'))} | "
                    f"{texto(item.get('cliente'))} | DATA {texto(item.get('data'))} | "
                    f"FI {texto(item.get('f_horario')) or '—'}": item
                    for item in resultados_conversa
                }
                escolha = st.selectbox("Selecione a coleta para atualizar", list(opcoes.keys()))
                item_escolhido = opcoes[escolha]
                st.code(resumo_confirmacao_conversa(item_escolhido, parsed_conversa))
                if parsed_conversa.get("observacoes"):
                    st.caption(f"Observações: {parsed_conversa['observacoes']}")

                if st.button("Confirmar alteração", key="confirmar_conversa_multipla"):
                    registro_salvo = atualizar_conversa_no_supabase(item_escolhido["id"], parsed_conversa)
                    st.session_state["conversa_registro_salvo"] = resumo_registro_salvo_conversa(registro_salvo)
                    st.session_state.pop("conversa_parsed", None)
                    st.session_state.pop("conversa_resultados", None)
                    st.rerun()


if pagina_atual == "ler_folha":
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

        erro_imagem = None
        imagem_bytes = None

        if arquivo_folha:
            imagem_bytes, _, erro_imagem = validar_imagem_gemini(arquivo_folha)

            if erro_imagem:
                st.error(erro_imagem)

        imagem_final_bytes = None
        imagem_final_mime = "image/png"

        if arquivo_folha and not erro_imagem:
            modo_celular, largura_cropper = detectar_modo_celular_ler_folha()
            imagem_original = ImageOps.exif_transpose(Image.open(BytesIO(imagem_bytes))).convert("RGB")

            st.markdown("**Preparar imagem antes da leitura**")
            if modo_celular:
                rotacao_atual = st.session_state.get("rotacao_ler_folha_mobile", 0)
                if st.button("↶ Girar esquerda", key="girar_esquerda_ler_folha"):
                    rotacao_atual = (rotacao_atual + 90) % 360
                    st.session_state["rotacao_ler_folha_mobile"] = rotacao_atual
                    st.rerun()
                if st.button("↷ Girar direita", key="girar_direita_ler_folha"):
                    rotacao_atual = (rotacao_atual - 90) % 360
                    st.session_state["rotacao_ler_folha_mobile"] = rotacao_atual
                    st.rerun()
                rotacao = rotacao_atual
            else:
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
            chave_corte = f"{arquivo_folha.name}_{arquivo_folha.size}_{rotacao}_{'mobile' if modo_celular else 'desktop'}"
            chave_imagem_usada = f"imagem_cortada_ler_folha_{chave_corte}"
            chave_usar_inteira = f"usar_imagem_inteira_ler_folha_{chave_corte}"

            if modo_celular and chave_usar_inteira not in st.session_state and chave_imagem_usada not in st.session_state:
                st.session_state[chave_usar_inteira] = True

            if modo_celular:
                st.caption(
                    "Ajuste o corte por porcentagem. A prévia abaixo atualiza em tempo real "
                    "e o Gemini receberá a imagem selecionada pelos botões."
                )

                chaves_sliders = {
                    "topo": f"corte_topo_ler_folha_{chave_corte}",
                    "baixo": f"corte_baixo_ler_folha_{chave_corte}",
                    "esquerda": f"corte_esquerda_ler_folha_{chave_corte}",
                    "direita": f"corte_direita_ler_folha_{chave_corte}",
                }

                if st.button("Resetar corte", key=f"resetar_corte_{chave_corte}"):
                    for chave_slider in chaves_sliders.values():
                        st.session_state[chave_slider] = 0
                    st.session_state.pop(chave_imagem_usada, None)
                    st.session_state[chave_usar_inteira] = True
                    st.success("Corte resetado. A imagem inteira está selecionada para a leitura.")
                    st.rerun()

                corte_topo = st.slider("Cortar topo", 0, 50, 0, 1, format="%d%%", key=chaves_sliders["topo"])
                corte_baixo = st.slider("Cortar baixo", 0, 50, 0, 1, format="%d%%", key=chaves_sliders["baixo"])
                corte_esquerda = st.slider("Cortar esquerda", 0, 50, 0, 1, format="%d%%", key=chaves_sliders["esquerda"])
                corte_direita = st.slider("Cortar direita", 0, 50, 0, 1, format="%d%%", key=chaves_sliders["direita"])

                imagem_cortada_preview = recortar_imagem_por_percentuais(
                    imagem_girada,
                    topo=corte_topo,
                    baixo=corte_baixo,
                    esquerda=corte_esquerda,
                    direita=corte_direita,
                )

                st.image(
                    imagem_cortada_preview,
                    caption="Prévia da imagem cortada",
                    use_container_width=True,
                )

                if st.button("Usar imagem cortada", key=f"usar_imagem_cortada_{chave_corte}"):
                    st.session_state[chave_imagem_usada] = imagem_para_png_bytes(imagem_cortada_preview)
                    st.session_state[chave_usar_inteira] = False
                    st.success("Imagem cortada selecionada para a leitura.")

                if st.button("Usar imagem inteira", key=f"usar_imagem_inteira_{chave_corte}"):
                    st.session_state[chave_usar_inteira] = True
                    st.session_state.pop(chave_imagem_usada, None)
                    st.success("Imagem inteira selecionada para a leitura.")
            else:
                st.caption(
                    "Confira a imagem completa. Se precisar, use o cropper abaixo. "
                    "A prévia é reduzida apenas para caber na tela; o arquivo enviado ao Gemini "
                    "mantém a proporção e usa o corte na resolução original."
                )

                st.image(
                    imagem_girada,
                    caption="Imagem completa",
                    use_container_width=True,
                )

                if st.button("✅ Usar imagem inteira", key=f"usar_imagem_inteira_{chave_corte}"):
                    st.session_state[chave_usar_inteira] = True
                    st.session_state.pop(chave_imagem_usada, None)
                    st.success("Imagem inteira selecionada para a leitura.")

                imagem_cropper, escala_cropper = redimensionar_imagem_para_cropper(
                    imagem_girada,
                    largura_maxima=largura_cropper,
                )

                with st.expander("✂️ Cortar imagem", expanded=True):
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
                        caption="Imagem cortada (prévia abaixo da imagem)",
                        use_container_width=True,
                    )

                    if st.button("✂️ Cortar imagem", key=f"usar_imagem_cortada_{chave_corte}"):
                        st.session_state[chave_imagem_usada] = imagem_para_png_bytes(imagem_cortada_preview)
                        st.session_state[chave_usar_inteira] = False
                        st.success("Imagem cortada selecionada para a leitura.")

            if chave_imagem_usada in st.session_state and not st.session_state.get(chave_usar_inteira, False):
                imagem_final_bytes = st.session_state[chave_imagem_usada]
                imagem_final = Image.open(BytesIO(imagem_final_bytes)).convert("RGB")
                legenda_final = "Imagem final cortada que será analisada pelo Gemini"
            else:
                imagem_final = imagem_girada
                imagem_final_bytes = imagem_para_png_bytes(imagem_final)
                legenda_final = "Imagem final inteira que será analisada pelo Gemini"

            st.image(imagem_final, caption=legenda_final, use_container_width=True)

        imagem_pronta = imagem_final_bytes is not None

        if st.button("🤖 Ler com Gemini", disabled=not imagem_pronta):
            if not imagem_pronta:
                st.warning("Envie e prepare uma imagem antes de interpretar.")
            elif not obter_gemini_api_keys():
                st.error(
                    "Configure GEMINI_API_KEY ou GEMINI_API_KEY_2 em st.secrets "
                    "para usar a leitura automática."
                )
            elif erro_imagem:
                st.error(erro_imagem)
            elif not st.session_state.get("gemini_teste_ok", False):
                st.warning("Clique em Testar Gemini e confirme que o teste simples funciona antes de ler a imagem.")
            else:
                with st.spinner("Interpretando a folha com Gemini 2.5 Flash..."):
                    try:
                        texto_interpretado, modelo_usado, api_usada = interpretar_folha_com_gemini(
                            imagem_final_bytes,
                            imagem_final_mime,
                        )
                    except Exception as e:
                        mostrar_erro_gemini(e)
                    else:
                        st.session_state["resposta_original_gemini_ler_folha"] = texto_interpretado
                        st.session_state["previa_ler_folha"] = texto_interpretado
                        st.success(f"Folha interpretada com {modelo_usado}. {api_usada}.")

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
                resumos = []

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
                    resumos.append(resumo_atualizacao_rapida(parsed, resultado))

                st.success("Processamento concluído.")
                st.write(f"Registros criados: {criados}")
                st.write(f"Registros atualizados: {atualizados}")
                st.write(f"Linhas com erro: {len(erros)}")
                if resumos:
                    st.write("Resumo por delivery:")
                    st.code("\n\n".join(resumos))

                if erros:
                    st.error("Erros encontrados:")
                    for erro in erros:
                        st.write(f"- {erro}")


if pagina_atual == "importar":
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


if pagina_atual == "regras_operacionais":
    render_regras_operacionais(admin)


if pagina_atual == "historico_alteracoes":
    st.subheader("Backup / Histórico")
    if not admin:
        st.warning("Entre como administrador para acessar o histórico de alterações.")
    else:
        historico_sistema = pd.DataFrame(supabase.table(TABELA_AUDITORIA).select("*").execute().data or [])
        if not historico_sistema.empty:
            st.caption("Alterações do sistema com usuário, data/hora, valor antigo e valor novo.")
            st.dataframe(historico_sistema.iloc[::-1], use_container_width=True, hide_index=True)
        historico_regras = carregar_historico_regras()
        if historico_regras.empty and historico_sistema.empty:
            st.info("Nenhuma alteração registrada ainda.")
        if not historico_regras.empty:
            st.caption("Histórico de regras com data, hora, usuário, ação e tamanho da versão salva.")
            st.dataframe(
                historico_regras.drop(columns=["conteudo"], errors="ignore").iloc[::-1],
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "⬇️ Baixar histórico completo",
                data=historico_regras.to_csv(index=False).encode("utf-8"),
                file_name="historico_regras_operacionais.csv",
                mime="text/csv",
                use_container_width=True,
            )


if pagina_atual == "clientes_cnpj":
    render_clientes_cnpj(admin)


if pagina_atual == "admin":
    st.subheader("Excel Mestre")

    if not admin:
        st.warning("Entre como administrador para acessar as funções administrativas.")
    else:
        df_atual = listar()

        st.write(f"Registros na nuvem: {len(df_atual)}")
        st.markdown("### Visualizar e pesquisar registros")
        f1, f2, f3, f4 = st.columns(4)
        filtro_data = f1.text_input("Pesquisar por data", key="admin_filtro_data")
        filtro_motorista = f2.text_input("Pesquisar por motorista", key="admin_filtro_motorista")
        filtro_cliente = f3.text_input("Pesquisar por cliente", key="admin_filtro_cliente")
        filtro_delivery = f4.text_input("Pesquisar por delivery", key="admin_filtro_delivery")
        df_filtrado = df_atual.copy()
        for coluna, valor in [("data", filtro_data), ("motorista", filtro_motorista), ("cliente", filtro_cliente), ("delivery", filtro_delivery)]:
            if valor and coluna in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado[coluna].fillna("").astype(str).str.upper().str.contains(valor.upper(), na=False)]
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Baixar Excel mestre",
            data=excel_bytes(df_filtrado),
            file_name="excel_mestre_operacional.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.divider()
        st.subheader("Padronizar nomes antigos")
        st.caption(
            "Corrige somente o campo MOTORISTA/M quando o registro antigo está salvo "
            "apenas com o primeiro nome. Cliente, observação e nomes já completos não são alterados."
        )

        preview_motoristas = preview_padronizacao_motoristas(df_atual)
        st.write(f"Registros que serão alterados: {len(preview_motoristas)}")

        if preview_motoristas.empty:
            st.info("Nenhum motorista antigo sem sobrenome encontrado para padronizar.")
        else:
            st.dataframe(
                preview_motoristas.rename(
                    columns={
                        "id": "ID",
                        "antes": "Antes",
                        "depois": "Depois",
                        "delivery": "Delivery",
                        "cliente": "Cliente",
                        "data": "Data",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption("Exemplo da correção: JEAN → JEAN ROBSON; FABIO → FABIO SOUZA.")

            if st.button("Confirmar padronização", type="primary"):
                total = aplicar_padronizacao_motoristas(preview_motoristas)
                st.success(
                    f"{total} registro(s) atualizado(s) no Supabase. "
                    "Baixe novamente o Excel mestre para obter a planilha corrigida."
                )
                st.rerun()

        st.divider()
        st.subheader("Atualizar status automaticamente")
        st.caption(
            "Recalcula somente o campo STATUS pela regra oficial: "
            "DESLOCAMENTO, BLOQUEIO, FINALIZADO ou EM ABERTO."
        )

        preview_status = preview_atualizacao_status(df_atual)
        resumo_status = resumo_preview_status(preview_status)
        c_status1, c_status2, c_status3, c_status4 = st.columns(4)
        c_status1.metric("DESLOCAMENTO", resumo_status["DESLOCAMENTO"])
        c_status2.metric("BLOQUEIO", resumo_status["BLOQUEIO"])
        c_status3.metric("FINALIZADO", resumo_status["FINALIZADO"])
        c_status4.metric("EM ABERTO", resumo_status["EM ABERTO"])

        alteracoes_status = preview_status[
            preview_status["status_atual"].fillna("") != preview_status["status_novo"].fillna("")
        ] if not preview_status.empty else preview_status
        st.write(f"Registros que terão STATUS alterado: {len(alteracoes_status)}")

        if not alteracoes_status.empty:
            st.dataframe(
                alteracoes_status.rename(columns={
                    "id": "ID",
                    "status_atual": "STATUS atual",
                    "status_novo": "STATUS novo",
                    "delivery": "Delivery",
                    "cliente": "Cliente",
                    "f_horario": "FINALIZADO",
                    "observacoes": "O/Observações",
                }),
                use_container_width=True,
                hide_index=True,
            )

        if st.button("Confirmar atualização automática de status", type="primary"):
            total = aplicar_atualizacao_status(preview_status)
            st.success(
                f"{total} registro(s) atualizado(s) no Supabase. "
                "Baixe novamente o Excel mestre para obter a planilha com STATUS recalculado."
            )
            st.rerun()

        st.divider()
        st.subheader("Trocar ano das datas para 2026")
        st.caption("Atualiza somente os campos de data existentes, sem alterar a estrutura do banco e sem reorganizar IDs.")

        if st.button("Trocar ano das datas para 2026", type="primary"):
            total = atualizar_datas_para_2026()
            st.success(f"{total} registro(s) com datas ajustadas para 2026.")

        st.dataframe(df_atual, use_container_width=True, hide_index=True)
