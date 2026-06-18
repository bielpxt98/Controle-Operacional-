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
    "cliente_combina",
    "parse_atualizacao_rapida",
    "resumo_atualizacao_rapida",
    "numero_operacional_visual",
    "montar_registro",
    "numero",
    "extrair_regra_bloqueio_deslocamento",
    "normalizar_observacao",
    "calcular_status_automatico",
    "preview_atualizacao_status",
    "resumo_preview_status",
    "resumo_confirmacao_conversa",
    "colunas_reais_deliveries",
    "resolver_coluna_delivery",
    "preparar_campos_deliveries_para_salvar",
    "valor_campo_delivery",
    "normalizar_chave_cliente_cnpj",
    "formatar_cnpj_cliente",
    "aplicar_cnpjs_clientes_cadastrados",
    "normalizar_rotulo_cadastro_cliente",
    "parse_cadastro_cliente_conversa",
    "parece_cadastro_cliente_conversa",
    "observacao_cadastro_cliente_conversa",
    "payload_cadastro_cliente_conversa",
    "resumo_cadastro_cliente_conversa",
}

CONSTANTES_NECESSARIAS = {
    "MOTORISTAS_FIXOS",
    "ACOES_CONVERSA",
    "PALAVRAS_COMANDO_CONVERSA",
    "COMANDOS_CONSULTA_CONVERSA",
    "PADROES_RELATORIO_CONVERSA",
    "CAMPOS_CADASTRO_CLIENTE_CONVERSA",
    "TABELA_DELIVERIES",
    "COLUNAS_LOGICAS_DELIVERIES",
}


def carregar_funcoes_app():
    """Carrega só funções puras do app, sem executar a interface Streamlit."""
    modulo = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    namespace = {"re": re, "datetime": datetime, "logger": logging.getLogger("test_atualizacao_conversa")}
    import pandas as pd
    namespace["pd"] = pd

    class _ExecResult:
        data = []

    class _SupabaseTabelaFake:
        def select(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def execute(self):
            return _ExecResult()

    class _SupabaseFake:
        def table(self, *args, **kwargs):
            return _SupabaseTabelaFake()

    namespace["supabase"] = _SupabaseFake()

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
    assert parsed["observacoes"] == "BLOQUEIO AS 16:22 | CLIENTE NAO QUIS CARREGAR"

    campos = app["campos_atualizacao_conversa"](parsed)
    assert campos["f_horario"] == "16:22"
    assert campos["observacoes"] == "BLOQUEIO AS 16:22 | CLIENTE NAO QUIS CARREGAR"


def test_conversa_atualiza_l_c_pc_por_frase_natural_e_confirma_sem_setas():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "delivery": "3787849356", "cliente": "GMF", "motorista": "FABIO", "l_horario": "", "c_horario": "", "f_horario": ""},
    ])

    parsed, erro = app["parse_atualizacao_conversa"](
        "fabio chegou a GMF 9356 as 08:02 e coletou as 09:24 PC 76"
    )
    resultados = app["buscar_coletas_por_conversa"](df, parsed)
    campos = app["campos_atualizacao_conversa"](parsed)
    resumo = app["resumo_confirmacao_conversa"](resultados.iloc[0].to_dict(), parsed)

    assert erro is None
    assert len(resultados) == 1
    assert campos["l_horario"] == "08:02"
    assert campos["c_horario"] == "09:24"
    assert campos["pc"] == 76
    assert "paletes_coletados" not in campos
    assert "D 3787849356\nM FABIO\nCL GMF\n\nALTERAÇÕES:\nL 08:02\nC 09:24\nPC 76" in resumo


