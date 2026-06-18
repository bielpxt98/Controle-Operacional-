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
    "extrair_campos_operacionais_conversa",
    "identificar_acao_conversa",
    "extrair_motorista_conversa",
    "extrair_codigo_conversa",
    "extrair_contexto_linha_busca",
    "extrair_valores_alteracao_conversa",
    "extrair_observacao_livre_conversa",
    "remover_observacao_livre_conversa",
    "combinar_observacoes_conversa",
    "detectar_modo_conversa",
    "parse_atualizacao_conversa",
    "campos_atualizacao_conversa",
    "buscar_coletas_por_conversa",
    "parse_atualizacao_rapida",
    "montar_registro",
    "numero",
    "extrair_regra_bloqueio_deslocamento",
    "normalizar_observacao",
    "calcular_status_automatico",
    "preview_atualizacao_status",
    "resumo_preview_status",
    "resumo_confirmacao_conversa",
}

CONSTANTES_NECESSARIAS = {
    "MOTORISTAS_FIXOS",
    "ACOES_CONVERSA",
    "PALAVRAS_COMANDO_CONVERSA",
    "COMANDOS_CONSULTA_CONVERSA",
    "PADROES_RELATORIO_CONVERSA",
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


def test_conversa_detecta_consulta_por_comandos_iniciais_sem_confundir_atualizacao():
    app = carregar_funcoes_app()

    consultas = [
        "relatório reembolso 16/06",
        "relatorio deslocamento 10/06 a 17/06",
        "quantos deslocamentos teve entre 10/06 e 17/06",
        "quais deslocamentos teve entre 10/06 e 17/06",
        "listar bloqueios do mês",
        "mostrar SR do mês",
        "total reembolsos",
        "resumo deslocamentos",
        "DESLOCAMENTO DO DIA 13/06 AO DIA 18/06",
        "DESLOCAMENTOS DE 13/06 A 18/06",
        "DESLOCAMENTO DO DIA 13/06",
        "BLOQUEIOS DO DIA 15/06",
        "SEM FI DO DIA 18/06",
    ]
    atualizacoes = [
        "Jean finalizou Mercantil às 19:49",
        "3787805422 FI 19:49",
        "3787807939 CL ASSAI URUGUAI",
        "3787807939 M ARIEL NASCIMENTO",
    ]

    for frase in consultas:
        assert app["detectar_modo_conversa"](frase) == "CONSULTA"

    for frase in atualizacoes:
        assert app["detectar_modo_conversa"](frase) == "ATUALIZACAO"


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


def test_conversa_altera_cliente_por_aliases_e_busca_delivery_completo_final_e_linha_copiada():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "delivery": "3787832285", "motorista": "JONES ROSARIO", "cliente": "ANTIGO", "f_horario": ""},
        {"id": 2, "delivery": "3787811111", "motorista": "ARIEL NASCIMENTO", "cliente": "OUTRO", "f_horario": ""},
    ])

    exemplos = [
        "delivery 3787832285 mudar CL ASSAÍ URUGUAI",
        "delivery 3787832285 cliente ASSAI URUGUAI",
        "3787832285 CL ASSAÍ URUGUAI",
        "3787832285 alterar cliente ASSAI URUGUAI",
        "32285 CL ASSAÍ URUGUAI",
        "JONES ROSARIO | 3787832285 | ANTIGO mudar CL ASSAÍ URUGUAI",
    ]

    for frase in exemplos:
        parsed, erro = app["parse_atualizacao_conversa"](frase)
        resultados = app["buscar_coletas_por_conversa"](df, parsed)
        campos = app["campos_atualizacao_conversa"](parsed)

        assert erro is None
        assert parsed["tipo_atualizacao"] == "alteracao"
        assert parsed["novo_cliente"] == "ASSAÍ URUGUAI"
        assert campos["cliente"] == "ASSAÍ URUGUAI"
        assert len(resultados) == 1
        assert resultados.iloc[0]["id"] == 1


def test_conversa_altera_motorista_por_aliases_e_alteracao_conjunta():
    app = carregar_funcoes_app()

    exemplos = [
        "delivery 3787832285 mudar M ARIEL NASCIMENTO",
        "delivery 3787832285 motorista ARIEL NASCIMENTO",
        "3787832285 M ARIEL NASCIMENTO",
        "3787832285 alterar motorista ARIEL NASCIMENTO",
    ]

    for frase in exemplos:
        parsed, erro = app["parse_atualizacao_conversa"](frase)
        campos = app["campos_atualizacao_conversa"](parsed)

        assert erro is None
        assert parsed["tipo_atualizacao"] == "alteracao"
        assert parsed["novo_motorista"] == "ARIEL NASCIMENTO"
        assert campos["motorista"] == "ARIEL NASCIMENTO"

    parsed, erro = app["parse_atualizacao_conversa"]("delivery 3787832285\nM ARIEL NASCIMENTO\nCL ASSAÍ URUGUAI")
    campos = app["campos_atualizacao_conversa"](parsed)

    assert erro is None
    assert parsed["novo_motorista"] == "ARIEL NASCIMENTO"
    assert parsed["novo_cliente"] == "ASSAÍ URUGUAI"
    assert campos["motorista"] == "ARIEL NASCIMENTO"
    assert campos["cliente"] == "ASSAÍ URUGUAI"


