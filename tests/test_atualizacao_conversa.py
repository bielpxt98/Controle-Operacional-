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
    "eh_cadastro_completo_atualizacao_rapida",
    "normalizar_data_conversa",
    "extrair_campos_operacionais_conversa",
    "identificar_acao_conversa",
    "extrair_motorista_conversa",
    "extrair_codigos_conversa",
    "extrair_codigo_conversa",
    "extrair_contexto_linha_busca",
    "extrair_valores_alteracao_conversa",
    "extrair_observacao_livre_conversa",
    "remover_observacao_livre_conversa",
    "combinar_observacoes_conversa",
    "observacao_status_operacional",
    "detectar_modo_conversa",
    "parse_atualizacao_conversa",
    "campos_atualizacao_conversa",
    "buscar_coletas_por_conversa",
    "buscar_coletas_multiplas_por_conversa",
    "resumo_coletas_atualizadas_conversa",
    "cliente_combina",
    "observacao_livre_rapida",
    "preparar_linha_atualizacao_rapida",
    "parse_atualizacao_rapida",
    "parse_glid_envio_rapido",
    "parse_glid_cliente_conversa",
    "parse_consulta_glid_conversacao",
    "buscar_cliente_por_glid_conversacao",
    "formatar_cliente_glid_conversacao",
    "responder_consulta_glid_conversacao",
    "buscar_cliente_glid_conversa",
    "resumo_glid_cliente_conversa",
    "resumo_glid_envio_rapido",
    "buscar_clientes_glid_envio_rapido",
    "resumo_atualizacao_rapida",
    "atualizar_cliente_delivery_direto",
    "resumo_mudanca_cliente_rapida",
    "atualizar_rapido_registro_no_supabase",
    "buscar_registros_atualizacao_rapida",
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
    "registrar_historico_campos",
    "registrar_historico_alteracao",
    "juntar_observacoes_sem_duplicar",
    "valor_campo_delivery",
    "colunas_reais_clientes",
    "normalizar_chave_cliente_cnpj",
    "formatar_cnpj_cliente",
    "aplicar_cnpjs_clientes_cadastrados",
    "normalizar_rotulo_cadastro_cliente",
    "mensagem_cadastro_cliente_invalido",
    "rotulos_cadastro_cliente_presentes",
    "parse_cadastro_cliente_conversa",
    "parece_cadastro_cliente_conversa",
    "texto_tem_rotulos_cliente_e_cnpj",
    "separar_blocos_atualizacao_rapida",
    "buscar_cliente_por_cnpj",
    "salvar_cliente_por_cnpj",
    "salvar_cadastro_cliente_conversa",
    "observacao_cadastro_cliente_conversa",
    "payload_cadastro_cliente_conversa",
    "preparar_payload_cliente_para_salvar",
    "salvar_cadastro_cliente_conversa",
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
    "TABELA_CLIENTES_CNPJ",
    "TABELA_AUDITORIA",
    "COLUNAS_LOGICAS_DELIVERIES",
    "ABREVIACOES_LOCALIDADE_CNPJ",
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

        def eq(self, *args, **kwargs):
            return self

        def insert(self, *args, **kwargs):
            return self

        def update(self, *args, **kwargs):
            return self

        def upsert(self, *args, **kwargs):
            raise AssertionError("clientes_cnpj não deve usar upsert")

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
    assert parsed["observacoes"] == "BLOQUEIO AS 16:22 - CLIENTE NAO QUIS CARREGAR"

    campos = app["campos_atualizacao_conversa"](parsed)
    assert campos["f_horario"] == "16:22"
    assert campos["observacoes"] == "BLOQUEIO AS 16:22 - CLIENTE NAO QUIS CARREGAR"


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
    assert "D 3787849356\nM FABIO\nCL GMF" in resumo
    assert "ALTERAÇÕES:\nL 08:02\nC 09:24\nPC 76" in resumo


def test_alteracao_manual_cliente_preserva_texto_digitado_sem_normalizar():
    app = carregar_funcoes_app()
    novo_cliente = "PANPHARMA (SC DISTRIBUIÇÃO (CAMAÇARI)"

    rapido, erro_rapido = app["parse_atualizacao_rapida"](f"D 2669 CL {novo_cliente}")
    conversa, erro_conversa = app["parse_atualizacao_conversa"](f"D 2669 CL {novo_cliente}")
    campos_conversa = app["campos_atualizacao_conversa"](conversa)
    resumo_rapido = app["resumo_mudanca_cliente_rapida"](
        {"delivery": "3787802669", "cliente": "SC DIST. CAMAÇARI"},
        rapido["campos"]["cliente"],
    )

    assert erro_rapido is None
    assert erro_conversa is None
    assert rapido["campos"]["cliente"] == novo_cliente
    assert conversa["novo_cliente"] == novo_cliente
    assert campos_conversa["cliente"] == novo_cliente
    assert "CLIENTE ATUAL: SC DIST. CAMAÇARI" in resumo_rapido
    assert f"NOVO CLIENTE: {novo_cliente}" in resumo_rapido


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