def test_conversa_filtra_por_cliente_quando_final_tem_mais_de_um_resultado():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "delivery": "3787849356", "cliente": "OUTRO", "motorista": "FABIO", "f_horario": ""},
        {"id": 2, "delivery": "3400009356", "cliente": "GMF", "motorista": "FABIO", "f_horario": ""},
    ])

    parsed, erro = app["parse_atualizacao_conversa"]("fabio chegou a GMF 9356 as 08:02 PC 76")
    resultados = app["buscar_coletas_por_conversa"](df, parsed)

    assert erro is None
    assert resultados["id"].tolist() == [2]


def test_conversa_deslocamento_e_bloqueio_salvam_fi_observacao_e_status():
    app = carregar_funcoes_app()

    deslocamento, erro = app["parse_atualizacao_conversa"]("D 3787849356 deslocamento as 14:05")
    campos_deslocamento = app["campos_atualizacao_conversa"](deslocamento)
    bloqueio, erro_bloqueio = app["parse_atualizacao_conversa"]("D 3787849356 bloqueio as 16:20")
    campos_bloqueio = app["campos_atualizacao_conversa"](bloqueio)

    assert erro is None
    assert campos_deslocamento["f_horario"] == "14:05"
    assert campos_deslocamento["observacoes"] == "DESLOCAMENTO AS 14:05"
    assert campos_deslocamento["status"] == "DESLOCAMENTO"
    assert erro_bloqueio is None
    assert campos_bloqueio["f_horario"] == "16:20"
    assert campos_bloqueio["observacoes"] == "BLOQUEIO AS 16:20"
    assert campos_bloqueio["status"] == "BLOQUEIO"


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


def test_atualizacao_rapida_processa_todos_campos_da_mesma_linha():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_rapida"](
        "DATA 17/06/2026 M ARIEL NASCIMENTO D 3787832424 CL WMS MAX ATACADO B.F "
        "P 200.0 V 664,22 L 11:15 C 16:00 FI 09:20 DF 18/06"
    )

    assert erro is None
    assert parsed["chave_busca"] == "delivery"
    assert parsed["valor_busca"] == "3787832424"
    assert parsed["campos"]["l_horario"] == "11:15"
    assert parsed["campos"]["c_horario"] == "16:00"
    assert parsed["campos"]["f_horario"] == "09:20"
    assert parsed["campos"]["data_finalizacao"] == "18/06"
    assert app["resumo_atualizacao_rapida"](parsed, "atualizado") == (
        "D 3787832424 OK\n"
        "L 11:15\n"
        "C 16:00\n"
        "FI 09:20\n"
        "DF 18/06"
    )


def test_atualizacao_rapida_processa_linhas_independentes_com_mesmos_campos():
    app = carregar_funcoes_app()
    linhas = [
        (
            "DATA 17/06/2026 M ARIEL NASCIMENTO D 3787832424 CL WMS MAX ATACADO B.F "
            "P 200.0 V 664,22 L 11:15 C 16:00 FI 09:20 DF 18/06",
            "3787832424",
            "11:15",
            "16:00",
        ),
        (
            "DATA 17/06/2026 M ARIEL NASCIMENTO D 3787832285 CL ASSAÍ URUGUAI "
            "P 272.0 V 1021,05 L 10:30 C 11:09 FI 09:20 DF 18/06",
            "3787832285",
            "10:30",
            "11:09",
        ),
    ]

    for linha, delivery, l_horario, c_horario in linhas:
        parsed, erro = app["parse_atualizacao_rapida"](linha)

        assert erro is None
        assert parsed["valor_busca"] == delivery
        assert parsed["campos"]["l_horario"] == l_horario
        assert parsed["campos"]["c_horario"] == c_horario
        assert parsed["campos"]["f_horario"] == "09:20"
        assert parsed["campos"]["data_finalizacao"] == "18/06"


