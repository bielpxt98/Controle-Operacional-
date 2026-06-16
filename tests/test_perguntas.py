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


if __name__ == "__main__":
    unittest.main()