def test_atualizacao_rapida_preserva_observacao_livre_apos_o_com_d_horario():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_rapida"](
        "3787849331 L 12:00 D 15:46 O SEM AJUDANTE"
    )

    assert erro is None
    assert parsed["campos"]["delivery"] == "3787849331"
    assert parsed["campos"]["l_horario"] == "12:00"
    assert parsed["campos"]["f_horario"] == "15:46"
    assert parsed["campos"]["observacoes"] == "DESLOCAMENTO AS 15:46 - SEM AJUDANTE"
    assert app["resumo_atualizacao_rapida"](parsed, "atualizado") == (
        "D 3787849331 OK\n"
        "L 12:00\n"
        "FI 15:46\n"
        "O DESLOCAMENTO AS 15:46 - SEM AJUDANTE"
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
        cliente_esperado = "ASSAI URUGUAI" if "ASSAI" in frase else "ASSAÍ URUGUAI"
        assert parsed["novo_cliente"] == cliente_esperado
        assert campos["cliente"] == cliente_esperado
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
    assert app["calcular_status_automatico"]("BLOQUEIO e DESLOCAMENTO") == "BLOQUEIO"
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
    assert parsed["campos"]["observacoes"] == "DESLOCAMENTO AS 14:05"
    assert parsed["campos"]["status"] == "DESLOCAMENTO"


def test_atualizacao_rapida_b_horario_com_observacao_salva_bloqueio_as_horario():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_rapida"](
        "19/06/2026 | LUIS CARLOS | 3402204834 | BOOMIX | B 16:07 O PALETES MOLHADOS"
    )

    assert erro is None
    assert parsed["campos"]["f_horario"] == "16:07"
    assert parsed["campos"]["observacoes"] == "BLOQUEIO AS 16:07 - PALETES MOLHADOS"
    assert parsed["campos"]["status"] == "BLOQUEIO"


def test_conversa_d_horario_com_l_e_observacao_salva_deslocamento_as_horario():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_atualizacao_conversa"](
        "19/06/2026 | FABIO SOUZA | 3787867806 | ASSAÍ LAURO DE FREITAS | L 11:28 | D 13:02 O SEM PALETES"
    )
    campos = app["campos_atualizacao_conversa"](parsed)

    assert erro is None
    assert campos["l_horario"] == "11:28"
    assert campos["f_horario"] == "13:02"
    assert campos["observacoes"] == "DESLOCAMENTO AS 13:02 - SEM PALETES"
    assert campos["status"] == "DESLOCAMENTO"


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


def test_conversacao_enriquece_cnpj_por_nome_exibicao_normalizado_e_abreviacao():
    app = carregar_funcoes_app()
    coletas = pd.DataFrame([
        {
            "delivery": "3787878659",
            "cliente": "BUIATTE TRANSPORTE LOGISTICA (SIMOES FILHO)",
            "cidade": "",
            "motorista": "LUIS CARLOS",
        },
    ])
    clientes = pd.DataFrame([
        {
            "cliente": "BUIATTE TRANSPORTE LOGÍSTICA (S.F)",
            "nome_exibicao": "BUIATTE TRANSPORTE LOGÍSTICA (S.F)",
            "cidade": "",
            "cnpj": "12345678000199",
        },
    ])

    enriquecido = app["aplicar_cnpjs_clientes_cadastrados"](coletas, clientes)

    assert enriquecido.loc[0, "cnpj"] == "12.345.678/0001-99"


def test_conversa_glid_atualiza_cadastro_cliente_sem_buscar_delivery():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_glid_cliente_conversa"]("CL WMS MAX ATACADO BR 324 LOJA GLID 1000238063")
    resumo = app["resumo_glid_cliente_conversa"](
        {"id": 1, "cliente": "WMS MAX ATACADO BR 324 LOJA", "glid": ""},
        parsed,
    )

    assert app["detectar_modo_conversa"]("CL WMS MAX ATACADO BR 324 LOJA GLID 1000238063") == "GLID_CLIENTE"
    assert erro is None
    assert parsed["cliente"] == "WMS MAX ATACADO BR 324 LOJA"
    assert parsed["glid"] == "1000238063"
    assert parsed["campos"]["glid"] == "1000238063"
    assert "✅ Cliente encontrado." in resumo
    assert "CLIENTE: WMS MAX ATACADO BR 324 LOJA" in resumo
    assert "GLID ANTERIOR: —" in resumo
    assert "GLID NOVO: 1000238063" in resumo


def test_conversa_glid_clientes_exemplos_nao_entram_em_atualizacao_delivery():
    app = carregar_funcoes_app()

    exemplos = [
        ("CL ASSAI PARIPE GLID 1000000001", "ASSAÍ PARIPE", "1000000001"),
        (
            "CLIENTE A D R DISTRIBUIDORA DE ALIMENTOS GLID 123456789",
            "A D R DISTRIBUIDORA DE ALIMENTOS",
            "123456789",
        ),
    ]

    for frase, cliente, glid in exemplos:
        parsed, erro = app["parse_glid_cliente_conversa"](frase)
        assert app["detectar_modo_conversa"](frase) == "GLID_CLIENTE"
        assert erro is None
        assert parsed["cliente"] == cliente
        assert parsed["glid"] == glid
        assert parsed["campos"]["glid"] == glid


def test_conversa_cl_gl_curto_atualiza_glid_do_cadastro_sem_coleta():
    app = carregar_funcoes_app()
    clientes = pd.DataFrame([
        {"id": 1, "cliente": "WMS MAX ATACADO BR 324 LOJA", "nome_exibicao": "", "cidade": "FEIRA", "glid": ""},
        {"id": 2, "cliente": "WMS BR 324", "nome_exibicao": "", "cidade": "FEIRA", "glid": ""},
    ])

    exemplos = [
        ("CL WMS MAX ATACADO BR 324 LOJA GL 1000238063", "WMS MAX ATACADO BR 324 LOJA", "1000238063"),
        ("CL: WMS MAX ATACADO BR 324 LOJA GL: 1000238063", "WMS MAX ATACADO BR 324 LOJA", "1000238063"),
        ("CL CABULA GL 000000000", "CABULA", "000000000"),
        ("CL WMS BR 324 GL 1000238063", "WMS BR 324", "1000238063"),
    ]

    for frase, cliente, glid in exemplos:
        assert app["detectar_modo_conversa"](frase) == "GLID_CLIENTE"
        parsed, erro = app["parse_glid_envio_rapido"](frase)
        assert erro is None
        assert parsed["cliente"] == cliente
        assert parsed["glid"] == glid
        assert parsed["campos"]["glid"] == glid
        assert "delivery" not in parsed["campos"]
        assert "observacoes" not in parsed["campos"]

    parsed_wms, _ = app["parse_glid_envio_rapido"]("CL WMS BR 324 GL 1000238063")
    resultados = app["buscar_clientes_glid_envio_rapido"](clientes, parsed_wms)
    assert len(resultados) == 1
    assert resultados[0]["id"] == 2
    assert app["resumo_glid_envio_rapido"](parsed_wms) == (
        "✅ GLID atualizado no cadastro do cliente.\nCLIENTE: WMS BR 324\nGLID: 1000238063"
    )