def test_atualizacao_rapida_nao_confunde_lf_do_cliente_com_campo_l():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_rapida"](
        "M JONES D 3787780078 CL DROGARIA SÃO PAULO L.F V 992,17 L 07:33 C 09:59 FI 10:10 DF 18/06"
    )

    assert erro is None
    assert parsed["campos"]["cliente"] == "DROGARIA SÃO PAULO L.F"
    assert parsed["campos"]["l_horario"] == "07:33"
    assert parsed["campos"]["c_horario"] == "09:59"
    assert parsed["campos"]["f_horario"] == "10:10"
    assert parsed["campos"]["data_finalizacao"] == "18/06"


def test_atualizacao_rapida_aceita_linha_copiada_com_pipe_e_delivery_sem_d():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_rapida"](
        "18/06/2026 | WILSON REIS | 3787850905 | YOKI DISTRIBUIDORA L 07:30 C 09:55"
    )

    assert erro is None
    assert parsed["chave_busca"] == "delivery"
    assert parsed["valor_busca"] == "3787850905"
    assert parsed["campos"]["data"] == "18/06/2026"
    assert parsed["campos"]["motorista"] == "WILSON REIS"
    assert parsed["campos"]["delivery"] == "3787850905"
    assert parsed["campos"]["cliente"] == "YOKI DISTRIBUIDORA"
    assert parsed["campos"]["l_horario"] == "07:30"
    assert parsed["campos"]["c_horario"] == "09:55"


def test_atualizacao_rapida_infer_delivery_378_ou_340_sem_marcador_d():
    app = carregar_funcoes_app()

    for delivery in ["3787850905", "3407850905"]:
        parsed, erro = app["parse_atualizacao_rapida"](f"{delivery} L 07:30 C 09:55 F 10:20")

        assert erro is None
        assert parsed["chave_busca"] == "delivery"
        assert parsed["valor_busca"] == delivery
        assert parsed["campos"]["delivery"] == delivery
        assert parsed["campos"]["l_horario"] == "07:30"
        assert parsed["campos"]["c_horario"] == "09:55"
        assert parsed["campos"]["f_horario"] == "10:20"


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


def test_resumo_confirmacao_conversa_mostra_coleta_encontrada_e_alteracoes_sem_seta():
    app = carregar_funcoes_app()
    parsed, erro = app["parse_atualizacao_conversa"]("delivery 3787832285 mudar CL ASSAÍ URUGUAI")

    resumo = app["resumo_confirmacao_conversa"]({"delivery": "3787832285", "motorista": "JONES ROSARIO", "cliente": "ANTIGO"}, parsed)

    assert erro is None
    assert "COLETA ENCONTRADA" in resumo
    assert "ALTERAÇÕES:" in resumo
    assert "CL ASSAÍ URUGUAI" in resumo
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
    assert "L 11:50" in resumo
    assert "C 14:58" in resumo
    assert "FI 15:40" in resumo
    assert "DF 17/06" in resumo


