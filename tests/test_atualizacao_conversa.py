import ast
import re
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd


FUNCOES_NECESSARIAS = {
    "texto",
    "limpar_busca",
    "normalizar_motorista",
    "normalizar_cliente_rapido",
    "normalizar_horario",
    "completar_dados_motorista",
    "limpar_codigo_delivery",
    "parece_delivery_completo",
    "normalizar_data_conversa",
    "identificar_acao_conversa",
    "extrair_motorista_conversa",
    "extrair_codigo_conversa",
    "extrair_contexto_linha_busca",
    "extrair_valores_alteracao_conversa",
    "extrair_observacao_livre_conversa",
    "remover_observacao_livre_conversa",
    "combinar_observacoes_conversa",
    "parse_atualizacao_conversa",
    "campos_atualizacao_conversa",
    "buscar_coletas_por_conversa",
    "parse_atualizacao_rapida",
    "montar_registro",
    "numero",
    "extrair_regra_bloqueio_deslocamento",
    "normalizar_observacao",
}

CONSTANTES_NECESSARIAS = {
    "MOTORISTAS_FIXOS",
    "ACOES_CONVERSA",
    "PALAVRAS_COMANDO_CONVERSA",
}


def carregar_funcoes_app():
    """Carrega só funções puras do app, sem executar a interface Streamlit."""
    modulo = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    namespace = {"re": re, "datetime": datetime, "logger": logging.getLogger("test_atualizacao_conversa")}
    import pandas as pd
    namespace["pd"] = pd

    for node in modulo.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) in CONSTANTES_NECESSARIAS for t in node.targets):
            exec(compile(ast.Module([node], []), "app.py", "exec"), namespace)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCOES_NECESSARIAS:
            exec(compile(ast.Module([node], []), "app.py", "exec"), namespace)

    return namespace


def test_conversa_bloqueio_com_observacao_livre_concatena_o_campo_o():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_conversa"](
        "16/06/2026 | ARIEL | 3787816659 | WMS MAX ATACADO B 16:22 O cliente não quis carregar"
    )

    assert erro is None
    assert parsed["horario"] == "16:22"
    assert parsed["acao"] == "BLOQUEIO"
    assert parsed["observacoes"] == "BLOQUEIO 16:22 | CLIENTE NAO QUIS CARREGAR"

    campos = app["campos_atualizacao_conversa"](parsed)
    assert campos["f_horario"] == "16:22"
    assert campos["observacoes"] == "BLOQUEIO 16:22 | CLIENTE NAO QUIS CARREGAR"


def test_conversa_finalizacao_salva_observacao_livre_ate_fim_da_frase():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_conversa"](
        "ARIEL 3787816659 finalizou 16:22 O cliente pediu comprovante depois"
    )

    assert erro is None
    assert parsed["horario"] == "16:22"
    assert parsed["acao"] == "FINALIZACAO"
    assert parsed["observacoes"] == "CLIENTE PEDIU COMPROVANTE DEPOIS"

    campos = app["campos_atualizacao_conversa"](parsed)
    assert campos["f_horario"] == "16:22"
    assert campos["observacoes"] == "CLIENTE PEDIU COMPROVANTE DEPOIS"


def test_conversa_formato_operacional_extrai_delivery_e_busca_somente_por_d():
    app = carregar_funcoes_app()
    df = pd.DataFrame(
        [
            {"id": 1, "D": 3787816621, "motorista": "Outro", "cliente": "Cliente X", "f_horario": "08:00"},
            {"id": 2, "D": 3787816622, "motorista": "Jean", "cliente": "Cliente Y", "f_horario": ""},
        ]
    )

    parsed, erro = app["parse_atualizacao_conversa"]("D   3787816621 FI 09:44 DF 17/06")
    resultados = app["buscar_coletas_por_conversa"](df, parsed)

    assert erro is None
    assert parsed["final_delivery"] == "3787816621"
    assert parsed["horario"] == "09:44"
    assert parsed["data_finalizacao"] == "17/06"
    assert len(resultados) == 1
    assert resultados.iloc[0]["id"] == 1