def test_envio_rapido_glid_atualiza_apenas_cliente_sem_delivery():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_glid_envio_rapido"]("CL CABULA GLID 000000000")

    assert erro is None
    assert parsed["cliente"] == "CABULA"
    assert parsed["glid"] == "000000000"
    assert parsed["campos"]["glid"] == "000000000"
    assert "observacoes" not in parsed["campos"]
    assert "delivery" not in parsed["campos"]

    parsed_delivery, erro_delivery = app["parse_atualizacao_rapida"]("CL CABULA GLID 000000000")
    assert parsed_delivery is None
    assert erro_delivery == "GLID deve atualizar somente o cadastro do cliente"


def test_envio_rapido_glid_cliente_composto_e_busca_cadastro():
    app = carregar_funcoes_app()
    clientes = pd.DataFrame([
        {"id": 1, "cliente": "WMS MAX ATACADO CABULA", "cidade": "SALVADOR", "glid": ""},
        {"id": 2, "cliente": "OUTRO", "cidade": "SALVADOR", "glid": ""},
    ])

    parsed, erro = app["parse_glid_envio_rapido"]("CLIENTE WMS MAX ATACADO CABULA GLID 000000000")
    resultados = app["buscar_clientes_glid_envio_rapido"](clientes, parsed)

    assert erro is None
    assert parsed["cliente"] == "WMS MAX ATACADO CABULA"
    assert parsed["glid"] == "000000000"
    assert len(resultados) == 1
    assert resultados[0]["id"] == 1


def test_cadastro_cliente_payload_preserva_glid_com_zeros():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_cadastro_cliente_conversa"](
        "CLIENTE: WMS MAX ATACADO CABULA\n"
        "RAZÃO_SOCIAL: WMS SUPERMERCADOS DO BRASIL LTDA.\n"
        "GLID: 000000000"
    )
    payload = app["preparar_payload_cliente_para_salvar"](
        app["payload_cadastro_cliente_conversa"](parsed),
        {"cliente": "", "nome_exibicao": "", "razao_social": "", "glid": ""},
    )

    assert erro is None
    assert parsed["glid"] == "000000000"
    assert payload["glid"] == "000000000"


def test_atualizacao_rapida_preserva_bloco_cadastro_cliente_com_cnpj():
    app = carregar_funcoes_app()

    bloco = """CLIENTE: ATACADÃO BR 324 CD
NOME_EXIBICAO: ATACADÃO BR 324 CD
RAZAO_SOCIAL: ATACADÃO S.A.
CNPJ: 75.315.333/0341-94
CIDADE: SIMÕES FILHO
ENDERECO: ACESSO II BR 324, 1796 - CIA SUL
GLID: 1000054613
OBSERVACAO: DLIS"""

    assert app["texto_tem_rotulos_cliente_e_cnpj"](bloco)
    assert app["separar_blocos_atualizacao_rapida"](bloco) == [bloco]

    parsed, erro = app["parse_cadastro_cliente_conversa"](bloco)
    payload = app["payload_cadastro_cliente_conversa"](parsed)

    assert erro is None
    assert parsed["cliente_operacao"] == "ATACADÃO BR 324 CD"
    assert parsed["cnpj"] == "75.315.333/0341-94"
    assert payload["cliente"] == "ATACADÃO BR 324 CD"
    assert payload["cidade"] == "SIMÕES FILHO"
    assert payload["endereco_referencia"] == "ACESSO II BR 324, 1796 - CIA SUL"
    assert payload["glid"] == "1000054613"
    assert payload["observacao"] == "DLIS"