def test_conversa_processa_l_c_fi_df_individualmente():
    app = carregar_funcoes_app()

    casos = [
        ("6565 L 11:50", "l_horario", "11:50", "L 11:50"),
        ("6565 C 14:58", "c_horario", "14:58", "C 14:58"),
        ("6565 FI 15:40", "horario", "15:40", "FI 15:40"),
        ("6565 DF 17/06", "data_finalizacao", "17/06", "DF 17/06"),
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


def test_numero_preserva_centavos_e_decimal_do_banco():
    app = carregar_funcoes_app()

    assert app["numero"]("2189,60") == 2189.60
    assert app["numero"]("992,17") == 992.17
    assert app["numero"]("1021,05") == 1021.05
    assert app["numero"]("664,22") == 664.22
    assert app["numero"]("1468,13") == 1468.13
    assert app["numero"]("R$ 2.189,60") == 2189.60
    assert app["numero"]("1.021,05") == 1021.05
    assert app["numero"]("2189.6") == 2189.60
    assert app["numero"]("1021.05") == 1021.05


def test_status_automatico_regras_observacao():
    app = carregar_funcoes_app()

    assert app["calcular_status_automatico"]("bloqueio") == "BLOQUEIO"
    assert app["calcular_status_automatico"]("O BLOQUEIO") == "BLOQUEIO"
    assert app["calcular_status_automatico"]("deslocamento sem carga") == "DESLOCAMENTO"
    assert app["calcular_status_automatico"]("BLOQUEIO e DESLOCAMENTO") == "DESLOCAMENTO"
    assert app["calcular_status_automatico"]("cliente pediu comprovante") == "EM ABERTO"
    assert app["calcular_status_automatico"]("", "") == "EM ABERTO"
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


def test_pc_e_enviado_para_coluna_pc_e_nao_substitui_paletes():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_rapida"](
        "JONES D 3787816552 P 272 L 12:00 C 14:15 FI 09:06 DF 18/06 PC 250"
    )

    assert erro is None
    assert parsed["campos"]["paletes"] == 272
    assert parsed["campos"]["pc"] == 250
    assert "paletes_coletados" not in parsed["campos"]
    assert "PC 250" in app["resumo_atualizacao_rapida"](parsed, "atualizado")

    conversa, erro = app["parse_atualizacao_conversa"]("JONES 6552 PC 250")

    assert erro is None
    assert conversa["final_delivery"] == "6552"
    assert app["campos_atualizacao_conversa"](conversa)["pc"] == 250
    assert "paletes_coletados" not in app["campos_atualizacao_conversa"](conversa)


def test_validacao_salvar_usa_coluna_pc_mesmo_quando_registro_nao_tem_valor():
    app = carregar_funcoes_app()

    campos = {"l_horario": "14:00", "c_horario": "15:25", "pc": 332}
    registro_atual = {"id": 1, "delivery": "3787816412", "l_horario": "", "c_horario": ""}

    preparados = app["preparar_campos_deliveries_para_salvar"](campos, registro_atual)

    assert preparados == {"l_horario": "14:00", "c_horario": "15:25", "pc": 332}
    assert app["valor_campo_delivery"]({"pc": 332}, "pc") == 332


def test_exemplo_pc_rapido_e_conversa_mantem_pc_logico_ate_validacao():
    app = carregar_funcoes_app()

    rapido, erro = app["parse_atualizacao_rapida"](
        "D 3787816412 CL MULTICOM FEIRA DE SANTANA P 200 V 2189,60 L 14:00 C 15:25 PC 332"
    )
    conversa, erro_conversa = app["parse_atualizacao_conversa"](
        "D 3787816412 CL MULTICOM FEIRA DE SANTANA P 200 V 2189,60 L 14:00 C 15:25 PC 332"
    )

    assert erro is None
    assert erro_conversa is None
    assert rapido["campos"]["l_horario"] == "14:00"
    assert rapido["campos"]["c_horario"] == "15:25"
    assert rapido["campos"]["pc"] == 332
    assert app["campos_atualizacao_conversa"](conversa)["pc"] == 332

def test_atualizacao_rapida_cria_registro_com_wms_alagoinhas_e_paletes():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_rapida"](
        "D 3787850562 M ARGEMIRO P 120 CL WMS ALAGOINHAS V 2473,00 L 13:06"
    )

    assert erro is None
    assert parsed["campos"]["delivery"] == "3787850562"
    assert parsed["campos"]["motorista"] == "ARGEMIRO BORGES"
    assert parsed["campos"]["paletes"] == 120
    assert parsed["campos"]["cliente"] == "WMS MAX ATACADO ALAGOINHAS"
    assert parsed["campos"]["valor_frete"] == 2473.00
    assert parsed["campos"]["l_horario"] == "13:06"
    assert parsed["campos"]["status"] == "EM ABERTO"
    assert "paletes_coletados" not in parsed["campos"]