def test_resumo_confirmacao_conversa_mostra_coleta_encontrada_e_alteracoes_com_seta_textual():
    app = carregar_funcoes_app()
    parsed, erro = app["parse_atualizacao_conversa"]("delivery 3787832285 mudar CL ASSAÍ URUGUAI")

    resumo = app["resumo_confirmacao_conversa"]({"delivery": "3787832285", "motorista": "JONES ROSARIO", "cliente": "ANTIGO"}, parsed)

    assert erro is None
    assert "COLETA ENCONTRADA" in resumo
    assert "ALTERAÇÕES:" in resumo
    assert "CL -> ASSAÍ URUGUAI" in resumo
    assert "CONFIRMAR?" in resumo


def test_conversa_processa_l_c_fi_df_simultaneamente_em_qualquer_ordem():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_conversa"]("ARGEMIRO 6565 L 11:50 C 14:58 FI 15:40 DF 17/06")
    campos = app["campos_atualizacao_conversa"](parsed)
    resumo = app["resumo_confirmacao_conversa"](
        {"delivery": "3787816565", "motorista": "ARGEMIRO", "cliente": "DIST SÃO ROQUE F.S"},
        parsed,
    )

    assert erro is None
    assert parsed["l_horario"] == "11:50"
    assert parsed["c_horario"] == "14:58"
    assert parsed["horario"] == "15:40"
    assert parsed["data_finalizacao"] == "17/06"
    assert campos["l_horario"] == "11:50"
    assert campos["c_horario"] == "14:58"
    assert campos["f_horario"] == "15:40"
    assert campos["data_finalizacao"] == "17/06"
    assert "L -> 11:50" in resumo
    assert "C -> 14:58" in resumo
    assert "FI -> 15:40" in resumo
    assert "DF -> 17/06" in resumo


def test_conversa_processa_l_c_fi_df_individualmente():
    app = carregar_funcoes_app()

    casos = [
        ("6565 L 11:50", "l_horario", "11:50", "L -> 11:50"),
        ("6565 C 14:58", "c_horario", "14:58", "C -> 14:58"),
        ("6565 FI 15:40", "horario", "15:40", "FI -> 15:40"),
        ("6565 DF 17/06", "data_finalizacao", "17/06", "DF -> 17/06"),
    ]

    for frase, chave, valor, linha_resumo in casos:
        parsed, erro = app["parse_atualizacao_conversa"](frase)
        campos = app["campos_atualizacao_conversa"](parsed)
        resumo = app["resumo_confirmacao_conversa"]({"delivery": "3787816565"}, parsed)

        assert erro is None
        assert parsed[chave] == valor
        assert linha_resumo in resumo
        if chave == "l_horario":
            assert campos["l_horario"] == valor
        elif chave == "c_horario":
            assert campos["c_horario"] == valor
        elif chave == "horario":
            assert campos["f_horario"] == valor
        elif chave == "data_finalizacao":
            assert campos["data_finalizacao"] == valor


def test_status_automatico_regras_observacao():
    app = carregar_funcoes_app()

    assert app["calcular_status_automatico"]("bloqueio") == "BLOQUEIO"
    assert app["calcular_status_automatico"]("O BLOQUEIO") == "BLOQUEIO"
    assert app["calcular_status_automatico"]("deslocamento sem carga") == "DESLOCAMENTO"
    assert app["calcular_status_automatico"]("BLOQUEIO e DESLOCAMENTO") == "DESLOCAMENTO"
    assert app["calcular_status_automatico"]("cliente pediu comprovante") == "EM ABERTO"
    assert app["calcular_status_automatico"]("cliente pediu comprovante", "13:44") == "FINALIZADO"
    assert app["calcular_status_automatico"]("deslocamento", "13:44") == "DESLOCAMENTO"


def test_preview_status_conta_todos_os_status_sem_alterar_outros_campos():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "status": "", "delivery": "D1", "cliente": "A", "f_horario": "13:44", "observacoes": ""},
        {"id": 2, "status": "", "delivery": "D2", "cliente": "B", "f_horario": "", "observacoes": "O BLOQUEIO"},
        {"id": 3, "status": "", "delivery": "D3", "cliente": "C", "f_horario": "", "observacoes": "deslocamento sem carga"},
        {"id": 4, "status": "", "delivery": "D4", "cliente": "D", "f_horario": "", "observacoes": ""},
    ])

    preview = app["preview_atualizacao_status"](df)
    resumo = app["resumo_preview_status"](preview)

    assert resumo == {
        "DESLOCAMENTO": 1,
        "BLOQUEIO": 1,
        "FINALIZADO": 1,
        "EM ABERTO": 1,
    }
    assert list(preview["delivery"]) == ["D1", "D2", "D3", "D4"]
    assert list(preview["cliente"]) == ["A", "B", "C", "D"]
