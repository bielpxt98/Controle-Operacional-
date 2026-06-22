import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from perguntas import responder_pergunta


class PerguntasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        hoje = date.today()
        mes = hoje.replace(day=1)
        self.df = pd.DataFrame(
            [
                {"data": hoje.strftime("%d/%m/%Y"), "motorista": "Jean", "delivery": "1001", "cliente": "A", "tipo_veiculo": "TRUCK", "valor_frete": "100,50", "c_horario": "09:00", "f_horario": "10:00", "observacoes": ""},
                {"data": hoje.strftime("%d/%m/%Y"), "motorista": "Jean Robson", "delivery": "1002", "cliente": "B", "tipo_veiculo": "TRUCK", "valor_frete": "200,00", "l_horario": "08:34", "c_horario": "", "f_horario": "", "observacoes": "BLOQUEIO 12:00"},
                {"data": mes.strftime("%d/%m/%Y"), "motorista": "Fabio", "delivery": "1003", "cliente": "C", "tipo_veiculo": "CARRETA", "valor_frete": 300, "l_horario": "", "c_horario": "11:00", "f_horario": "", "observacoes": "DESLOCAMENTO 13:00"},
            ]
        )
        self.csv = self.base / "dados.csv"
        self.xlsx = self.base / "dados.xlsx"
        self.db = self.base / "dados.sqlite"
        self.df.to_csv(self.csv, index=False)
        self.df.to_excel(self.xlsx, index=False)
        with sqlite3.connect(self.db) as conn:
            self.df.to_sql("deliveries", conn, index=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_quantas_coletas_motorista_hoje_csv(self):
        resposta = responder_pergunta("Quantas coletas JEAN teve hoje?", str(self.csv))
        self.assertIn("Coletas de JEAN ROBSON hoje: 2.", resposta)

    def test_coletas_por_motorista_mes_excel(self):
        resposta = responder_pergunta("Quantas coletas cada motorista teve este mês?", str(self.xlsx))
        self.assertIn("JEAN ROBSON: 2", resposta)
        self.assertIn("FABIO SOUZA: 1", resposta)

    def test_sem_fi_banco_sqlite(self):
        resposta = responder_pergunta("Quais coletas estão sem FI?", str(self.db))
        self.assertIn("Coletas sem FI: 2", resposta)
        self.assertIn("1002", resposta)
        self.assertIn("1003", resposta)
        self.assertIn("1002 | B | L 08:34 | C — | FI —", resposta)
        self.assertIn("1003 | C | L — | C 11:00 | FI —", resposta)

    def test_codigos_de_todas_sem_fi(self):
        df = pd.DataFrame(
            [
                {"motorista": "Jean", "delivery": "2001", "cliente": "Cliente A", "f_horario": ""},
                {"motorista": "Fabio", "delivery": "2002", "cliente": "Cliente B", "f_horario": "-"},
                {"motorista": "Luis", "delivery": "2003", "cliente": "Cliente C", "f_horario": None},
                {"motorista": "Jones", "delivery": "2004", "cliente": "Cliente D", "f_horario": float("nan")},
                {"motorista": "Gabriel", "delivery": "2005", "cliente": "Cliente E", "f_horario": "12:00"},
            ]
        )
        caminho = self.base / "codigos_sem_fi.csv"
        df.to_csv(caminho, index=False)

        resposta = responder_pergunta("Me envie o código de todas que estão sem FI", str(caminho))

        self.assertIn("D 2001 | JEAN ROBSON | Cliente A", resposta)
        self.assertIn("D 2002 | FABIO SOUZA | Cliente B", resposta)
        self.assertIn("D 2003 | LUIS CARLOS | Cliente C", resposta)
        self.assertIn("D 2004 | JONES ROSARIO | Cliente D", resposta)
        self.assertNotIn("2005", resposta)
        self.assertNotIn("Coletas sem FI", resposta)

    def test_valor_total_por_motorista(self):
        resposta = responder_pergunta("Qual valor total por motorista no mês?", str(self.csv))
        self.assertIn("JEAN ROBSON: R$ 300,50", resposta)
        self.assertIn("FABIO SOUZA: R$ 300,00", resposta)

    def test_motorista_com_mais_coletas(self):
        resposta = responder_pergunta("Qual motorista teve mais coletas?", str(self.csv))
        self.assertIn("JEAN ROBSON (2 coleta(s))", resposta)

    def test_consulta_por_tipo_veiculo(self):
        resposta = responder_pergunta("Quais coletas foram com TRUCK?", str(self.csv))
        self.assertIn("DATA", resposta)
        self.assertIn("M JEAN ROBSON", resposta)
        self.assertIn("D 1001", resposta)
        self.assertIn("VEÍCULO TRUCK", resposta)
        self.assertIn("TOTAL DE COLETAS COM TRUCK: 2", resposta)
        self.assertNotIn("1003", resposta)

    def test_consulta_tipo_veiculo_motorista(self):
        resposta = responder_pergunta("Quantas coletas com TRUCK Jean fez?", str(self.csv))
        self.assertIn("TOTAL DE COLETAS COM TRUCK: 2", resposta)

    def test_consulta_tipo_veiculo_por_motorista(self):
        resposta = responder_pergunta("Separar por motorista as coletas feitas com TRUCK", str(self.csv))
        self.assertIn("MOTORISTA JEAN ROBSON (2 coleta(s))", resposta)

    def test_status_por_data_aceita_variacoes_e_retorna_linhas_operacionais(self):
        data_consulta = date(2026, 6, 17)
        caminho = self.base / "status_data.csv"
        pd.DataFrame(
            [
                {"data": "17/06/2026", "motorista": "Fabio", "delivery": "3787807939", "cliente": "COMERCIAL SEIS IRMÃOS", "paletes": 272, "valor_frete": "1468,13", "l_horario": "12:23", "f_horario": "16:04"},
                {"data": "18/06/2026", "motorista": "Jean", "delivery": "3787805566", "cliente": "ASSAÍ PARIPE", "paletes": 117, "valor_frete": "992,17", "l_horario": "08:08", "c_horario": "09:31", "f_horario": "13:44"},
            ]
        ).to_csv(caminho, index=False)

        for pergunta in ["STATUS 17/06", "STATUS DE 17/06", "STATUS DIA 17/06", "STATUS DO DIA 17/06/2026", "STATUS DIA 17"]:
            resposta = responder_pergunta(pergunta, str(caminho))
            self.assertIn("D 3787807939 M FABIO SOUZA CL COMERCIAL SEIS IRMÃOS L 12:23 FI 16:04", resposta)
            self.assertNotIn("DATA", resposta)
            self.assertNotIn("P 272", resposta)
            self.assertNotIn("V 1.468,13", resposta)
            self.assertNotIn("3787805566", resposta)

    def test_status_por_periodo_hoje_ontem_e_em_aberto_hoje(self):
        hoje = date.today()
        ontem = hoje - timedelta(days=1)
        caminho = self.base / "status_periodo.csv"
        pd.DataFrame(
            [
                {"data": ontem.strftime("%d/%m/%Y"), "motorista": "Fabio", "delivery": "3787807939", "cliente": "A", "f_horario": "16:04"},
                {"data": hoje.strftime("%d/%m/%Y"), "motorista": "Jean", "delivery": "3787805566", "cliente": "B", "f_horario": ""},
                {"data": hoje.strftime("%d/%m/%Y"), "motorista": "Luis", "delivery": "3787805454", "cliente": "C", "f_horario": "13:44"},
            ]
        ).to_csv(caminho, index=False)

        resposta_hoje = responder_pergunta("STATUS DE HOJE", str(caminho))
        self.assertIn("3787805566", resposta_hoje)
        self.assertIn("3787805454", resposta_hoje)
        self.assertNotIn("3787807939", resposta_hoje)

        resposta_ontem = responder_pergunta("STATUS DE ONTEM", str(caminho))
        self.assertIn("3787807939", resposta_ontem)
        self.assertNotIn("3787805566", resposta_ontem)

        resposta_aberto = responder_pergunta("STATUS EM ABERTO DE HOJE", str(caminho))
        self.assertIn("3787805566", resposta_aberto)
        self.assertNotIn("3787805454", resposta_aberto)

        resposta_periodo = responder_pergunta(
            f"STATUS DE {ontem.strftime('%d/%m')} A {hoje.strftime('%d/%m')}",
            str(caminho),
        )
        self.assertIn("3787807939", resposta_periodo)
        self.assertIn("3787805454", resposta_periodo)

    def test_consulta_por_motorista_e_delivery_com_variacoes(self):
        caminho = self.base / "status_motorista_delivery.csv"
        pd.DataFrame(
            [
                {"data": date.today().strftime("%d/%m/%Y"), "motorista": "Jean", "delivery": "3787805454", "cliente": "ASSAÍ PARIPE", "f_horario": ""},
                {"data": date.today().strftime("%d/%m/%Y"), "motorista": "Fabio", "delivery": "3787807939", "cliente": "COMERCIAL SEIS IRMÃOS", "f_horario": "16:04"},
            ]
        ).to_csv(caminho, index=False)

        resposta_motorista = responder_pergunta("JEAN HOJE", str(caminho))
        self.assertIn("M JEAN ROBSON D 3787805454", resposta_motorista)
        self.assertNotIn("3787807939", resposta_motorista)

        resposta_status_motorista = responder_pergunta("STATUS FABIO", str(caminho))
        self.assertIn("D 3787807939 M FABIO SOUZA", resposta_status_motorista)
        self.assertNotIn("3787805454", resposta_status_motorista)

        for pergunta in ["STATUS 5454", "STATUS DELIVERY 3787805454", "COMO ESTÁ A 5454", "CONSULTAR 5454"]:
            resposta_delivery = responder_pergunta(pergunta, str(caminho))
            self.assertIn("D 3787805454", resposta_delivery)
            self.assertIn("CL ASSAÍ PARIPE", resposta_delivery)
            self.assertNotIn("3787807939", resposta_delivery)

    def test_pergunta_quantas_coletas_motorista_mes_dataframe(self):
        resposta = responder_pergunta("Quantas coletas Jean fez este mês?", str(self.csv))
        self.assertIn("JEAN REALIZOU 2 COLETA(S) ESTE MÊS.", resposta)

    def test_pergunta_quantas_coletas_motorista_sem_periodo(self):
        resposta = responder_pergunta("quantas coletas jean fez?", str(self.csv))
        self.assertIn("JEAN REALIZOU 2 COLETA(S).", resposta)

    def test_cria_coluna_tipo_veiculo_quando_nao_existe(self):
        caminho = self.base / "sem_veiculo.csv"
        self.df.drop(columns=["tipo_veiculo"]).to_csv(caminho, index=False)
        resposta = responder_pergunta("Quais coletas foram com TRUCK?", str(caminho))
        self.assertIn("TOTAL DE COLETAS COM TRUCK: 0", resposta)
        self.assertIn("tipo_veiculo", pd.read_csv(caminho).columns)

    def test_observacoes_sr_reembolso_mes(self):
        df = pd.concat([self.df, pd.DataFrame([{"data": date.today().strftime("%d/%m/%Y"), "motorista": "Luis", "delivery": "1004", "cliente": "D", "observacoes": "SR 12345 reembolso"}])], ignore_index=True)
        caminho = self.base / "sr.csv"
        df.to_csv(caminho, index=False)
        resposta = responder_pergunta("Quantos SR teve este mês?", str(caminho))
        self.assertIn("TOTAL DE SR/REEMBOLSO: 1", resposta)
        lista = responder_pergunta("Mostrar SR de 01/01/2000 a 31/12/2099", str(caminho))
        self.assertIn("DATA", lista)
        self.assertIn("D 1004", lista)
        self.assertIn("O SR 12345 REEMBOLSO", lista)

    def test_observacoes_deslocamento_por_motivo(self):
        df = pd.concat([self.df, pd.DataFrame([{"data": date.today().strftime("%d/%m/%Y"), "motorista": "Jones", "delivery": "1005", "cliente": "E", "observacoes": "desloc sem carga"}])], ignore_index=True)
        caminho = self.base / "desloc.csv"
        df.to_csv(caminho, index=False)
        resposta = responder_pergunta("Quantos deslocamentos por motivo?", str(caminho))
        self.assertIn("TOTAL DE DESLOCAMENTOS: 2", resposta)
        self.assertIn("SEM CARGA: 1", resposta)

    def test_observacoes_bloqueio_por_motorista(self):
        df = pd.concat([self.df, pd.DataFrame([{"data": date.today().strftime("%d/%m/%Y"), "motorista": "Jean", "delivery": "1006", "cliente": "F", "observacoes": "bloq cliente fechado"}])], ignore_index=True)
        caminho = self.base / "bloqueio.csv"
        df.to_csv(caminho, index=False)
        resposta = responder_pergunta("Quantos bloqueios por motorista?", str(caminho))
        self.assertIn("TOTAL DE BLOQUEIOS: 2", resposta)
        self.assertIn("JEAN ROBSON: 2", resposta)

    def test_observacao_bloqueio_com_horario(self):
        df = pd.concat([self.df, pd.DataFrame([{"data": date.today().strftime("%d/%m/%Y"), "motorista": "Gabriel", "delivery": "1007", "cliente": "G", "observacoes": "MOTORISTA TERCEIRIZADO B (16:20)"}])], ignore_index=True)
        caminho = self.base / "bloqueio_horario.csv"
        df.to_csv(caminho, index=False)
        resposta = responder_pergunta("Mostrar bloqueios de 01/01/2000 a 31/12/2099", str(caminho))
        self.assertIn("D 1007", resposta)
        self.assertIn("F 16:20 O MOTORISTA TERCEIRIZADO BLOQUEIO ÀS 16:20", resposta)

    def test_consulta_cliente_livre(self):
        df = pd.concat([self.df, pd.DataFrame([{"data": date.today().strftime("%d/%m/%Y"), "motorista": "Luis", "delivery": "1008", "cliente": "ASSAÍ", "observacoes": ""}])], ignore_index=True)
        caminho = self.base / "cliente.csv"
        df.to_csv(caminho, index=False)
        resposta = responder_pergunta("Mostre todas as coletas do cliente ASSAÍ.", str(caminho))
        self.assertIn("Coletas do cliente ASSAI: 1", resposta)
        self.assertIn("1008", resposta)
        self.assertNotIn("1001", resposta)

    def test_observacoes_deslocamento_por_motorista_nome(self):
        resposta = responder_pergunta("Quantos deslocamentos Fabio teve?", str(self.csv))
        self.assertIn("TOTAL DE DESLOCAMENTOS DE FABIO SOUZA: 1", resposta)

    def test_observacoes_bloqueio_por_motorista_nome(self):
        resposta = responder_pergunta("Quantos bloqueios Jean teve?", str(self.csv))
        self.assertIn("TOTAL DE BLOQUEIOS DE JEAN ROBSON: 1", resposta)

    def test_deslocamento_intervalo_datas_sem_ano(self):
        ano = date.today().year
        df = pd.DataFrame([
            {"data": f"10/06/{ano}", "motorista": "Jean", "delivery": "2001", "cliente": "A", "observacoes": "DESLOCAMENTO CLIENTE FECHADO"},
            {"data": f"17/06/{ano}", "motorista": "Fabio", "delivery": "2002", "cliente": "B", "observacoes": "O DESLOCAMENTO"},
            {"data": f"18/06/{ano}", "motorista": "Luis", "delivery": "2003", "cliente": "C", "observacoes": "DESLOCAMENTO"},
        ])
        caminho = self.base / "desloc_periodo.csv"
        df.to_csv(caminho, index=False)
        resposta = responder_pergunta("quantas coletas tiveram deslocamento do dia 10/06 ao dia 17/06", str(caminho))
        self.assertIn("TOTAL DE DESLOCAMENTOS: 2", resposta)



    def test_status_delivery_status_hoje_e_em_aberto_operacional(self):
        hoje = date.today().strftime("%d/%m/%Y")
        df = pd.DataFrame([
            {"data": hoje, "motorista": "Fabio", "delivery": "3787849356", "cliente": "GMF FEIRA DE SANTANA", "paletes": 476, "valor_frete": "2189,60", "l_horario": "08:00", "c_horario": "10:00", "f_horario": "", "observacoes": ""},
            {"data": hoje, "motorista": "Jones", "delivery": "3787849414", "cliente": "DROGARIA SÃO PAULO", "paletes": 272, "valor_frete": "992,17", "l_horario": "08:15", "c_horario": "10:34", "f_horario": "11:00", "observacoes": ""},
        ])
        caminho = self.base / "operacional.csv"
        df.to_csv(caminho, index=False)

        status = responder_pergunta("STATUS DA DELIVERY 3787849414", str(caminho))
        self.assertNotIn("DATA", status)
        self.assertNotIn("P 272", status)
        self.assertNotIn("V 992,17", status)
        self.assertEqual(
            status,
            "D 3787849414 M JONES ROSARIO CL DROGARIA SÃO PAULO L 08:15 C 10:34 FI 11:00",
        )

        status_como_esta = responder_pergunta("COMO ESTÁ A 9414", str(caminho))
        self.assertEqual(status_como_esta, status)

        hoje_resposta = responder_pergunta("STATUS DE HOJE", str(caminho))
        self.assertNotIn("DATA", hoje_resposta)
        self.assertNotIn("P 476", hoje_resposta)
        self.assertNotIn("V 2.189,60", hoje_resposta)
        self.assertIn("D 3787849356", hoje_resposta)
        self.assertIn("D 3787849414", hoje_resposta)

        aberto = responder_pergunta("EM ABERTO", str(caminho))
        self.assertIn("D 3787849356", aberto)
        self.assertIn("L 08:00", aberto)
        self.assertNotIn("3787849414", aberto)

    def test_relatorio_deslocamento_intervalo_datas_formato_especial(self):
        ano = date.today().year
        df = pd.DataFrame([
            {"data": f"10/06/{ano}", "delivery": "3787807939", "cliente": "COMERCIAL SEIS IRMAOS", "valor_frete": "1468,13", "status": "", "observacoes": "O DESLOCAMENTO"},
            {"data": f"17/06/{ano}", "delivery": "2002", "cliente": "B", "valor_frete": "100,00", "status": "DESLOCAMENTO", "observacoes": ""},
            {"data": f"18/06/{ano}", "delivery": "2003", "cliente": "C", "valor_frete": "80,00", "status": "DESLOCAMENTO", "observacoes": ""},
        ])
        caminho = self.base / "relatorio_deslocamento.csv"
        df.to_csv(caminho, index=False)

        resposta = responder_pergunta("relatório deslocamento 10/06 17/06", str(caminho))

        self.assertIn("DATA | DELIVERY | CLIENTE | MOTORISTA | VALOR DIVIDIDO | VALOR TOTAL", resposta)
        self.assertIn(f"10/06/{ano} | 3787807939 | COMERCIAL SEIS IRMAOS |  | 734,07 | 1.468,13", resposta)
        self.assertIn(f"17/06/{ano} | 2002 | B |  | 50,00 | 100,00", resposta)
        self.assertIn("TOTAL DE REGISTROS: 2", resposta)
        self.assertIn("TOTAL PLANILHA: R$ 784,07", resposta)
        self.assertIn("TOTAL ORIGINAL: R$ 1.568,13", resposta)
        self.assertNotIn("2003", resposta)

    def test_relatorio_deslocamento_data_unica_sem_palavra_relatorio(self):
        ano = date.today().year
        df = pd.DataFrame([
            {"data": f"16/06/{ano}", "delivery": "3787762706", "cliente": "AMERICANAS S.A F.S", "valor_frete": "992,17", "status": "", "observacoes": "DESLOCAMENTO"},
            {"data": f"17/06/{ano}", "delivery": "3787762754", "cliente": "ASSAI PARIPE", "valor_frete": "1021,05", "status": "", "observacoes": "DESLOCAMENTO"},
        ])
        caminho = self.base / "relatorio_deslocamento_data_unica.csv"
        df.to_csv(caminho, index=False)

        resposta = responder_pergunta("deslocamentos 16/06", str(caminho))

        self.assertIn("DATA | DELIVERY | CLIENTE | MOTORISTA | VALOR DIVIDIDO | VALOR TOTAL", resposta)
        self.assertIn(f"16/06/{ano} | 3787762706 | AMERICANAS S.A F.S |  | 496,08 | 992,17", resposta)
        self.assertIn("TOTAL DE REGISTROS: 1", resposta)
        self.assertIn("TOTAL PLANILHA: R$ 496,08", resposta)
        self.assertIn("TOTAL ORIGINAL: R$ 992,17", resposta)
        self.assertNotIn("3787762754", resposta)

        resposta_periodo = responder_pergunta("me mande os dados dos deslocamentos do dia 16/06 ao dia 17/06", str(caminho))
        self.assertIn(f"17/06/{ano} | 3787762754 | ASSAI PARIPE |  | 510,53 | 1.021,05", resposta_periodo)
        self.assertIn("TOTAL DE REGISTROS: 2", resposta_periodo)
        self.assertIn("TOTAL PLANILHA: R$ 1.006,61", resposta_periodo)
        self.assertIn("TOTAL ORIGINAL: R$ 2.013,22", resposta_periodo)


    def test_relatorio_deslocamento_do_dia_ao_dia_nao_exige_horario(self):
        ano = date.today().year
        df = pd.DataFrame([
            {"data": f"13/06/{ano}", "delivery": "3787807939", "cliente": "COMERCIAL SEIS IRMÃOS", "motorista": "FABIO", "valor_frete": "1468,13", "status": "", "observacoes": "O DESLOCAMENTO"},
            {"data": f"14/06/{ano}", "delivery": "2001", "cliente": "A", "motorista": "JEAN", "valor_frete": "100,00", "status": "DESLOCAMENTO", "observacoes": ""},
            {"data": f"18/06/{ano}", "delivery": "2002", "cliente": "B", "motorista": "LUIS", "valor_frete": "80,00", "status": "DESLOCAMENTO", "observacoes": ""},
            {"data": f"19/06/{ano}", "delivery": "2003", "cliente": "C", "motorista": "JONES", "valor_frete": "90,00", "status": "DESLOCAMENTO", "observacoes": ""},
        ])
        caminho = self.base / "relatorio_deslocamento_do_dia.csv"
        df.to_csv(caminho, index=False)

        resposta = responder_pergunta("DESLOCAMENTO DO DIA 13/06 AO DIA 18/06", str(caminho))

        self.assertIn("DATA | DELIVERY | CLIENTE | MOTORISTA | VALOR DIVIDIDO | VALOR TOTAL", resposta)
        self.assertIn(f"13/06/{ano} | 3787807939 | COMERCIAL SEIS IRMÃOS | FABIO SOUZA | 734,07 | 1.468,13", resposta)
        self.assertIn(f"14/06/{ano} | 2001 | A | JEAN ROBSON | 50,00 | 100,00", resposta)
        self.assertIn(f"18/06/{ano} | 2002 | B | LUIS CARLOS | 40,00 | 80,00", resposta)
        self.assertNotIn("2003", resposta)

        resposta_dia = responder_pergunta("DESLOCAMENTO DO DIA 13/06", str(caminho))
        self.assertIn("3787807939", resposta_dia)
        self.assertNotIn("2001", resposta_dia)

    def test_relatorio_reembolso_intervalo_datas_valor_cheio(self):
        ano = date.today().year
        df = pd.DataFrame([
            {"data": f"15/06/{ano}", "delivery": "3787807939", "cliente": "COMERCIAL SEIS IRMAOS", "valor_frete": "1468,13", "observacoes": "SR 12345 REEMBOLSO"},
            {"data": f"16/06/{ano}", "delivery": "2002", "cliente": "B", "valor_frete": "1.000,00", "observacoes": "O REEMBOLSO"},
            {"data": f"17/06/{ano}", "delivery": "2003", "cliente": "C", "valor_frete": "80,00", "observacoes": "DESLOCAMENTO"},
        ])
        caminho = self.base / "relatorio_reembolso.csv"
        df.to_csv(caminho, index=False)

        resposta = responder_pergunta("gerar relatório de reembolsos de 10/06 até 17/06", str(caminho))

        self.assertIn("DATA | DELIVERY | CLIENTE | STATUS | VALOR", resposta)
        self.assertIn(f"15/06/{ano} | 3787807939 | COMERCIAL SEIS IRMAOS | REEMBOLSO | R$ 1.468,13", resposta)
        self.assertIn(f"16/06/{ano} | 2002 | B | REEMBOLSO | R$ 1.000,00", resposta)
        self.assertIn("TOTAL DE REGISTROS: 2", resposta)
        self.assertIn("VALOR TOTAL: R$ 2.468,13", resposta)
        self.assertNotIn("2003", resposta)

    def test_relatorio_especial_sem_registros(self):
        resposta = responder_pergunta("relatório reembolso 01/01/2000 02/01/2000", str(self.csv))
        self.assertEqual("Nenhum registro encontrado para o período informado.", resposta)

    def test_pergunta_nao_reconhecida(self):
        resposta = responder_pergunta("qual é a previsão do tempo?", str(self.csv))
        self.assertEqual("Pergunta não reconhecida.", resposta)

    def test_deslocamento_sem_resultados(self):
        resposta = responder_pergunta("quantas coletas tiveram deslocamento do dia 01/01/2000 ao dia 02/01/2000", str(self.csv))
        self.assertEqual("Nenhum registro encontrado.", resposta)


if __name__ == "__main__":
    unittest.main()


def test_status_mostra_pc_somente_quando_preenchido(tmp_path):
    caminho = tmp_path / "status_pc.csv"
    pd.DataFrame([
        {"delivery": "3787816552", "motorista": "Jones", "cliente": "ATAKAREJO SIMOES FILHO", "l_horario": "12:00", "c_horario": "14:15", "f_horario": "09:06", "data_finalizacao": "18/06", "paletes": 272, "pc": 250},
        {"delivery": "3787816553", "motorista": "Jones", "cliente": "ATAKAREJO", "l_horario": "12:00", "paletes": 272},
    ]).to_csv(caminho, index=False)

    resposta_com_pc = responder_pergunta("STATUS 3787816552", str(caminho))
    resposta_sem_pc = responder_pergunta("STATUS 3787816553", str(caminho))

    assert "PC 250" in resposta_com_pc
    assert "P 272" not in resposta_com_pc
    assert "PC" not in resposta_sem_pc

class ConsultaAdministrativaTest(unittest.TestCase):
    def test_coletas_de_hoje_formato_cliente_cidade_sigla_e_cnpj(self):
        hoje = date.today().strftime("%d/%m/%Y")
        df = pd.DataFrame([
            {"data": hoje, "motorista": "Fabio", "delivery": "3787849356", "cliente": "GMF", "cidade": "FEIRA DE SANTANA", "cnpj": "XX.XXX.XXX/XXXX-XX"},
            {"data": hoje, "motorista": "Jones", "delivery": "3787849414", "cliente": "DROGARIA SÃO PAULO", "cidade": "LAURO DE FREITAS", "cnpj": "YY.YYY.YYY/YYYY-YY"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "coletas_hoje.csv"
            df.to_csv(caminho, index=False)

            resposta = responder_pergunta("COLETAS DE HOJE", str(caminho))

            self.assertEqual(
                resposta,
                "3787849356 - GMF (FEIRA DE SANTANA) - @FA | CNPJ XX.XXX.XXX/XXXX-XX\n"
                "3787849414 - DROGARIA SAO PAULO (LAURO DE FREITAS) - @JO | CNPJ YY.YYY.YYY/YYYY-YY",
            )
            self.assertNotIn("REGISTROS ENCONTRADOS", resposta)
            self.assertNotIn("REGISTROS EXIBIDOS", resposta)
            self.assertIn("| CNPJ XX.XXX.XXX/XXXX-XX", resposta)
            self.assertNotIn("GMF - FEIRA DE SANTANA", resposta)

    def test_coletas_de_hoje_sem_cnpj_ignora_valores_vazios_e_na(self):
        hoje = date.today().strftime("%d/%m/%Y")
        df = pd.DataFrame([
            {"data": hoje, "motorista": "Fabio", "delivery": "3787849356", "cliente": "GMF", "cidade": "FEIRA DE SANTANA", "cnpj": pd.NA},
            {"data": hoje, "motorista": "Argemiro", "delivery": "3787849367", "cliente": "WMS MAX ATACADO CABULA", "cidade": None, "cnpj": float("nan")},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "coletas_hoje_sem_cnpj.csv"
            df.to_csv(caminho, index=False)

            resposta = responder_pergunta("COLETAS DE HOJE", str(caminho))

            self.assertIn("3787849356 - GMF (FEIRA DE SANTANA) - @FA", resposta)
            self.assertIn("3787849367 - WMS MAX ATACADO CABULA - @AR", resposta)
            self.assertNotIn("CLIENTE NÃO CADASTRADO", resposta)
            self.assertNotIn("CNPJ NÃO ENCONTRADO", resposta)
            self.assertNotIn("CNPJ:", resposta)


    def test_coletas_de_hoje_normaliza_nome_exibicao_wms_e_abreviacoes(self):
        hoje = date.today().strftime("%d/%m/%Y")
        df = pd.DataFrame([
            {"data": hoje, "motorista": "Ariel", "delivery": "3787849310", "cliente": "WMS (MAX ATACADO BARROS REIS)", "cidade": None, "cnpj": pd.NA},
            {"data": hoje, "motorista": "Ariel", "delivery": "3787849311", "cliente": "WMS MAX ATACADO REITOR MIGUEL (S.F)", "cidade": None, "cnpj": pd.NA},
            {"data": hoje, "motorista": "Argemiro", "delivery": "3787849312", "cliente": "WMS MAX ATACADO", "cidade": "L.F", "cnpj": "12.345.678/0001-90"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "coletas_wms.csv"
            df.to_csv(caminho, index=False)

            resposta = responder_pergunta("COLETAS DE HOJE", str(caminho))

            self.assertIn("3787849310 - WMS MAX ATACADO (BARROS REIS) - @AI", resposta)
            self.assertIn("3787849311 - WMS MAX ATACADO REITOR MIGUEL (SIMOES FILHO) - @AI", resposta)
            self.assertIn("3787849312 - WMS MAX ATACADO (LAURO DE FREITAS) - @AR", resposta)
            self.assertNotIn("REGISTROS ENCONTRADOS", resposta)
            self.assertNotIn("REGISTROS EXIBIDOS", resposta)
            self.assertIn("| CNPJ 12.345.678/0001-90", resposta)
            self.assertNotIn("WMS (MAX ATACADO", resposta)

    def test_coletas_de_hoje_exibe_todos_registros_do_dia_sem_limite_ou_cnpj(self):
        hoje = date.today().strftime("%d/%m/%Y")
        registros = [
            ("3787868756", "WMS MAX ATACADO DORIVAL CAYMMI", "Ariel"),
            ("3787867867", "WMS MAX ATACADO REITOR MIGUEL", "Ariel"),
            ("3787867863", "MERCANTIL LAURO DE FREITAS", "Ariel"),
            ("3787867862", "WMS MAX ATACADO CENTENARIO", "Maria"),
            ("3787816532", "ASSAI VASCO DA GAMA", "Gabriel"),
            ("3402204834", "BOOMIX", "Luis"),
            ("3787816418", "PAGUE MENOS", "Jones"),
            ("3787866517", "YOKI DISTRIBUIDORA", "Wilson"),
            ("3787867835", "CENCOSUD CAMACARI", "Argemiro"),
            ("3787867806", "ASSAI LAURO DE FREITAS", "Fabio"),
        ]
        df = pd.DataFrame([
            {"data": hoje, "delivery": delivery, "cliente": cliente, "motorista": motorista, "cnpj": ""}
            for delivery, cliente, motorista in registros
        ])
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "coletas_hoje_10.csv"
            df.to_csv(caminho, index=False)

            resposta = responder_pergunta("COLETAS DE HOJE", str(caminho))

            esperado = "\n".join(
                f"{delivery} - {cliente} - {sigla}"
                for delivery, cliente, sigla in [
                    ("3787868756", "WMS MAX ATACADO DORIVAL CAYMMI", "@AI"),
                    ("3787867867", "WMS MAX ATACADO REITOR MIGUEL", "@AI"),
                    ("3787867863", "MERCANTIL (LAURO DE FREITAS)", "@AI"),
                    ("3787867862", "WMS MAX ATACADO CENTENARIO", "@MA"),
                    ("3787816532", "ASSAÍ (VASCO DA GAMA)", "@GA"),
                    ("3402204834", "BOOMIX", "@LU"),
                    ("3787816418", "PAGUE MENOS", "@JO"),
                    ("3787866517", "YOKI DISTRIBUIDORA", "@WI"),
                    ("3787867835", "CENCOSUD CAMACARI", "@AR"),
                    ("3787867806", "ASSAÍ (LAURO DE FREITAS)", "@FA"),
                ]
            )
            self.assertEqual(resposta, esperado)
            self.assertNotIn("REGISTROS ENCONTRADOS", resposta)
            self.assertNotIn("REGISTROS EXIBIDOS", resposta)
            self.assertNotIn("CNPJ:", resposta)
            self.assertNotIn("DELIVERIES IGNORADOS", resposta)

    def test_coletas_hoje_e_do_dia_usam_somente_delivery_cliente_sigla(self):
        hoje = date.today().strftime("%d/%m/%Y")
        df = pd.DataFrame([
            {"data": hoje, "motorista": "Fabio Souza", "delivery": "3787867806", "cliente": "ASSAI LAURO DE FREITAS", "paletes": 272, "valor_frete": "992,17"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "coletas_hoje_curto.csv"
            df.to_csv(caminho, index=False)

            for pergunta in ["COLETAS HOJE", "COLETAS DE HOJE", "COLETAS DO DIA"]:
                resposta = responder_pergunta(pergunta, str(caminho))

                self.assertEqual(resposta, "3787867806 - ASSAÍ (LAURO DE FREITAS) - @FA")
                for termo in ["DATA", "M FABIO", "CL", "P 272", "V 992,17", "CNPJ", " FI "]:
                    self.assertNotIn(termo, resposta)


    def test_coletas_de_ontem_e_do_dia_usam_formato_admin(self):
        ontem = date.today() - timedelta(days=1)
        df = pd.DataFrame([
            {"data": ontem.strftime("%d/%m/%Y"), "motorista": "Jones", "delivery": "3787849414", "cliente": "DROGARIA SÃO PAULO", "cidade": "LAURO DE FREITAS", "cnpj": "61412110062002"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "coletas_ontem.csv"
            df.to_csv(caminho, index=False)

            resposta_ontem = responder_pergunta("COLETAS DE ONTEM", str(caminho))
            resposta_dia = responder_pergunta(f"COLETAS DO DIA {ontem.strftime('%d/%m')}", str(caminho))

            self.assertEqual(resposta_ontem, "3787849414 - DROGARIA SAO PAULO (LAURO DE FREITAS) - @JO")
            self.assertNotIn("REGISTROS ENCONTRADOS", resposta_ontem)
            self.assertNotIn("REGISTROS EXIBIDOS", resposta_ontem)
            self.assertNotIn("CNPJ:", resposta_ontem)
            self.assertEqual(resposta_dia, "3787849414 - DROGARIA SAO PAULO (LAURO DE FREITAS) - @JO")