def test_d_horario_vira_deslocamento_com_prioridade_sobre_finalizado():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_rapida"](
        "D 3787850562 M ARGEMIRO CL ALAGOINHAS L 10:20 D 14:05"
    )

    assert erro is None
    assert parsed["campos"]["cliente"] == "WMS MAX ATACADO ALAGOINHAS"
    assert parsed["campos"]["f_horario"] == "14:05"
    assert parsed["campos"]["observacoes"] == "O DESLOCAMENTO AS 14:05"
    assert parsed["campos"]["status"] == "DESLOCAMENTO"


def test_conversacao_enriquece_cnpj_da_tabela_clientes_sem_mensagem_de_nao_encontrado():
    app = carregar_funcoes_app()
    coletas = pd.DataFrame([
        {"delivery": "3787849414", "cliente": "DROGARIA SÃO PAULO", "cidade": "LAURO DE FREITAS", "motorista": "JONES ROSARIO"},
        {"delivery": "3787849356", "cliente": "GMF", "cidade": "FEIRA DE SANTANA", "motorista": "FABIO SOUZA"},
    ])
    clientes = pd.DataFrame([
        {"cliente": "DROGARIA SAO PAULO", "cidade": "LAURO DE FREITAS", "cnpj": "61412110062002"},
    ])

    enriquecido = app["aplicar_cnpjs_clientes_cadastrados"](coletas, clientes)

    assert enriquecido.loc[0, "cnpj"] == "61.412.110/0620-02"
    assert enriquecido.loc[1, "cnpj"] == ""


def test_conversa_reconhece_cadastro_assistido_cliente():
    app = carregar_funcoes_app()

    texto_cadastro = """CLIENTE: ASSAÍ
NOME_EXIBICAO: ASSAÍ
RAZÃO_SOCIAL: SENDAS DISTRIBUIDORA S/A
UNIDADE: PAU DA LIMA
ENDEREÇO_REFERÊNCIA: RUA GENARO DE CARVALHO
CIDADE: SALVADOR
CNPJ: 06.057.223/0381-44
STATUS: CONFIRMADO"""

    assert app["detectar_modo_conversa"](texto_cadastro) == "CADASTRO_CLIENTE"
    parsed, erro = app["parse_cadastro_cliente_conversa"](texto_cadastro)

    assert erro is None
    assert parsed["cliente_operacao"] == "ASSAÍ"
    assert parsed["nome_exibicao"] == "ASSAÍ"
    assert parsed["razao_social"] == "SENDAS DISTRIBUIDORA S/A"
    assert parsed["cnpj"] == "06.057.223/0381-44"

    payload = app["payload_cadastro_cliente_conversa"](parsed)
    assert payload["cliente"] == "ASSAÍ"
    assert payload["razao_social"] == "SENDAS DISTRIBUIDORA S/A"
    assert payload["cidade"] == "SALVADOR"
    assert payload["endereco"] == "RUA GENARO DE CARVALHO"


def test_conversa_cadastro_cliente_exige_razao_social():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_cadastro_cliente_conversa"](
        "CLIENTE: WMS\nNOME_EXIBICAO: WMS MAX ATACADO CABULA\nCNPJ: 93.209.765/0529-31"
    )

    assert parsed is None
    assert "RAZÃO_SOCIAL" in erro


def test_resumo_cadastro_cliente_avisa_atualizacao_sem_sobrescrever():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_cadastro_cliente_conversa"](
        "CLIENTE: WMS\nNOME_EXIBICAO: WMS MAX ATACADO CABULA\n"
        "RAZÃO_SOCIAL: WMS SUPERMERCADOS DO BRASIL LTDA.\nCNPJ: 93.209.765/0529-31"
    )
    resumo = app["resumo_cadastro_cliente_conversa"](parsed, {"id": 7, "cliente": "WMS MAX ATACADO CABULA"})

    assert erro is None
    assert "CLIENTE JÁ CADASTRADO" in resumo
    assert "DESEJA ATUALIZAR?" in resumo