def test_salvar_cadastro_cliente_conversa_atualiza_por_id_sem_upsert_quando_cnpj_existe():
    app = carregar_funcoes_app()
    operacoes = []
    existente = {
        "id": 42,
        "cliente": "WMS ANTIGO",
        "nome_exibicao": "WMS ANTIGO",
        "razao_social": "WMS SUPERMERCADOS DO BRASIL LTDA.",
        "cnpj": "93.209.765/0695-83",
        "data_cadastro": "2026-01-01T00:00:00",
    }

    class Resultado:
        def __init__(self, data):
            self.data = data

    class TabelaFake:
        def __init__(self):
            self.operacao = None
            self.payload = None

        def select(self, *args, **kwargs):
            self.operacao = "select"
            return self

        def update(self, payload):
            self.operacao = "update"
            self.payload = payload
            operacoes.append(("update", payload))
            return self

        def insert(self, payload):
            operacoes.append(("insert", payload))
            raise AssertionError("não deve inserir quando CNPJ já existe")

        def upsert(self, *args, **kwargs):
            raise AssertionError("clientes_cnpj não deve usar upsert")

        def eq(self, coluna, valor):
            operacoes.append(("eq", coluna, valor))
            return self

        def limit(self, *args, **kwargs):
            return self

        def execute(self):
            if self.operacao == "select":
                return Resultado([existente])
            if self.operacao == "update":
                return Resultado([{**existente, **self.payload}])
            return Resultado([])

    class SupabaseFake:
        def table(self, nome):
            assert nome == app["TABELA_CLIENTES_CNPJ"]
            return TabelaFake()

    app["supabase"] = SupabaseFake()
    parsed, erro = app["parse_cadastro_cliente_conversa"]("""CLIENTE: WMS MAX ATACADO CENTENARIO
NOME_EXIBICAO: WMS MAX ATACADO CENTENARIO
RAZAO_SOCIAL: WMS SUPERMERCADOS DO BRASIL LTDA.
CNPJ: 93.209.765/0695-83
CIDADE: SALVADOR
ENDERECO: AVENIDA CENTENARIO, 2786
GLID: 1000238063""")

    salvo = app["salvar_cadastro_cliente_conversa"](parsed)

    assert erro is None
    assert salvo["id"] == 42
    assert salvo["cliente"] == "WMS MAX ATACADO CENTENARIO"
    assert ("eq", "cnpj", "93.209.765/0695-83") in operacoes
    assert ("eq", "id", 42) in operacoes
    assert any(op[0] == "update" for op in operacoes)
    assert not any(op[0] == "insert" for op in operacoes)


def test_salvar_cadastro_cliente_conversa_insere_sem_upsert_quando_cnpj_nao_existe():
    app = carregar_funcoes_app()
    operacoes = []

    class Resultado:
        def __init__(self, data):
            self.data = data

    class TabelaFake:
        def __init__(self):
            self.operacao = None
            self.payload = None

        def select(self, *args, **kwargs):
            self.operacao = "select"
            return self

        def insert(self, payload):
            self.operacao = "insert"
            self.payload = payload
            operacoes.append(("insert", payload))
            return self

        def update(self, payload):
            operacoes.append(("update", payload))
            raise AssertionError("não deve atualizar quando CNPJ não existe")

        def upsert(self, *args, **kwargs):
            raise AssertionError("clientes_cnpj não deve usar upsert")

        def eq(self, coluna, valor):
            operacoes.append(("eq", coluna, valor))
            return self

        def limit(self, *args, **kwargs):
            return self

        def execute(self):
            if self.operacao == "select":
                return Resultado([])
            if self.operacao == "insert":
                return Resultado([self.payload])
            return Resultado([])

    class SupabaseFake:
        def table(self, nome):
            assert nome == app["TABELA_CLIENTES_CNPJ"]
            return TabelaFake()

    app["supabase"] = SupabaseFake()
    parsed, erro = app["parse_cadastro_cliente_conversa"]("""CLIENTE: ATACADÃO BR 324 CD
NOME_EXIBICAO: ATACADÃO BR 324 CD
RAZAO_SOCIAL: ATACADÃO S.A.
CNPJ: 75.315.333/0341-94
CIDADE: SIMÕES FILHO
ENDERECO: ACESSO II BR 324, 1796 - CIA SUL
GLID: 1000054613
OBSERVACAO: DLIS""")

    salvo = app["salvar_cadastro_cliente_conversa"](parsed)

    assert erro is None
    assert salvo["cliente"] == "ATACADÃO BR 324 CD"
    assert salvo["cnpj"] == "75.315.333/0341-94"
    assert ("eq", "cnpj", "75.315.333/0341-94") in operacoes
    assert any(op[0] == "insert" for op in operacoes)
    assert not any(op[0] == "update" for op in operacoes)

def test_atualizacao_rapida_sem_cadastro_continua_separando_por_linha():
    app = carregar_funcoes_app()

    texto = "D 3787762754 FI 11:03\nD 3787833608 PC 102"

    assert app["separar_blocos_atualizacao_rapida"](texto) == [
        "D 3787762754 FI 11:03",
        "D 3787833608 PC 102",
    ]

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
    assert parsed["endereco_referencia"] == "RUA GENARO DE CARVALHO"
    assert payload["endereco_referencia"] == "RUA GENARO DE CARVALHO"


def test_conversa_cadastro_cliente_endereco_salva_em_endereco_referencia_sem_observacao():
    app = carregar_funcoes_app()

    texto_cadastro = """CLIENTE: WMS MAX ATACADO CENTENARIO
NOME_EXIBICAO: WMS MAX ATACADO CENTENARIO
RAZAO_SOCIAL: WMS SUPERMERCADOS DO BRASIL LTDA.
CNPJ: 93.209.765/0695-83
CIDADE: SALVADOR
ENDERECO: AVENIDA CENTENARIO, 2786
OBSERVACAO: AV. CENTENARIO"""

    parsed, erro = app["parse_cadastro_cliente_conversa"](texto_cadastro)
    payload_base = app["payload_cadastro_cliente_conversa"](parsed)
    payload = app["preparar_payload_cliente_para_salvar"](
        payload_base,
        {
            "cliente": "",
            "nome_exibicao": "",
            "razao_social": "",
            "cnpj": "",
            "cidade": "",
            "endereco_referencia": "",
            "observacao": "",
        },
    )

    assert erro is None
    assert parsed["endereco_referencia"] == "AVENIDA CENTENARIO, 2786"
    assert payload["cliente"] == "WMS MAX ATACADO CENTENARIO"
    assert payload["nome_exibicao"] == "WMS MAX ATACADO CENTENARIO"
    assert payload["razao_social"] == "WMS SUPERMERCADOS DO BRASIL LTDA."
    assert payload["cnpj"] == "93.209.765/0695-83"
    assert payload["cidade"] == "SALVADOR"
    assert payload["endereco_referencia"] == "AVENIDA CENTENARIO, 2786"
    assert payload["observacao"] == "AV. CENTENARIO"
    assert "endereco" not in payload