def test_conversa_aceita_delivery_sem_letra_d_no_inicio():
    app = carregar_funcoes_app()
    df = pd.DataFrame(
        [{"id": 1, "delivery": "3787816621", "motorista": "Outro", "cliente": "Cliente X", "f_horario": "08:00"}]
    )

    parsed, erro = app["parse_atualizacao_conversa"]("3787816621 FI 09:44 DF 17/06")
    resultados = app["buscar_coletas_por_conversa"](df, parsed)

    assert erro is None
    assert parsed["final_delivery"] == "3787816621"
    assert len(resultados) == 1
    assert resultados.iloc[0]["id"] == 1


def test_conversa_aceita_alias_delivery_e_remessa():
    app = carregar_funcoes_app()

    for frase in ["delivery 3787816621 FI 09:44", "remessa 3787816621 FI 09:44", "d 3787816621 FI 09:44"]:
        parsed, erro = app["parse_atualizacao_conversa"](frase)
        assert erro is None
        assert parsed["final_delivery"] == "3787816621"


def test_conversa_aceita_apenas_delivery_para_abrir_confirmacao():
    app = carregar_funcoes_app()
    df = pd.DataFrame([{"id": 1, "delivery": 3787816621, "motorista": "Outro", "cliente": "Cliente X", "f_horario": ""}])

    parsed, erro = app["parse_atualizacao_conversa"]("D 3787816621")
    resultados = app["buscar_coletas_por_conversa"](df, parsed)

    assert erro is None
    assert parsed["final_delivery"] == "3787816621"
    assert parsed["acao"] == ""
    assert len(resultados) == 1


def test_normalizar_cliente_wms_preserva_nome_completo():
    app = carregar_funcoes_app()

    assert app["normalizar_cliente_rapido"]("WMS MAX ATACADO AV. SANTOS DUMONT") == "WMS MAX ATACADO AV. SANTOS DUMONT"


def test_atualizacao_rapida_preserva_cliente_wms_completo():
    app = carregar_funcoes_app()

    campos, erro = app["parse_atualizacao_rapida"](
        "M ARIEL D 3787816621 CL WMS MAX ATACADO AV. SANTOS DUMONT"
    )

    assert erro is None
    assert campos["campos"]["cliente"] == "WMS MAX ATACADO AV. SANTOS DUMONT"


def test_atualizacao_conversa_preserva_novo_cliente_wms_completo():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_conversa"](
        "alterar cliente 3787816621 para WMS MAX ATACADO AV. SANTOS DUMONT"
    )
    campos = app["campos_atualizacao_conversa"](parsed)

    assert erro is None
    assert parsed["novo_cliente"] == "WMS MAX ATACADO AV. SANTOS DUMONT"
    assert campos["cliente"] == "WMS MAX ATACADO AV. SANTOS DUMONT"


def test_montar_registro_excel_preserva_cliente_wms_completo():
    app = carregar_funcoes_app()

    registro = app["montar_registro"]({
        "delivery": "3787816621",
        "motorista": "ARIEL",
        "cliente": "WMS MAX ATACADO AV. SANTOS DUMONT",
    })

    assert registro["cliente"] == "WMS MAX ATACADO AV. SANTOS DUMONT"


def test_ariel_usa_dados_fixos_atualizados_em_novas_coletas():
    app = carregar_funcoes_app()

    campos, erro = app["parse_atualizacao_rapida"]("M ARIEL D 3787816621 CL CLIENTE TESTE")
    registro = app["montar_registro"]({
        "delivery": "3787816621",
        "motorista": "ARIEL",
        "cliente": "CLIENTE TESTE",
    })

    assert erro is None
    assert campos["campos"]["motorista"] == "ARIEL NASCIMENTO"
    assert campos["campos"]["cpf"] == "050.153.565-95"
    assert campos["campos"]["cavalo"] == "JVL8A44"
    assert campos["campos"]["carreta"] == "TRUCK"
    assert registro["motorista"] == "ARIEL NASCIMENTO"
    assert registro["cpf"] == "050.153.565-95"
    assert registro["cavalo"] == "JVL8A44"
    assert registro["carreta"] == "TRUCK"
