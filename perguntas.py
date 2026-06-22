"""Perguntas simples sobre o histórico de coletas.

Este módulo não usa APIs externas nem modelos de IA. Ele carrega dados locais
(CSV, Excel ou SQLite) com pandas e responde por regras de palavras-chave.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

import pandas as pd


logger = logging.getLogger(__name__)

COLUNAS_PADRAO = {
    "data": "data",
    "date": "data",
    "dt": "data",
    "data coleta": "data",
    "data_coleta": "data",
    "data finalizacao": "data_finalizacao",
    "data finalização": "data_finalizacao",
    "data_finalizacao": "data_finalizacao",
    "df": "data_finalizacao",
    "motorista": "motorista",
    "driver": "motorista",
    "delivery": "delivery",
    "documento": "delivery",
    "doc": "delivery",
    "remessa": "delivery",
    "remessas": "delivery",
    "sr": "sr",
    "cliente": "cliente",
    "tipo veiculo": "tipo_veiculo",
    "tipo_veiculo": "tipo_veiculo",
    "veiculo": "tipo_veiculo",
    "veículo": "tipo_veiculo",
    "tipo": "tipo_veiculo",
    "tipo veiculo usado": "tipo_veiculo",
    "carreta": "tipo_veiculo",
    "status": "status",
    "pc": "pc",
    "paletes coletados": "pc",
    "pallets coletados": "pc",
    "valor": "valor_frete",
    "frete": "valor_frete",
    "valor frete": "valor_frete",
    "valor_frete": "valor_frete",
    "l": "l_horario",
    "chegada": "l_horario",
    "l_horario": "l_horario",
    "c": "c_horario",
    "coleta": "c_horario",
    "c_horario": "c_horario",
    "fi": "f_horario",
    "f": "f_horario",
    "finalizacao": "f_horario",
    "finalização": "f_horario",
    "f_horario": "f_horario",
    "observacao": "observacoes",
    "observação": "observacoes",
    "observacoes": "observacoes",
    "observações": "observacoes",
    "cidade": "cidade",
    "cnpj": "cnpj",
    "obs": "observacoes",
    "o": "observacoes",
}

COLUNAS_NECESSARIAS = [
    "data",
    "motorista",
    "delivery",
    "sr",
    "cliente",
    "valor_frete",
    "c_horario",
    "f_horario",
    "observacoes",
    "tipo_veiculo",
    "status",
    "paletes",
    "pc",
    "l_horario",
    "data_finalizacao",
    "cidade",
    "cnpj",
]


def _sem_acentos(texto: object) -> str:
    valor = "" if texto is None or pd.isna(texto) else str(texto)
    valor = unicodedata.normalize("NFKD", valor)
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return valor.upper().strip()


MOTIVOS_DESLOCAMENTO = [
    "SEM CARGA",
    "CLIENTE FECHADO",
    "AGUARDANDO AGENDAMENTO",
    "FALTA DE MERCADORIA",
    "RECUSA DE RECEBIMENTO",
]
MOTIVOS_BLOQUEIO = [
    "CLIENTE FECHADO",
    "AGUARDANDO AGENDAMENTO",
    "SEM JANELA DE RECEBIMENTO",
    "RECUSA DE RECEBIMENTO",
    "FALTA DE MERCADORIA",
]


def normalizar_observacao_operacional(valor: object) -> str | None:
    """Normaliza observações de SR/reembolso, deslocamento e bloqueio por regras simples."""
    obs_original = "" if valor is None else str(valor).strip()
    obs = _sem_acentos(obs_original)
    if not obs:
        return None
    if re.match(r"^F\s+[0-2]?\d:[0-5]\d\s+O\s+", obs):
        return obs_original.upper()
    if obs.startswith("O ") and ("BLOQUEIO" in obs or "DESLOCAMENTO" in obs or "SR" in obs or "REEMB" in obs):
        return obs_original.upper()

    horario = None
    marcado_horario = re.search(r"(?<!\w)([BD])\s*\(\s*([0-2]?\d)[:hH]([0-5]\d)\s*\)", obs)
    if marcado_horario:
        horario = f"{marcado_horario.group(2).zfill(2)}:{marcado_horario.group(3)}"
        motivo = re.sub(r"(?<!\w)[BD]\s*\(\s*[0-2]?\d[:hH][0-5]\d\s*\)", " ", obs).strip(" -:")
        motivo = re.sub(r"\s+", " ", motivo)
        return f"F {horario} O {motivo + ' ' if motivo else ''}BLOQUEIO ÀS {horario}"

    sr_match = re.search(r"\bSR\s*(\d{3,})\b", obs)
    if sr_match and ("REEMB" in obs or "REEMBOLSO" in obs):
        return f"O SR {sr_match.group(1)} REEMBOLSO"
    if re.search(r"\bS\.?R\b", obs) or "REEMB" in obs or "SOLICITACAO DE REEMBOLSO" in obs:
        return "O SR/REEMBOLSO"

    tem_deslocamento = "DESLOC" in obs
    if tem_deslocamento:
        for motivo in MOTIVOS_DESLOCAMENTO:
            if motivo in obs:
                return f"O DESLOCAMENTO {motivo}"
        return "O DESLOCAMENTO"

    tem_bloqueio = re.search(r"\bBLOQ(?:UEIO)?\b", obs) is not None
    if tem_bloqueio or any(motivo in obs for motivo in MOTIVOS_BLOQUEIO):
        for motivo in MOTIVOS_BLOQUEIO:
            if motivo in obs:
                return f"O BLOQUEIO {motivo}"
        return "O BLOQUEIO"

    if any(motivo in obs for motivo in MOTIVOS_DESLOCAMENTO):
        for motivo in MOTIVOS_DESLOCAMENTO:
            if motivo in obs:
                return f"O DESLOCAMENTO {motivo}"
        return "O DESLOCAMENTO"

    return None


def _chave_coluna(coluna: object) -> str:
    return _sem_acentos(coluna).lower().replace("_", " ").strip()


def _valor_vazio(valor: object) -> bool:
    if valor is None or pd.isna(valor):
        return True
    texto = str(valor).strip()
    return texto == "" or texto.lower() in {"nan", "none", "null", "<na>", "-", "—"}


def _normalizar_motorista(valor: object) -> str:
    nome = _sem_acentos(valor)
    conhecidos = {
        "WILSON": "WILSON REIS",
        "FABIO": "FABIO SOUZA",
        "LUIS": "LUIS CARLOS",
        "ARGEMIRO": "ARGEMIRO BORGES",
        "JEAN": "JEAN ROBSON",
        "JONES": "JONES ROSARIO",
        "GABRIEL": "GABRIEL BORGES",
        "VALDEMIR": "VALDEMIR DE JESUS",
    }
    for trecho, nome_completo in conhecidos.items():
        if trecho in nome:
            return nome_completo
    return nome



SIGLAS_MOTORISTAS = {
    "JONES": "@JO",
    "JONES ROSARIO": "@JO",
    "JEAN": "@JE",
    "JEAN ROBSON": "@JE",
    "GABRIEL": "@GA",
    "GABRIEL BORGES": "@GA",
    "FABIO": "@FA",
    "FABIO SOUZA": "@FA",
    "ARGEMIRO": "@AR",
    "ARGEMIRO BORGES": "@AR",
    "ARIEL": "@AI",
    "ARIEL NASCIMENTO": "@AI",
    "WILSON": "@WI",
    "WILSON REIS": "@WI",
    "LUIS": "@LU",
    "LUIS CARLOS": "@LU",
}


def _sigla_motorista(valor: object) -> str:
    nome = _normalizar_motorista(valor)
    return SIGLAS_MOTORISTAS.get(nome, f"@{nome[:2]}" if nome else "@--")


ABREVIACOES_LOCALIDADE = {
    "L.F": "LAURO DE FREITAS",
    "LF": "LAURO DE FREITAS",
    "S.F": "SIMOES FILHO",
    "SF": "SIMOES FILHO",
    "F.S": "FEIRA DE SANTANA",
    "FS": "FEIRA DE SANTANA",
    "S.G": "SAO GONCALO",
    "SG": "SAO GONCALO",
}

LOCALIDADES_WMS_COM_PARENTES = ("BARROS REIS", "LAURO DE FREITAS")


def _expandir_abreviacoes_localidade(texto: str) -> str:
    for abreviacao, localidade in ABREVIACOES_LOCALIDADE.items():
        texto = re.sub(rf"(?<!\w){re.escape(abreviacao)}(?!\w)", localidade, texto)
    return texto


def _normalizar_nome_exibicao_cliente(cliente: str, cidade: str = "") -> str:
    cliente = _expandir_abreviacoes_localidade(re.sub(r"\s+", " ", cliente).strip())
    cidade = _expandir_abreviacoes_localidade(re.sub(r"\s+", " ", cidade).strip())

    if cliente.startswith("WMS"):
        cliente = re.sub(r"^WMS\s*\((MAX\s+ATACADO)(?:\s+(.+?))?\)$", r"WMS \1 (\2)", cliente).strip()
        cliente = re.sub(r"\s+\)", ")", cliente)
        cliente = re.sub(r"\(\s*([^()]+?)\s*\)", lambda m: f"({_expandir_abreviacoes_localidade(m.group(1).strip())})", cliente)
        if cidade and f"({cidade})" not in cliente:
            return f"{cliente} ({cidade})"
        for localidade in LOCALIDADES_WMS_COM_PARENTES:
            sufixo = f" {localidade}"
            if cliente.endswith(sufixo) and f"({localidade})" not in cliente:
                return f"{cliente[:-len(sufixo)]} ({localidade})"
        return cliente

    if not cidade and cliente:
        partes = cliente.split()
        bases = {"ASSAI", "ATAKAREJO", "GMF", "MERCANTIL"}
        if len(partes) > 1 and partes[0] in bases:
            cliente, cidade = partes[0], " ".join(partes[1:])

    if cliente == "ASSAI":
        cliente = "ASSAÍ"

    return f"{cliente} ({cidade})" if cidade else cliente


def _cliente_cidade_formatado(row: pd.Series) -> str:
    cliente = _sem_acentos(row.get("cliente"))
    cidade = _sem_acentos(row.get("cidade"))
    return _normalizar_nome_exibicao_cliente(cliente, cidade)


def _texto_valido(valor: object) -> str:
    """Converte valores escalares opcionais para texto sem avaliar pandas.NA como booleano."""
    return "" if _valor_vazio(valor) else str(valor).strip()


def formatar_linha_coleta_motorista(row: pd.Series) -> str:
    """Formata coletas para a aba Conversação: DELIVERY - CLIENTE - @SIGLA."""
    delivery = _texto_valido(row.get("delivery")) or _texto_valido(row.get("sr"))
    return f"{delivery} - {_cliente_cidade_formatado(row)} - {_sigla_motorista(row.get('motorista'))}"


def _linha_coleta_admin(row: pd.Series, incluir_cnpj: bool = False) -> str:
    linha = formatar_linha_coleta_motorista(row)
    cnpj = _texto_valido(row.get("cnpj"))
    if incluir_cnpj and cnpj:
        linha += f"\n\nCNPJ: {cnpj}"
    return linha


def _conferencia_coletas_admin(base: pd.DataFrame, linhas: list[str]) -> list[str]:
    total_encontrado = len(base)
    total_exibido = len(linhas)
    conferencia = [
        f"REGISTROS ENCONTRADOS: {total_encontrado}",
        f"REGISTROS EXIBIDOS: {total_exibido}",
    ]
    if total_exibido < total_encontrado:
        deliveries_exibidos = {
            _texto_valido(row.get("delivery")) or _texto_valido(row.get("sr"))
            for _, row in base.iloc[:total_exibido].iterrows()
        }
        ignorados = []
        for _, row in base.iterrows():
            delivery = _texto_valido(row.get("delivery")) or _texto_valido(row.get("sr")) or "SEM DELIVERY/SR"
            if delivery not in deliveries_exibidos:
                ignorados.append(f"{delivery} - motivo: registro encontrado no período, mas não foi exibido na resposta")
        if ignorados:
            conferencia.extend(["", "DELIVERIES IGNORADOS:", *ignorados])
    return conferencia


def _responder_coletas_motorista_periodo(df: pd.DataFrame, pergunta: str) -> str:
    base = _aplicar_periodo_operacional(df, pergunta)
    if base.empty:
        return "Nenhuma coleta encontrada para o período informado."
    linhas = [formatar_linha_coleta_motorista(row) for _, row in base.iterrows()]
    return "\n".join(linhas)


def _responder_coletas_hoje_admin(df: pd.DataFrame) -> str:
    base = _periodo_hoje(df)
    if base.empty:
        return "Nenhuma coleta encontrada para hoje."
    linhas = [_linha_coleta_admin(row, incluir_cnpj=True) for _, row in base.iterrows()]
    return "\n".join(linhas)

def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    logger.debug("Normalizando dataframe para perguntas. Colunas originais: %s", list(df.columns))
    mapa = {}
    for coluna in df.columns:
        chave = _chave_coluna(coluna)
        if chave in COLUNAS_PADRAO:
            mapa[coluna] = COLUNAS_PADRAO[chave]
    df = df.rename(columns=mapa).copy()
    if df.columns.duplicated().any():
        duplicadas = df.columns[df.columns.duplicated()].unique().tolist()
        logger.warning("Colunas duplicadas após normalização: %s. Unindo valores não vazios.", duplicadas)
        colunas_unidas = {}
        for coluna in dict.fromkeys(df.columns):
            valores = df.loc[:, df.columns == coluna]
            if isinstance(valores, pd.Series) or valores.shape[1] == 1:
                colunas_unidas[coluna] = valores.squeeze(axis=1)
            else:
                colunas_unidas[coluna] = valores.bfill(axis=1).iloc[:, 0]
        df = pd.DataFrame(colunas_unidas, index=df.index)
    logger.debug("Mapa de colunas aplicado: %s. Colunas normalizadas: %s", mapa, list(df.columns))
    for coluna in COLUNAS_NECESSARIAS:
        if coluna not in df.columns:
            logger.warning("Coluna ausente após normalização: %s. Criando coluna vazia para manter consulta.", coluna)
            df[coluna] = pd.NA
    df["data"] = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)
    df["motorista"] = df["motorista"].apply(_normalizar_motorista)
    df["valor_frete"] = df["valor_frete"].apply(_numero)
    df["tipo_veiculo"] = df["tipo_veiculo"].apply(lambda v: _sem_acentos(v))
    df["observacoes"] = df["observacoes"].apply(lambda v: normalizar_observacao_operacional(v) or (_sem_acentos(v) if not _valor_vazio(v) else ""))
    df["status"] = df["status"].apply(lambda v: _sem_acentos(v) if not _valor_vazio(v) else "")
    return df


def _numero(valor: object) -> float:
    if _valor_vazio(valor):
        return 0.0
    texto = str(valor).replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _tem_coluna_veiculo(colunas: Iterable[object]) -> bool:
    chaves = {_chave_coluna(coluna) for coluna in colunas}
    return "tipo veiculo" in chaves or "veiculo" in chaves


def _ler_sqlite(caminho: Path) -> pd.DataFrame:
    with sqlite3.connect(caminho) as conexao:
        tabelas = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
            conexao,
        )["name"].tolist()
        if not tabelas:
            return pd.DataFrame()
        tabela = "deliveries" if "deliveries" in tabelas else tabelas[0]
        df = pd.read_sql_query(f'SELECT * FROM "{tabela}"', conexao)
        if "observacoes" in tabelas and tabela != "observacoes":
            obs = pd.read_sql_query('SELECT * FROM "observacoes"', conexao)
            df = pd.concat([df, obs], ignore_index=True, sort=False)
        return df


def _garantir_coluna_veiculo(caminho: Path) -> None:
    """Cria tipo_veiculo na fonte local quando não existir tipo_veiculo/veiculo."""
    ext = caminho.suffix.lower()
    if ext in {".xlsx", ".xls", ".xlsm"}:
        planilhas = pd.read_excel(caminho, sheet_name=None)
        alterou = False
        for nome, df in planilhas.items():
            if not _tem_coluna_veiculo(df.columns):
                planilhas[nome] = df.assign(tipo_veiculo=pd.NA)
                alterou = True
        if alterou:
            with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
                for nome, df in planilhas.items():
                    df.to_excel(writer, sheet_name=nome, index=False)
    elif ext in {".csv", ".txt"}:
        df = pd.read_csv(caminho, sep=None, engine="python")
        if not _tem_coluna_veiculo(df.columns):
            df["tipo_veiculo"] = pd.NA
            df.to_csv(caminho, index=False)
    elif ext in {".db", ".sqlite", ".sqlite3"}:
        with sqlite3.connect(caminho) as conexao:
            tabelas = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
                conexao,
            )["name"].tolist()
            tabela = "deliveries" if "deliveries" in tabelas else (tabelas[0] if tabelas else "")
            if tabela:
                info = pd.read_sql_query(f'PRAGMA table_info("{tabela}")', conexao)
                if not _tem_coluna_veiculo(info["name"].tolist()):
                    conexao.execute(f'ALTER TABLE "{tabela}" ADD COLUMN tipo_veiculo TEXT')


def carregar_dados(caminho_dados: str) -> pd.DataFrame:
    """Carrega CSV, Excel ou SQLite e devolve um DataFrame normalizado."""
    caminho = Path(caminho_dados)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de dados não encontrado: {caminho_dados}")

    ext = caminho.suffix.lower()
    _garantir_coluna_veiculo(caminho)
    if ext in {".xlsx", ".xls", ".xlsm"}:
        planilhas = pd.read_excel(caminho, sheet_name=None)
        df = next(iter(planilhas.values()), pd.DataFrame())
        for nome, obs_df in planilhas.items():
            if _sem_acentos(nome) in {"OBSERVACOES", "OBSERVAÇÕES"}:
                df = pd.concat([df, obs_df], ignore_index=True, sort=False)
                break
    elif ext in {".csv", ".txt"}:
        df = pd.read_csv(caminho, sep=None, engine="python")
    elif ext in {".db", ".sqlite", ".sqlite3"}:
        df = _ler_sqlite(caminho)
    else:
        raise ValueError("Formato não suportado. Use .xlsx, .xls, .csv, .db, .sqlite ou .sqlite3.")

    return _normalizar_colunas(df)


def _periodo_hoje(df: pd.DataFrame) -> pd.DataFrame:
    hoje = pd.Timestamp(date.today())
    return df[df["data"].dt.date == hoje.date()]


def _periodo_ontem(df: pd.DataFrame) -> pd.DataFrame:
    ontem = pd.Timestamp(date.today() - timedelta(days=1))
    return df[df["data"].dt.date == ontem.date()]


def _periodo_mes(df: pd.DataFrame) -> pd.DataFrame:
    hoje = pd.Timestamp(date.today())
    return df[(df["data"].dt.year == hoje.year) & (df["data"].dt.month == hoje.month)]


def _extrair_motorista(pergunta: str, motoristas: Iterable[str]) -> str:
    pergunta_norm = _sem_acentos(pergunta)
    for motorista in sorted(set(motoristas), key=len, reverse=True):
        if motorista and motorista in pergunta_norm:
            return motorista
        primeiro_nome = motorista.split()[0] if motorista else ""
        if primeiro_nome and re.search(rf"\b{re.escape(primeiro_nome)}\b", pergunta_norm):
            return motorista
    return ""


def _filtrar_motorista(df: pd.DataFrame, motorista: str) -> pd.DataFrame:
    if not motorista:
        return df
    return df[df["motorista"] == motorista]


def _extrair_termo_apos(pergunta_norm: str, termos: Iterable[str]) -> str:
    for termo in termos:
        match = re.search(rf"\b{termo}\s+([A-Z0-9][A-Z0-9 ._-]*)", pergunta_norm)
        if match:
            valor = match.group(1).strip()
            valor = re.split(r"\b(COM|NO|NA|EM|ESTE|ESSE|MES|HOJE|FEZ|USARAM|USOU)\b", valor)[0]
            return valor.strip(" .?!,;:")
    return ""


def _extrair_veiculo(pergunta: str) -> str:
    pergunta_norm = _sem_acentos(pergunta)
    conhecidos = ["TRUCK", "TOCO", "VAN", "UTILITARIO", "CARRETA", "BITRUCK", "VUC"]
    for veiculo in conhecidos:
        if re.search(rf"\b{re.escape(veiculo)}\b", pergunta_norm):
            return veiculo
    return _extrair_termo_apos(pergunta_norm, ["VEICULO", "TIPO"])


def _extrair_data_especifica(pergunta: str) -> pd.Timestamp | None:
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", pergunta)
    if match:
        dia, mes, ano = match.groups()
        ano = ano or str(date.today().year)
        if len(ano) == 2:
            ano = "20" + ano
        return pd.to_datetime(f"{dia}/{mes}/{ano}", dayfirst=True, errors="coerce")

    pergunta_norm = _sem_acentos(pergunta)
    if "STATUS" not in pergunta_norm:
        return None
    if _extrair_delivery_solto(pergunta):
        return None
    dias = [int(valor) for valor in re.findall(r"(?<![/-])\b(\d{1,2})\b(?![/-])", pergunta_norm)]
    dias_validos = [dia for dia in dias if 1 <= dia <= 31]
    if not dias_validos:
        return None
    hoje = date.today()
    return pd.to_datetime(f"{dias_validos[0]}/{hoje.month}/{hoje.year}", dayfirst=True, errors="coerce")


def _aplicar_filtros_pergunta(df: pd.DataFrame, pergunta: str, motorista: str = "") -> pd.DataFrame:
    pergunta_norm = _sem_acentos(pergunta)
    base = df
    data_especifica = _extrair_data_especifica(pergunta)
    if data_especifica is not None and not pd.isna(data_especifica):
        base = base[base["data"].dt.date == data_especifica.date()]
    elif "HOJE" in pergunta_norm:
        base = _periodo_hoje(base)
    elif "ONTEM" in pergunta_norm:
        base = _periodo_ontem(base)
    elif "MES" in pergunta_norm or "MÊS" in pergunta_norm:
        base = _periodo_mes(base)

    base = _filtrar_motorista(base, motorista)

    delivery = _extrair_termo_apos(pergunta_norm, ["DELIVERY", "ENTREGA", "DOCUMENTO", "REMESSA"])
    if delivery:
        base = base[base["delivery"].apply(lambda v: delivery in _sem_acentos(v))]

    cliente = _extrair_termo_apos(pergunta_norm, ["CLIENTE"])
    if cliente:
        base = base[base["cliente"].apply(lambda v: cliente in _sem_acentos(v))]

    return base



def _campo_operacional(rotulo: str, valor: object) -> str:
    if _valor_vazio(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return f"{rotulo} {str(valor).strip()}"


def _formatar_valor_operacional(valor: object) -> str:
    numero = _numero(valor)
    if not numero:
        return ""
    return f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _linha_operacional(row: pd.Series) -> str:
    data = row.get("data")
    partes = []
    if not pd.isna(data):
        partes.append(f"DATA {pd.Timestamp(data).strftime('%d/%m/%Y')}")
    campos = [
        ("M", row.get("motorista")),
        ("D", row.get("delivery")),
        ("CL", row.get("cliente")),
        ("P", row.get("paletes")),
        ("PC", row.get("pc")),
    ]
    for rotulo, valor in campos:
        parte = _campo_operacional(rotulo, valor)
        if parte:
            partes.append(parte)
    valor = _formatar_valor_operacional(row.get("valor_frete"))
    if valor:
        partes.append(f"V {valor}")
    for rotulo, coluna in [("L", "l_horario"), ("C", "c_horario"), ("FI", "f_horario")]:
        parte = _campo_operacional(rotulo, row.get(coluna))
        if parte:
            partes.append(parte)
    obs = _campo_operacional("O", row.get("observacoes"))
    if obs:
        partes.append(obs)
    return _adicionar_cnpj_conferencia(" ".join(partes), row)


def _adicionar_cnpj_conferencia(linha: str, row: pd.Series) -> str:
    cnpj = _texto_valido(row.get("cnpj"))
    if not cnpj:
        return linha
    return f"{linha}\n\nCNPJ: {cnpj}"


def _linha_status_individual(row: pd.Series) -> str:
    """Linha curta para consultas de status, exibindo só campos úteis preenchidos."""
    partes = []
    for rotulo, valor in [
        ("D", row.get("delivery")),
        ("M", row.get("motorista")),
        ("CL", row.get("cliente")),
        ("L", row.get("l_horario")),
        ("C", row.get("c_horario")),
        ("FI", row.get("f_horario")),
        ("DF", row.get("data_finalizacao")),
        ("PC", row.get("pc")),
        ("O", row.get("observacoes")),
    ]:
        parte = _campo_operacional(rotulo, valor)
        if parte:
            partes.append(parte)
    return _adicionar_cnpj_conferencia(" ".join(partes), row)


def _responder_status_delivery(df: pd.DataFrame, pergunta: str) -> str:
    numeros = re.findall(r"\b\d{4,}\b", pergunta)
    if not numeros:
        return ""
    codigo = numeros[0]
    base = df[df["delivery"].astype("string").fillna("").str.replace(r"\D", "", regex=True).str.endswith(codigo[-4:])]
    if len(codigo) >= 8:
        base_exata = base[base["delivery"].astype("string").fillna("").str.replace(r"\D", "", regex=True) == codigo]
        if not base_exata.empty:
            base = base_exata
    if base.empty:
        return "Nenhuma coleta encontrada."
    return "\n\n".join(_linha_status_individual(row) for _, row in base.head(20).iterrows())


def _responder_status_hoje(df: pd.DataFrame) -> str:
    base = _periodo_hoje(df)
    if base.empty:
        return "Nenhuma coleta encontrada."
    return "\n".join(_linha_status_individual(row) for _, row in base.iterrows())


def _responder_em_aberto(df: pd.DataFrame, pergunta: str) -> str:
    base = _aplicar_periodo_operacional(df, pergunta)
    base = base[base["f_horario"].apply(_valor_vazio)]
    if base.empty:
        return "Nenhuma coleta em aberto."
    return "\n".join(_linha_status_individual(row) for _, row in base.iterrows())


def _linhas_veiculo(df: pd.DataFrame, veiculo: str) -> str:
    linhas = []
    for _, row in df.head(50).iterrows():
        data = row.get("data")
        data_txt = pd.Timestamp(data).strftime("%d/%m/%Y") if not pd.isna(data) else ""
        linhas.append(
            "DATA {data} M {motorista} D {delivery} CL {cliente} VEÍCULO {veiculo}".format(
                data=data_txt,
                motorista="" if _valor_vazio(row.get("motorista")) else row.get("motorista"),
                delivery="" if _valor_vazio(row.get("delivery")) else row.get("delivery"),
                cliente="" if _valor_vazio(row.get("cliente")) else row.get("cliente"),
                veiculo=veiculo,
            )
        )
    if len(df) > 50:
        linhas.append(f"... e mais {len(df) - 50} coleta(s).")
    linhas.append(f"TOTAL DE COLETAS COM {veiculo}: {len(df)}")
    return "\n".join(linhas)


def _responder_veiculo(df: pd.DataFrame, pergunta: str, motorista: str) -> str:
    veiculo = _extrair_veiculo(pergunta)
    base = _aplicar_filtros_pergunta(df, pergunta, motorista)
    base = base[base["tipo_veiculo"].apply(lambda v: veiculo in _sem_acentos(v))]

    pergunta_norm = _sem_acentos(pergunta)
    if "POR MOTORISTA" in pergunta_norm or "SEPARAR POR MOTORISTA" in pergunta_norm:
        if base.empty:
            return f"TOTAL DE COLETAS COM {veiculo}: 0"
        partes = []
        for nome, grupo in base.groupby("motorista", dropna=False):
            partes.append(f"MOTORISTA {nome} ({len(grupo)} coleta(s))")
            partes.append(_linhas_veiculo(grupo, veiculo))
        return "\n".join(partes)

    return _linhas_veiculo(base, veiculo)


def _linhas_resumo(df: pd.DataFrame) -> str:
    if df.empty:
        return "Nenhuma coleta encontrada."
    colunas = [c for c in ["data", "motorista", "delivery", "sr", "cliente", "observacoes", "cnpj"] if c in df.columns]
    linhas = []
    for _, row in df[colunas].head(50).iterrows():
        partes = []
        data = row.get("data")
        if not pd.isna(data):
            partes.append(pd.Timestamp(data).strftime("%d/%m/%Y"))
        for coluna in colunas:
            if coluna in {"data", "cnpj"}:
                continue
            valor = row.get(coluna)
            if not _valor_vazio(valor):
                partes.append(str(valor))
        linha = " - " + " | ".join(partes)
        linhas.append(_adicionar_cnpj_conferencia(linha, row))
    sufixo = "" if len(df) <= 50 else f"\n... e mais {len(df) - 50} coleta(s)."
    return "\n".join(linhas) + sufixo


def _formatar_campo_horario_resumo(rotulo: str, valor: object) -> str:
    horario = "—" if _valor_vazio(valor) else str(valor).strip()
    return f"{rotulo} {horario}"


def _linhas_resumo_sem_fi(df: pd.DataFrame) -> str:
    if df.empty:
        return "Nenhuma coleta encontrada."
    linhas = []
    for _, row in df.head(50).iterrows():
        data = row.get("data")
        data_texto = "—" if pd.isna(data) else pd.Timestamp(data).strftime("%d/%m/%Y")
        motorista = "—" if _valor_vazio(row.get("motorista")) else str(row.get("motorista")).strip()
        delivery = "—" if _valor_vazio(row.get("delivery")) else str(row.get("delivery")).strip()
        cliente = "—" if _valor_vazio(row.get("cliente")) else str(row.get("cliente")).strip()
        partes = [
            data_texto,
            motorista,
            delivery,
            cliente,
            _formatar_campo_horario_resumo("L", row.get("l_horario")),
            _formatar_campo_horario_resumo("C", row.get("c_horario")),
            _formatar_campo_horario_resumo("FI", row.get("f_horario")),
        ]
        linha = " - " + " | ".join(partes)
        linhas.append(_adicionar_cnpj_conferencia(linha, row))
    sufixo = "" if len(df) <= 50 else f"\n... e mais {len(df) - 50} coleta(s)."
    return "\n".join(linhas) + sufixo


def _linhas_codigos_sem_fi(df: pd.DataFrame) -> str:
    if df.empty:
        return "Nenhuma coleta encontrada."
    linhas = []
    for _, row in df.head(50).iterrows():
        delivery = "" if _valor_vazio(row.get("delivery")) else str(row.get("delivery")).strip()
        motorista = "" if _valor_vazio(row.get("motorista")) else str(row.get("motorista")).strip()
        cliente = "" if _valor_vazio(row.get("cliente")) else str(row.get("cliente")).strip()
        linhas.append(f"D {delivery} | {motorista} | {cliente}")
    if len(df) > 50:
        linhas.append(f"... e mais {len(df) - 50} coleta(s).")
    return "\n".join(linhas)



def _extrair_intervalo_datas(pergunta: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    datas = re.findall(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", pergunta)
    if len(datas) < 2:
        return None, None
    valores = []
    ano_atual = str(date.today().year)
    for dia, mes, ano in datas[:2]:
        ano = ano or ano_atual
        if len(ano) == 2:
            ano = "20" + ano
        valores.append(pd.to_datetime(f"{dia}/{mes}/{ano}", dayfirst=True, errors="coerce"))
    if any(pd.isna(v) for v in valores):
        return None, None
    inicio, fim = valores
    if inicio > fim:
        inicio, fim = fim, inicio
    return inicio, fim


def _aplicar_periodo_operacional(df: pd.DataFrame, pergunta: str) -> pd.DataFrame:
    pergunta_norm = _sem_acentos(pergunta)
    inicio, fim = _extrair_intervalo_datas(pergunta)
    if inicio is not None and fim is not None:
        logger.info("Aplicando período operacional de %s a %s para pergunta: %s", inicio.date(), fim.date(), pergunta)
        return df[(df["data"].dt.date >= inicio.date()) & (df["data"].dt.date <= fim.date())]
    data_especifica = _extrair_data_especifica(pergunta)
    if data_especifica is not None and not pd.isna(data_especifica):
        return df[df["data"].dt.date == data_especifica.date()]
    if "HOJE" in pergunta_norm:
        return _periodo_hoje(df)
    if "ONTEM" in pergunta_norm:
        return _periodo_ontem(df)
    if "MES" in pergunta_norm or "MÊS" in pergunta_norm:
        return _periodo_mes(df)
    return df


def _validar_colunas_consulta(df: pd.DataFrame, colunas: Iterable[str], consulta: str) -> None:
    faltantes = [coluna for coluna in colunas if coluna not in df.columns]
    if faltantes:
        logger.error("Consulta %r falhou por colunas ausentes: %s. Colunas disponíveis: %s", consulta, faltantes, list(df.columns))
        raise KeyError(f"Colunas ausentes para a consulta: {', '.join(faltantes)}")
    logger.debug("Consulta %r validou as colunas: %s", consulta, list(colunas))


def _filtrar_observacao(df: pd.DataFrame, tipo: str) -> pd.DataFrame:
    _validar_colunas_consulta(df, ["observacoes"], f"observações {tipo}")
    logger.info("Filtrando observações do tipo %s em %s registro(s)", tipo, len(df))
    if tipo == "SR/REEMBOLSO":
        return df[df["observacoes"].apply(lambda v: "SR" in _sem_acentos(v) or "REEMB" in _sem_acentos(v))]
    return df[df["observacoes"].apply(lambda v: tipo in _sem_acentos(v))]


def _motivo_observacao(obs: object, tipo: str) -> str:
    texto_obs = _sem_acentos(obs).replace("O ", "", 1)
    texto_obs = texto_obs.replace(f"{tipo} AS", f"{tipo} ÀS")
    if tipo in texto_obs:
        motivo = texto_obs.split(tipo, 1)[1].strip(" -:")
        motivo = re.sub(r"\bAS\s+\d{1,2}:\d{2}\b", "", motivo).strip(" -:")
        return motivo or "SEM MOTIVO"
    return "SEM MOTIVO"


def _linhas_observacoes(df: pd.DataFrame) -> str:
    if df.empty:
        return "Nenhum registro encontrado."
    linhas = []
    for _, row in df.head(50).iterrows():
        data = row.get("data")
        data_txt = pd.Timestamp(data).strftime("%d/%m/%Y") if not pd.isna(data) else ""
        linhas.append(
            "DATA {data} | M {motorista} | D {delivery} | CL {cliente} | O {observacao}".format(
                data=data_txt,
                motorista="" if _valor_vazio(row.get("motorista")) else row.get("motorista"),
                delivery="" if _valor_vazio(row.get("delivery")) else row.get("delivery"),
                cliente="" if _valor_vazio(row.get("cliente")) else row.get("cliente"),
                observacao="" if _valor_vazio(row.get("observacoes")) else str(row.get("observacoes")).removeprefix("O "),
            )
        )
    if len(df) > 50:
        linhas.append(f"... e mais {len(df) - 50} observação(ões).")
    return "\n".join(linhas)


def _responder_observacao(
    df: pd.DataFrame,
    pergunta: str,
    tipo: str,
    rotulo_total: str,
    motorista: str = "",
) -> str:
    pergunta_norm = _sem_acentos(pergunta)
    _validar_colunas_consulta(df, ["data", "motorista", "observacoes"], pergunta)
    base = _filtrar_motorista(_filtrar_observacao(_aplicar_periodo_operacional(df, pergunta), tipo), motorista)
    if "POR MOTORISTA" in pergunta_norm:
        if base.empty:
            return "Nenhum registro encontrado."
        contagem = base.groupby("motorista", dropna=False).size().sort_values(ascending=False)
        return f"{rotulo_total}: {len(base)}\n" + "\n".join(f"{m}: {int(q)}" for m, q in contagem.items())
    if "POR MOTIVO" in pergunta_norm:
        if base.empty:
            return "Nenhum registro encontrado."
        motivos = base["observacoes"].apply(lambda v: _motivo_observacao(v, tipo if tipo != "SR/REEMBOLSO" else "REEMBOLSO"))
        contagem = motivos.value_counts()
        return f"{rotulo_total}: {len(base)}\n" + "\n".join(f"{m}: {int(q)}" for m, q in contagem.items())
    if "MOSTRAR" in pergunta_norm or "QUAIS" in pergunta_norm or "LISTAR" in pergunta_norm:
        if base.empty:
            return "Nenhum registro encontrado."
        return f"{rotulo_total}: {len(base)}\n\n" + _linhas_observacoes(base)
    alvo = f" DE {motorista}" if motorista else ""
    if base.empty:
        return "Nenhum registro encontrado."
    return f"{rotulo_total}{alvo}: {len(base)}"



def _formatar_moeda_brasileira(valor: float | Decimal, com_prefixo: bool = True) -> str:
    valor_decimal = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    valor_formatado = f"{valor_decimal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {valor_formatado}" if com_prefixo else valor_formatado


def _tem_data_na_pergunta(pergunta: str) -> bool:
    return bool(re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", pergunta))


def _valor_planilha_deslocamento(valor_original: Decimal) -> Decimal:
    centavos = int((valor_original * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP)) % 100
    if centavos == 5:
        return (valor_original / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(f"{float(valor_original) / 2:.2f}")


def _eh_pedido_relatorio_especial(pergunta_norm: str, tipo: str) -> bool:
    if tipo != "DESLOCAMENTO":
        return ("RELATORIO" in pergunta_norm or _tem_data_na_pergunta(pergunta_norm)) and tipo in pergunta_norm
    if "DESLOC" not in pergunta_norm or "QUANT" in pergunta_norm:
        return False
    return "RELATORIO" in pergunta_norm or _tem_data_na_pergunta(pergunta_norm)


def _linhas_relatorio_especial(df: pd.DataFrame, tipo: str) -> str:
    if df.empty:
        return "Nenhum registro encontrado para o período informado."

    if tipo == "DESLOCAMENTO":
        cabecalho = "DATA | DELIVERY | CLIENTE | MOTORISTA | VALOR DIVIDIDO | VALOR TOTAL"
        status_coluna = ""
    else:
        cabecalho = "DATA | DELIVERY | CLIENTE | STATUS | VALOR"
        status_coluna = "REEMBOLSO"

    linhas = [cabecalho]
    total_planilha = Decimal("0.00")
    total_original = Decimal("0.00")
    for _, row in df.sort_values("data").iterrows():
        data = row.get("data")
        data_txt = pd.Timestamp(data).strftime("%d/%m/%Y") if not pd.isna(data) else ""
        valor_original = Decimal(str(_numero(row.get("valor_frete"))))
        total_original += valor_original
        if tipo == "DESLOCAMENTO":
            valor_planilha = _valor_planilha_deslocamento(valor_original)
            total_planilha += valor_planilha
            valor_txt = f"{_formatar_moeda_brasileira(valor_planilha, com_prefixo=False)} | {_formatar_moeda_brasileira(valor_original, com_prefixo=False)}"
        else:
            valor_txt = _formatar_moeda_brasileira(valor_original)
        linhas.append(
            "{data} | {delivery} | {cliente} | {status} | {valor}".format(
                data=data_txt,
                delivery="" if _valor_vazio(row.get("delivery")) else str(row.get("delivery")).strip(),
                cliente="" if _valor_vazio(row.get("cliente")) else str(row.get("cliente")).strip(),
                status=("" if _valor_vazio(row.get("motorista")) else str(row.get("motorista")).strip()) if tipo == "DESLOCAMENTO" else status_coluna,
                valor=valor_txt,
            )
        )

    if tipo == "DESLOCAMENTO":
        linhas.extend([
            f"TOTAL DE REGISTROS: {len(df)}",
            f"TOTAL PLANILHA: {_formatar_moeda_brasileira(total_planilha)}",
            f"TOTAL ORIGINAL: {_formatar_moeda_brasileira(total_original)}",
        ])
    else:
        linhas.extend([
            f"TOTAL DE REGISTROS: {len(df)}",
            f"VALOR TOTAL: {_formatar_moeda_brasileira(total_original)}",
        ])
    return "\n".join(linhas)


def _responder_relatorio_especial(df: pd.DataFrame, pergunta: str, tipo: str) -> str:
    _validar_colunas_consulta(df, ["data", "delivery", "cliente", "valor_frete", "observacoes", "status"], pergunta)
    base = _aplicar_periodo_operacional(df, pergunta)
    if tipo == "DESLOCAMENTO":
        base = base[
            base["status"].apply(lambda v: "DESLOCAMENTO" in _sem_acentos(v))
            | base["observacoes"].apply(lambda v: "DESLOCAMENTO" in _sem_acentos(v))
        ]
    else:
        base = base[base["observacoes"].apply(lambda v: "REEMBOLSO" in _sem_acentos(v))]
    return _linhas_relatorio_especial(base, tipo)


def _linhas_operacionais(df: pd.DataFrame, limite: int = 200, formato_status: bool = False) -> str:
    if df.empty:
        return "Nenhuma coleta encontrada."
    formatador = _linha_status_individual if formato_status else _linha_operacional
    linhas = [formatador(row) for _, row in df.head(limite).iterrows()]
    if len(df) > limite:
        linhas.append(f"... e mais {len(df) - limite} coleta(s).")
    return "\n".join(linhas)


def _responder_coletas_operacionais(df: pd.DataFrame, pergunta: str, motorista: str = "") -> str:
    base = _aplicar_periodo_operacional(df, pergunta)
    base = _filtrar_motorista(base, motorista)
    return _linhas_operacionais(base, formato_status="STATUS" in _sem_acentos(pergunta))


def _extrair_delivery_solto(pergunta: str) -> str:
    """Extrai consulta por delivery com palavra-chave ou por final numérico solto.

    Datas como 17/06 não entram aqui porque a expressão exige grupos de dígitos
    isolados sem barras.
    """
    pergunta_norm = _sem_acentos(pergunta)
    if re.search(r"\b(DIA|DATA)\b", pergunta_norm):
        return ""
    numeros = re.findall(r"\b\d{4,}\b", pergunta_norm)
    if not numeros:
        return ""
    if any(termo in pergunta_norm for termo in ["STATUS", "DELIVERY", "REMESSA", "DOCUMENTO", "CONSULTAR", "COMO ESTA", "COMO ESTÁ"]):
        return numeros[0]
    return ""


def _eh_pedido_lista_operacional(pergunta_norm: str, pergunta: str, motorista: str) -> bool:
    if "QUANT" in pergunta_norm or "TOTAL" in pergunta_norm or "VALOR" in pergunta_norm:
        return False
    if _tem_data_na_pergunta(pergunta) and any(termo in pergunta_norm for termo in ["STATUS", "COLETA", "DIA", "DATA"]):
        return True
    if any(termo in pergunta_norm for termo in ["STATUS", "COLETA", "COLETAS"]):
        return True
    if motorista and ("HOJE" in pergunta_norm or "ONTEM" in pergunta_norm):
        return True
    return False


def _responder_cliente(df: pd.DataFrame, pergunta: str, motorista: str) -> str:
    pergunta_norm = _sem_acentos(pergunta)
    cliente = _extrair_termo_apos(pergunta_norm, ["CLIENTE"])
    if not cliente:
        return ""
    base = _aplicar_filtros_pergunta(df, pergunta, motorista)
    if "QUANT" in pergunta_norm:
        return f"Coletas do cliente {cliente}: {len(base)}."
    return f"Coletas do cliente {cliente}: {len(base)}\n{_linhas_resumo(base)}"


def responder_pergunta_df(pergunta: str, dados: pd.DataFrame) -> str:
    """Responde perguntas operacionais sobre um DataFrame já carregado.

    Use esta função quando os dados vêm do app/Supabase. Ela reaproveita a
    mesma normalização usada para CSV, Excel e SQLite antes de interpretar a
    pergunta.
    """
    logger.info("Respondendo pergunta operacional: %s", pergunta)
    df = _normalizar_colunas(dados.copy())
    _validar_colunas_consulta(df, ["data", "motorista", "delivery", "sr", "cliente", "valor_frete", "c_horario", "f_horario", "observacoes", "tipo_veiculo"], pergunta)
    logger.debug("DataFrame normalizado para pergunta %r: %s linhas, colunas %s", pergunta, len(df), list(df.columns))
    pergunta_norm = _sem_acentos(pergunta)
    df_mes = _periodo_mes(df)
    motorista = _extrair_motorista(pergunta, df["motorista"].dropna().astype(str))
    veiculo = _extrair_veiculo(pergunta)

    if re.fullmatch(r"\s*COLETAS\s+(?:DE\s+)?HOJE\s*", pergunta_norm):
        return _responder_coletas_hoje_admin(df)

    if re.fullmatch(r"\s*COLETAS\s+DO\s+DIA\s*", pergunta_norm):
        return _responder_coletas_hoje_admin(df)

    if re.fullmatch(r"\s*COLETAS\s+(?:DE\s+ONTEM|DO\s+DIA\s+\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s*", pergunta_norm):
        return _responder_coletas_motorista_periodo(df, pergunta)

    if (
        ("STATUS" in pergunta_norm or "CONSULTAR" in pergunta_norm or re.search(r"\bCOMO\s+(?:ESTA|ESTÁ)\b", pergunta_norm))
        and re.search(r"\b\d{4,}\b", pergunta_norm)
        and _extrair_delivery_solto(pergunta)
    ):
        return _responder_status_delivery(df, pergunta)

    if any(termo in pergunta_norm for termo in ["EM ABERTO", "PENDENTES", "COLETAS EM ABERTO", "STATUS DAS ABERTAS"]):
        return _responder_em_aberto(df, pergunta)

    if veiculo:
        return _responder_veiculo(df, pergunta, motorista)

    if _eh_pedido_relatorio_especial(pergunta_norm, "DESLOCAMENTO"):
        return _responder_relatorio_especial(df, pergunta, "DESLOCAMENTO")

    if _eh_pedido_relatorio_especial(pergunta_norm, "REEMBOLSO"):
        return _responder_relatorio_especial(df, pergunta, "REEMBOLSO")

    if "SR" in pergunta_norm or "REEMB" in pergunta_norm:
        return _responder_observacao(df, pergunta, "SR/REEMBOLSO", "TOTAL DE SR/REEMBOLSO", motorista)

    if "DESLOC" in pergunta_norm:
        return _responder_observacao(df, pergunta, "DESLOCAMENTO", "TOTAL DE DESLOCAMENTOS", motorista)

    if "BLOQUE" in pergunta_norm or "BLOQ" in pergunta_norm:
        return _responder_observacao(df, pergunta, "BLOQUEIO", "TOTAL DE BLOQUEIOS", motorista)

    resposta_cliente = _responder_cliente(df, pergunta, motorista)
    if resposta_cliente:
        return resposta_cliente

    if "SEM FI" in pergunta_norm or "SEM FINAL" in pergunta_norm or "SEM FINALIZACAO" in pergunta_norm:
        pendentes = df[df["f_horario"].apply(_valor_vazio)]
        if "CODIGO" in pergunta_norm:
            return _linhas_codigos_sem_fi(pendentes)
        return f"Coletas sem FI: {len(pendentes)}\n{_linhas_resumo_sem_fi(pendentes)}"

    if re.search(r"\bSEM C\b", pergunta_norm) or "SEM COLETA" in pergunta_norm:
        pendentes = df[df["c_horario"].apply(_valor_vazio)]
        return f"Coletas sem C: {len(pendentes)}\n{_linhas_resumo(pendentes)}"

    if "BLOQUE" in pergunta_norm:
        bloqueios = df[df["observacoes"].apply(lambda v: "BLOQUE" in _sem_acentos(v))]
        return f"Coletas com bloqueio: {len(bloqueios)}\n{_linhas_resumo(bloqueios)}"

    if "DESLOC" in pergunta_norm:
        deslocamentos = df[df["observacoes"].apply(lambda v: "DESLOC" in _sem_acentos(v))]
        return f"Coletas com deslocamento: {len(deslocamentos)}\n{_linhas_resumo(deslocamentos)}"

    if "VALOR" in pergunta_norm and "MOTORISTA" in pergunta_norm:
        totais = df_mes.groupby("motorista", dropna=False)["valor_frete"].sum().sort_values(ascending=False)
        if totais.empty:
            return "Nenhum valor encontrado no mês atual."
        linhas = [f"{motorista}: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") for motorista, valor in totais.items()]
        return "Valor total por motorista no mês:\n" + "\n".join(linhas)

    if "MAIS COLETA" in pergunta_norm or "MAIOR NUMERO" in pergunta_norm:
        contagem = df_mes.groupby("motorista").size().sort_values(ascending=False)
        if contagem.empty:
            return "Nenhum motorista teve coletas no mês atual."
        return f"Motorista com mais coletas no mês: {contagem.index[0]} ({int(contagem.iloc[0])} coleta(s))."

    if "CADA MOTORISTA" in pergunta_norm or "POR MOTORISTA" in pergunta_norm:
        contagem = df_mes.groupby("motorista").size().sort_values(ascending=False)
        if contagem.empty:
            return "Nenhuma coleta encontrada no mês atual."
        return "Coletas por motorista no mês:\n" + "\n".join(f"{m}: {int(q)}" for m, q in contagem.items())

    if "REMESS" in pergunta_norm:
        base = df_mes if "MES" in pergunta_norm else df
        coluna = "delivery" if base["delivery"].notna().any() else "sr"
        total = base[coluna].dropna().astype(str).str.strip().replace("", pd.NA).dropna().nunique()
        return f"Remessas no mês atual: {total}."

    if _eh_pedido_lista_operacional(pergunta_norm, pergunta, motorista):
        return _responder_coletas_operacionais(df, pergunta, motorista)

    if "HOJE" in pergunta_norm:
        base = _filtrar_motorista(_periodo_hoje(df), motorista)
        alvo = f" de {motorista}" if motorista else ""
        return f"Coletas{alvo} hoje: {len(base)}."

    if "MES" in pergunta_norm or "MÊS" in pergunta_norm:
        base = _filtrar_motorista(df_mes, motorista)
        if motorista and ("QUANT" in pergunta_norm or "FEZ" in pergunta_norm):
            primeiro_nome = motorista.split()[0]
            return f"{primeiro_nome} realizou {len(base)} coleta(s) este mês.".upper()
        alvo = f" de {motorista}" if motorista else ""
        return f"Coletas{alvo} no mês atual: {len(base)}."

    if (
        motorista
        and "COLETA" in pergunta_norm
        and ("QUANT" in pergunta_norm or "FEZ" in pergunta_norm)
    ):
        base = _filtrar_motorista(df, motorista)
        primeiro_nome = motorista.split()[0]
        return f"{primeiro_nome} realizou {len(base)} coleta(s).".upper()

    logger.info("Pergunta não reconhecida: %s", pergunta)
    return "Pergunta não reconhecida."


def responder_pergunta(pergunta: str, caminho_dados: str) -> str:
    """Carrega uma fonte local e responde perguntas operacionais."""
    return responder_pergunta_df(pergunta, carregar_dados(caminho_dados))