def test_conversa_cadastro_cliente_aceita_rotulos_de_endereco_referencia():
    app = carregar_funcoes_app()

    for rotulo in ["ENDEREÇO", "ENDERECO", "ENDEREÇO_REFERÊNCIA", "ENDERECO_REFERENCIA"]:
        parsed, erro = app["parse_cadastro_cliente_conversa"](
            f"CLIENTE: WMS\nRAZÃO_SOCIAL: WMS SUPERMERCADOS DO BRASIL LTDA.\n{rotulo}: RUA TESTE"
        )

        assert erro is None
        assert parsed["endereco_referencia"] == "RUA TESTE"

def test_conversa_cadastro_cliente_exige_razao_social():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_cadastro_cliente_conversa"](
        "CLIENTE: WMS\nNOME_EXIBICAO: WMS MAX ATACADO CABULA\nCNPJ: 93.209.765/0529-31"
    )

    assert parsed is None
    assert "RAZÃO_SOCIAL" in erro


def test_conversa_cadastro_cliente_sem_nome_exibicao_copia_cliente():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_cadastro_cliente_conversa"](
        "CLIENTE: WMS MAX ATACADO CENTENARIO\nRAZÃO_SOCIAL: WMS SUPERMERCADOS DO BRASIL LTDA."
    )

    assert erro is None
    assert parsed["cliente_operacao"] == "WMS MAX ATACADO CENTENARIO"
    assert parsed["nome_exibicao"] == "WMS MAX ATACADO CENTENARIO"

    payload = app["payload_cadastro_cliente_conversa"](parsed)
    assert payload["cliente"] == "WMS MAX ATACADO CENTENARIO"
    assert payload["nome_exibicao"] == "WMS MAX ATACADO CENTENARIO"


def test_preparar_payload_cliente_usa_endereco_referencia_quando_tabela_tem_coluna():
    app = carregar_funcoes_app()

    payload = app["preparar_payload_cliente_para_salvar"](
        {
            "cliente": "WMS MAX ATACADO CENTENARIO",
            "nome_exibicao": "",
            "endereco": "RUA TESTE",
            "razao_social": "WMS SUPERMERCADOS DO BRASIL LTDA.",
        },
        {
            "cliente": "",
            "nome_exibicao": "",
            "endereco_referencia": "",
            "razao_social": "",
        },
    )

    assert payload["nome_exibicao"] == "WMS MAX ATACADO CENTENARIO"
    assert payload["endereco_referencia"] == "RUA TESTE"
    assert "endereco" not in payload


def test_conversa_cadastro_cliente_nao_exige_cnpj():
    app = carregar_funcoes_app()

    parsed, erro = app["parse_cadastro_cliente_conversa"](
        "CLIENTE: WMS\nNOME_EXIBICAO: WMS MAX ATACADO CABULA\n"
        "RAZÃO_SOCIAL: WMS SUPERMERCADOS DO BRASIL LTDA."
    )

    assert erro is None
    assert parsed["cliente_operacao"] == "WMS"
    assert parsed["nome_exibicao"] == "WMS MAX ATACADO CABULA"
    assert parsed["razao_social"] == "WMS SUPERMERCADOS DO BRASIL LTDA."
    assert parsed["cnpj"] == ""


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


def test_atualizacao_rapida_cadastro_completo_usa_delivery_completo_sem_busca_por_final():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "delivery": "3787806628", "cliente": "CLIENTE ANTIGO", "motorista": "OUTRO"},
    ])

    parsed, erro = app["parse_atualizacao_rapida"](
        "DATA 22/06/2026 M FABIO D 3787816628 P 329 CL BULITTE TRANSPORTE LOGÍSTICA (S.F) V 893,64 L 08:34"
    )
    resultados = app["buscar_registros_atualizacao_rapida"](df, parsed)

    assert erro is None
    assert parsed["campos"]["data"] == "22/06/2026"
    assert parsed["campos"]["motorista"] == "FABIO SOUZA"
    assert parsed["campos"]["delivery"] == "3787816628"
    assert parsed["campos"]["paletes"] == 329
    assert parsed["campos"]["cliente"] == "BULITTE TRANSPORTE LOGÍSTICA (S.F)"
    assert parsed["campos"]["valor_frete"] == 893.64
    assert parsed["campos"]["l_horario"] == "08:34"
    assert app["eh_cadastro_completo_atualizacao_rapida"]({**parsed, "campos": parsed["campos"]})
    assert resultados == []


def test_atualizacao_rapida_parcial_continua_busca_por_final_do_delivery():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "delivery": "3787816628", "cliente": "CLIENTE", "motorista": "FABIO", "f_horario": ""},
    ])

    parsed, erro = app["parse_atualizacao_rapida"]("D 6628 FI 13:40")
    resultados = app["buscar_registros_atualizacao_rapida"](df, parsed)

    assert erro is None
    assert parsed["valor_busca"] == "6628"
    assert not app["eh_cadastro_completo_atualizacao_rapida"]({**parsed, "campos": parsed["campos"]})
    assert len(resultados) == 1
    assert resultados[0]["delivery"] == "3787816628"


