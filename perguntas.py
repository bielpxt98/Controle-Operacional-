"""Perguntas simples sobre o histórico de coletas.

Este módulo não usa APIs externas nem modelos de IA. Ele carrega dados locais
(CSV, Excel ou SQLite) com pandas e responde por regras de palavras-chave.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd


COLUNAS_PADRAO = {
    "data": "data",
    "date": "data",
    "dt": "data",
    "data coleta": "data",
    "data_coleta": "data",
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
    "carreta": "tipo_veiculo",
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
]


def _sem_acentos(texto: object) -> str:
    valor = "" if texto is None else str(texto)
    valor = unicodedata.normalize("NFKD", valor)
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return valor.upper().strip()


def _chave_coluna(coluna: object) -> str:
    return _sem_acentos(coluna).lower().replace("_", " ").strip()


def _valor_vazio(valor: object) -> bool:
    if valor is None or pd.isna(valor):
        return True
    texto = str(valor).strip()
    return texto == "" or texto.lower() in {"nan", "none", "null", "-", "—"}


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


def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    mapa = {}
    for coluna in df.columns:
        chave = _chave_coluna(coluna)
        if chave in COLUNAS_PADRAO:
            mapa[coluna] = COLUNAS_PADRAO[chave]
    df = df.rename(columns=mapa).copy()
    for coluna in COLUNAS_NECESSARIAS:
        if coluna not in df.columns:
            df[coluna] = pd.NA
    df["data"] = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)
    df["motorista"] = df["motorista"].apply(_normalizar_motorista)
    df["valor_frete"] = df["valor_frete"].apply(_numero)
    df["tipo_veiculo"] = df["tipo_veiculo"].apply(lambda v: _sem_acentos(v))
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
        return pd.read_sql_query(f'SELECT * FROM "{tabela}"', conexao)


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
        df = pd.read_excel(caminho)
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
            return valor.strip()
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
    if not match:
        return None
    dia, mes, ano = match.groups()
    ano = ano or str(date.today().year)
    if len(ano) == 2:
        ano = "20" + ano
    return pd.to_datetime(f"{dia}/{mes}/{ano}", dayfirst=True, errors="coerce")


def _aplicar_filtros_pergunta(df: pd.DataFrame, pergunta: str, motorista: str = "") -> pd.DataFrame:
    pergunta_norm = _sem_acentos(pergunta)
    base = df
    data_especifica = _extrair_data_especifica(pergunta)
    if data_especifica is not None and not pd.isna(data_especifica):
        base = base[base["data"].dt.date == data_especifica.date()]
    elif "HOJE" in pergunta_norm:
        base = _periodo_hoje(base)
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
    colunas = [c for c in ["data", "motorista", "delivery", "sr", "cliente", "observacoes"] if c in df.columns]
    linhas = []
    for _, row in df[colunas].head(50).iterrows():
        partes = []
        data = row.get("data")
        if not pd.isna(data):
            partes.append(pd.Timestamp(data).strftime("%d/%m/%Y"))
        for coluna in colunas:
            if coluna == "data":
                continue
            valor = row.get(coluna)
            if not _valor_vazio(valor):
                partes.append(str(valor))
        linhas.append(" - " + " | ".join(partes))
    sufixo = "" if len(df) <= 50 else f"\n... e mais {len(df) - 50} coleta(s)."
    return "\n".join(linhas) + sufixo


def responder_pergunta(pergunta: str, caminho_dados: str) -> str:
    """Responde perguntas operacionais por palavras-chave e pandas.

    Exemplos aceitos: coletas de um motorista hoje/no mês, coletas sem FI,
    sem C, com bloqueio/deslocamento, remessas do mês, valor por motorista e
    motorista com mais coletas.
    """
    df = carregar_dados(caminho_dados)
    pergunta_norm = _sem_acentos(pergunta)
    df_mes = _periodo_mes(df)
    motorista = _extrair_motorista(pergunta, df["motorista"].dropna().astype(str))
    veiculo = _extrair_veiculo(pergunta)

    if veiculo:
        return _responder_veiculo(df, pergunta, motorista)

    if "SEM FI" in pergunta_norm or "SEM FINAL" in pergunta_norm or "SEM FINALIZACAO" in pergunta_norm:
        pendentes = df[df["f_horario"].apply(_valor_vazio)]
        return f"Coletas sem FI: {len(pendentes)}\n{_linhas_resumo(pendentes)}"

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

    if "HOJE" in pergunta_norm:
        base = _filtrar_motorista(_periodo_hoje(df), motorista)
        alvo = f" de {motorista}" if motorista else ""
        return f"Coletas{alvo} hoje: {len(base)}."

    if "MES" in pergunta_norm or "MÊS" in pergunta_norm:
        base = _filtrar_motorista(df_mes, motorista)
        alvo = f" de {motorista}" if motorista else ""
        return f"Coletas{alvo} no mês atual: {len(base)}."

    return (
        "Não entendi a pergunta. Tente perguntar sobre: hoje, mês, cada motorista, "
        "sem FI, sem C, bloqueio, deslocamento, remessas, valor por motorista ou motorista com mais coletas."
    )
