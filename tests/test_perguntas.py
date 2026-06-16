import sqlite3
import tempfile
import unittest
from datetime import date
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
                {"data": hoje.strftime("%d/%m/%Y"), "motorista": "Jean Robson", "delivery": "1002", "cliente": "B", "tipo_veiculo": "TRUCK", "valor_frete": "200,00", "c_horario": "", "f_horario": "", "observacoes": "BLOQUEIO 12:00"},
                {"data": mes.strftime("%d/%m/%Y"), "motorista": "Fabio", "delivery": "1003", "cliente": "C", "tipo_veiculo": "CARRETA", "valor_frete": 300, "c_horario": "11:00", "f_horario": "", "observacoes": "DESLOCAMENTO 13:00"},
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


if __name__ == "__main__":
    unittest.main()