def test_atualizacao_rapida_parcial_por_final_atualiza_somente_campos_informados():
    app = carregar_funcoes_app()
    casos = [
        ("D 8462 FI 12:00", {"delivery": "8462", "f_horario": "12:00"}),
        ("D 8462 FI 12:00 DF 22/06", {"delivery": "8462", "f_horario": "12:00", "data_finalizacao": "22/06"}),
        ("D 8462 PC 84", {"delivery": "8462", "pc": 84}),
        ("D 8462 C 10:30", {"delivery": "8462", "c_horario": "10:30"}),
        ("D 8462 TROCOU CL WMS MAX ATACADO BR 324 CD", {"delivery": "8462", "cliente": "WMS MAX ATACADO BR 324 CD"}),
        ("D 8462 TROCOU M ARIEL", {"delivery": "8462", "motorista": "ARIEL NASCIMENTO"}),
    ]

    for linha, esperado in casos:
        parsed, erro = app["parse_atualizacao_rapida"](linha)

        assert erro is None
        assert parsed["valor_busca"] == "8462"
        expected_keys = set(esperado)
        for campo, valor in esperado.items():
            assert parsed["campos"][campo] == valor
        campos_negocio = set(parsed["campos"]) - {"atualizado_em", "status", "cpf", "cavalo", "carreta"}
        assert campos_negocio == expected_keys
        assert not app["eh_cadastro_completo_atualizacao_rapida"](parsed)


def test_atualizacao_rapida_troca_cliente_usa_texto_apos_marcador():
    app = carregar_funcoes_app()
    casos = [
        "D 4257 CL ATACADÃO CENTRO SUL CD",
        "D 3787904257 CL ATACADÃO CENTRO SUL CD",
        "3787904257 cliente ATACADÃO CENTRO SUL CD",
        "3787904257 mudou CL ATACADÃO CENTRO SUL CD",
        "3787904257 nome ATACADÃO CENTRO SUL CD",
    ]

    for linha in casos:
        parsed, erro = app["parse_atualizacao_rapida"](linha)

        assert erro is None
        assert parsed["campos"]["cliente"] == "ATACADÃO CENTRO SUL CD"


def test_atualizacao_rapida_parcial_por_final_encontra_delivery_sem_exigir_cadastro_completo():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "delivery": "3787808462", "cliente": "CLIENTE", "motorista": "FABIO", "f_horario": ""},
    ])

    parsed, erro = app["parse_atualizacao_rapida"]("D 8462 TROCOU CL WMS MAX ATACADO BR 324 CD")
    resultados = app["buscar_registros_atualizacao_rapida"](df, parsed)

    assert erro is None
    assert parsed["campos"]["delivery"] == "8462"
    assert parsed["campos"]["cliente"] == "WMS MAX ATACADO BR 324 CD"
    assert len(resultados) == 1
    assert resultados[0]["delivery"] == "3787808462"

def test_delivery_valido_tem_exatamente_10_digitos_e_busca_final_nao_cria_codigo_curto():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "delivery": "3402204874", "cliente": "CLIENTE A", "motorista": "MOTORISTA A", "f_horario": ""},
        {"id": 2, "delivery": "3787804874", "cliente": "CLIENTE B", "motorista": "MOTORISTA B", "f_horario": ""},
    ])

    parsed, erro = app["parse_atualizacao_conversa"]("4874 B 16:07 RECUSADO PELO CLIENTE REEMBOLSO 664,22")
    resultados = app["buscar_coletas_por_conversa"](df, parsed)
    campos = app["campos_atualizacao_conversa"](parsed)

    assert erro is None
    assert not app["parece_delivery_completo"]("4874")
    assert app["parece_delivery_completo"]("3402204874")
    assert parsed["final_delivery"] == "4874"
    assert len(resultados) == 2
    assert campos["f_horario"] == "16:07"
    assert campos["status"] == "BLOQUEIO"
    assert campos["observacoes"] == "BLOQUEIO AS 16:07 | RECUSADO PELO CLIENTE | REEMBOLSO 664,22"


def test_busca_rapida_por_final_do_delivery_e_preserva_observacao_antiga_sem_duplicar():
    app = carregar_funcoes_app()
    df = pd.DataFrame([
        {"id": 1, "delivery": "3402204874", "cliente": "CLIENTE A", "motorista": "MOTORISTA A", "observacoes": "RECUSADO PELO CLIENTE"},
        {"id": 2, "delivery": "3787801111", "cliente": "CLIENTE B", "motorista": "MOTORISTA B", "observacoes": ""},
    ])

    parsed, erro = app["parse_atualizacao_rapida"]("4874 D 15:19 RECUSADO PELO CLIENTE REEMBOLSO 664,22")
    resultados = app["buscar_registros_atualizacao_rapida"](df, parsed)
    preparados = app["preparar_campos_deliveries_para_salvar"](
        parsed["campos"],
        resultados[0],
    )

    assert erro is None
    assert parsed["valor_busca"] == "4874"
    assert len(resultados) == 1
    assert parsed["campos"]["f_horario"] == "15:19"
    assert parsed["campos"]["status"] == "DESLOCAMENTO"
    assert preparados["observacoes"] == "RECUSADO PELO CLIENTE | DESLOCAMENTO AS 15:19 | REEMBOLSO 664,22"


def test_conversacao_consulta_glid_aceita_formatos_solicitados():
    app = carregar_funcoes_app()

    assert app["parse_consulta_glid_conversacao"]("GLID 4000334240") == {"glid": "4000334240"}
    assert app["parse_consulta_glid_conversacao"]("GL 4000334240") == {"glid": "4000334240"}
    assert app["parse_consulta_glid_conversacao"]("CLIENTE GLID 4000334240") == {"glid": "4000334240"}
    assert app["parse_consulta_glid_conversacao"]("CLIENTE PLANETA GLID 4000334240") is None


def test_conversacao_consulta_glid_formata_cliente_e_nao_encontrado():
    app = carregar_funcoes_app()
    cliente = {
        "cliente": "PLANETA NATURAL",
        "glid": "4000334240",
        "cnpj": "03427129000179",
        "cidade": "SALVADOR",
    }

    assert app["formatar_cliente_glid_conversacao"](cliente) == (
        "CLIENTE: PLANETA NATURAL\n"
        "GLID: 4000334240\n"
        "CNPJ: 03.427.129/0001-79\n"
        "CIDADE: SALVADOR"
    )
    assert app["formatar_cliente_glid_conversacao"](cliente, compacto=True) == "CL: PLANETA NATURAL | GLID: 4000334240"

    app["buscar_cliente_por_glid_conversacao"] = lambda glid: [cliente] if glid == "4000334240" else []
    assert "CLIENTE: PLANETA NATURAL" in app["responder_consulta_glid_conversacao"]("GLID 4000334240")
    assert app["responder_consulta_glid_conversacao"]("GLID 999") == "GLID não encontrado."


def test_parse_conversa_aceita_multiplos_finais_delivery():
    app = carregar_funcoes_app()
    parsed, erro = app["parse_atualizacao_conversa"]("ARIEL FINALIZOU 7868 E 8756 AS 11:34 DF 22/06")

    assert erro is None
    assert parsed["final_delivery"] == "7868"
    assert parsed["final_deliveries"] == ["7868", "8756"]
    assert parsed["horario"] == "11:34"
    assert parsed["data_finalizacao"] == "22/06"
    assert parsed["acao"] == "FINALIZACAO"


def test_busca_conversa_multiplos_deliveries_por_final():
    app = carregar_funcoes_app()
    parsed, _ = app["parse_atualizacao_conversa"]("ARIEL FINALIZOU 7868, 8756 E 4321 AS 11:34 DF 22/06")
    df = pd.DataFrame([
        {"id": 1, "delivery": "3787867868", "cliente": "Mercantil L.F", "motorista": "Ariel"},
        {"id": 2, "delivery": "3787868756", "cliente": "WMS Max Atacado Dorival Caymmi", "motorista": "Ariel"},
        {"id": 3, "delivery": "3787864321", "cliente": "Cliente 3", "motorista": "Ariel"},
    ])

    resultados, erros = app["buscar_coletas_multiplas_por_conversa"](df, parsed)

    assert erros == []
    assert [item["delivery"] for item in resultados] == ["3787867868", "3787868756", "3787864321"]


def test_parse_rapida_aceita_frase_natural_com_multiplos_deliveries():
    app = carregar_funcoes_app()
    parsed, erro = app["parse_atualizacao_rapida"]("FINALIZAR 7868 E 8756 AS 11:34 DF 22/06")

    assert erro is None
    assert parsed["tipo_rapida"] == "conversa_multipla"
    assert parsed["final_deliveries"] == ["7868", "8756"]
    assert parsed["campos"]["f_horario"] == "11:34"
    assert parsed["campos"]["data_finalizacao"] == "22/06"


def test_resumo_coletas_atualizadas_conversa():
    app = carregar_funcoes_app()
    resumo = app["resumo_coletas_atualizadas_conversa"]([
        {"delivery": "3787867868", "cliente": "MERCANTIL L.F", "f_horario": "11:34", "data_finalizacao": "22/06/2026"},
        {"delivery": "3787868756", "cliente": "WMS MAX ATACADO DORIVAL CAYMMI", "f_horario": "11:34", "data_finalizacao": "22/06/2026"},
    ])

    assert "✅ 2 coletas atualizadas." in resumo
    assert "3787867868 - MERCANTIL L.F" in resumo
    assert "3787868756 - WMS MAX ATACADO DORIVAL CAYMMI" in resumo


def test_salvar_cliente_por_cnpj_atualiza_quando_cnpj_ja_existe():
    app = carregar_funcoes_app()
    chamadas = []

    class Resultado:
        def __init__(self, data):
            self.data = data

    class TabelaFake:
        def __init__(self):
            self.operacao = None
            self.payload = None
            self.filtro = None

        def select(self, *args, **kwargs):
            self.operacao = "select"
            return self

        def update(self, payload):
            self.operacao = "update"
            self.payload = payload
            chamadas.append(("update", payload))
            return self

        def insert(self, payload):
            chamadas.append(("insert", payload))
            return self

        def eq(self, campo, valor):
            self.filtro = (campo, valor)
            chamadas.append(("eq", campo, valor))
            return self

        def limit(self, *args, **kwargs):
            return self

        def execute(self):
            if self.operacao == "select":
                return Resultado([{"id": 7, "cliente": "ANTIGO", "cnpj": "06.057.223/0381-44", "data_cadastro": "2026-01-01T00:00:00"}])
            if self.operacao == "update":
                return Resultado([{**self.payload, "id": 7}])
            return Resultado([])

    class SupabaseFake:
        def table(self, tabela):
            assert tabela == app["TABELA_CLIENTES_CNPJ"]
            return TabelaFake()

    historico = []
    app["supabase"] = SupabaseFake()
    app["registrar_historico_campos"] = lambda *args: historico.append(args)
    app["colunas_reais_clientes"] = lambda registro_atual=None: {"id", "cliente", "nome_exibicao", "cnpj", "razao_social", "data_cadastro", "data_ultima_atualizacao"}

    salvo = app["salvar_cliente_por_cnpj"]({
        "cliente": "ASSAÍ",
        "nome_exibicao": "ASSAÍ",
        "cnpj": "06057223038144",
        "razao_social": "SENDAS DISTRIBUIDORA S/A",
        "data_ultima_atualizacao": "2026-06-23T12:00:00",
    })

    assert salvo["id"] == 7
    assert salvo["cliente"] == "ASSAÍ"
    assert any(chamada[0] == "update" for chamada in chamadas)
    assert not any(chamada[0] == "insert" for chamada in chamadas)
    assert historico


def test_salvar_cliente_por_cnpj_insere_quando_cnpj_nao_existe():
    app = carregar_funcoes_app()
    chamadas = []

    class Resultado:
        def __init__(self, data):
            self.data = data

    class TabelaFake:
        def __init__(self):
            self.operacao = None
            self.payload = None

        def select(self, *args, **kwargs):
            self.operacao = "select"
            return self

        def insert(self, payload):
            self.operacao = "insert"
            self.payload = payload
            chamadas.append(("insert", payload))
            return self

        def update(self, payload):
            chamadas.append(("update", payload))
            return self

        def eq(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def execute(self):
            if self.operacao == "select":
                return Resultado([])
            if self.operacao == "insert":
                return Resultado([{**self.payload, "id": 8}])
            return Resultado([])

    class SupabaseFake:
        def table(self, tabela):
            assert tabela == app["TABELA_CLIENTES_CNPJ"]
            return TabelaFake()

    historico = []
    app["supabase"] = SupabaseFake()
    app["registrar_historico_campos"] = lambda *args: historico.append(args)
    app["colunas_reais_clientes"] = lambda registro_atual=None: {"id", "cliente", "nome_exibicao", "cnpj", "razao_social", "data_cadastro", "data_ultima_atualizacao"}

    salvo = app["salvar_cliente_por_cnpj"]({
        "cliente": "NOVO CLIENTE",
        "nome_exibicao": "NOVO CLIENTE",
        "cnpj": "11.222.333/0001-44",
        "razao_social": "NOVO CLIENTE LTDA",
        "data_ultima_atualizacao": "2026-06-23T12:00:00",
    })

    assert salvo["id"] == 8
    assert salvo["data_cadastro"]
    assert chamadas[0][0] == "insert"
    assert not any(chamada[0] == "update" for chamada in chamadas)
    assert historico


def test_resumo_mudanca_cliente_rapida_mostra_cliente_atual_e_novo():
    app = carregar_funcoes_app()

    resumo = app["resumo_mudanca_cliente_rapida"](
        {"cliente": "ATACADÃO CT SUL"},
        "ATACADÃO CENTRO SUL CD",
    )

    assert "CLIENTE ATUAL: ATACADÃO CT SUL" in resumo
    assert "NOVO CLIENTE: ATACADÃO CENTRO SUL CD" in resumo


def test_atualizar_cliente_delivery_direto_usa_delivery_e_payload_minimo_sem_id():
    app = carregar_funcoes_app()
    chamadas = []

    class Resultado:
        data = []

    class Query:
        def __init__(self):
            self.payload = None
            self.filtros = []

        def update(self, payload):
            self.payload = payload
            chamadas.append(("update", payload))
            return self

        def eq(self, coluna, valor):
            self.filtros.append((coluna, valor))
            chamadas.append(("eq", coluna, valor))
            return self

        def execute(self):
            chamadas.append(("execute", self.payload, tuple(self.filtros)))
            return Resultado()

    class SupabaseFake:
        def table(self, tabela):
            chamadas.append(("table", tabela))
            return Query()

    app["supabase"] = SupabaseFake()
    app["registrar_historico_campos"] = lambda *args, **kwargs: None
    app["atualizar_dataframe_principal"] = lambda: chamadas.append(("reload",))

    salvo = app["atualizar_cliente_delivery_direto"](
        "3787904257",
        "ATACADÃO CENTRO SUL CD",
        {"id": 99, "delivery": "3787904257", "cliente": "ATACADÃO CT SUL", "motorista": "NÃO ALTERAR"},
    )

    update = next(item for item in chamadas if item[0] == "update")
    assert update[1]["cliente"] == "ATACADÃO CENTRO SUL CD"
    assert set(update[1]) == {"cliente", "atualizado_em"}
    assert ("eq", "delivery", "3787904257") in chamadas
    assert not any(item[0] == "eq" and item[1] == "id" for item in chamadas)
    assert ("reload",) in chamadas
    assert salvo["cliente"] == "ATACADÃO CENTRO SUL CD"


def test_atualizar_rapido_registro_cliente_busca_id_mas_salva_por_delivery_sem_alterar_outros_campos():
    app = carregar_funcoes_app()
    chamadas = []

    class Resultado:
        data = [{"id": 7, "delivery": "3787904257", "cliente": "ATACADÃO CT SUL", "motorista": "MANTER"}]

    class Query:
        def __init__(self):
            self.payload = None
            self.filtros = []

        def select(self, *_args):
            return self

        def update(self, payload):
            self.payload = payload
            chamadas.append(("update", payload))
            return self

        def eq(self, coluna, valor):
            self.filtros.append((coluna, valor))
            chamadas.append(("eq", coluna, valor))
            return self

        def limit(self, *_args):
            return self

        def execute(self):
            return Resultado()

    class SupabaseFake:
        def table(self, tabela):
            chamadas.append(("table", tabela))
            return Query()

    app["supabase"] = SupabaseFake()
    app["registrar_historico_campos"] = lambda *args, **kwargs: None
    app["atualizar_dataframe_principal"] = lambda: chamadas.append(("reload",))

    app["atualizar_rapido_registro_no_supabase"](7, {
        "valor_busca": "3787904257",
        "campos": {"delivery": "3787904257", "cliente": "ATACADÃO CENTRO SUL CD", "status": "PENDENTE"},
    })

    update = next(item for item in chamadas if item[0] == "update")
    assert set(update[1]) == {"cliente", "atualizado_em"}
    assert ("eq", "delivery", "3787904257") in chamadas
    assert not any(item[0] == "update" and "status" in item[1] for item in chamadas)
