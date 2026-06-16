CONTROLE OPERACIONAL ONLINE EDITÁVEL

Atualização:
- Busca com edição de registros
- Exclusão de registro escolhido
- Exclusão apenas de linhas incompletas de uma delivery
- Bloqueio para evitar salvar manualmente registros incompletos
- Backup automático antes de editar/excluir/importar

Para atualizar no Streamlit:
1. No GitHub, substitua o app.py antigo por este app.py.
2. Mantenha requirements.txt.
3. Commit changes.
4. O Streamlit atualiza sozinho.

MÓDULO DE PERGUNTAS SOBRE HISTÓRICO

Foi adicionado o arquivo perguntas.py para responder perguntas simples usando somente Python, pandas e regras de palavras-chave. Não usa API paga, ChatGPT nem Gemini.

Função principal:

    from perguntas import responder_pergunta

    resposta = responder_pergunta(
        "Quantas coletas JEAN teve hoje?",
        "dados.xlsx"
    )
    print(resposta)

Formatos aceitos em caminho_dados:
- Excel: .xlsx, .xls, .xlsm
- CSV/TXT: .csv, .txt
- Banco SQLite: .db, .sqlite, .sqlite3

No SQLite, o módulo usa a tabela deliveries quando existir; caso contrário, usa a primeira tabela encontrada.

Perguntas de exemplo:
- Quantas coletas JEAN teve hoje?
- Quantas coletas JEAN teve este mês?
- Quantas coletas cada motorista teve este mês?
- Quais coletas estão sem FI?
- Quais coletas estão sem C?
- Quais coletas tiveram bloqueio?
- Quais coletas tiveram deslocamento?
- Quantas remessas tiveram no mês?
- Qual valor total por motorista no mês?
- Qual motorista teve mais coletas?

Exemplo com Excel mestre:

    print(responder_pergunta("Quais coletas estão sem FI?", "controle.xlsx"))
    print(responder_pergunta("Qual valor total por motorista no mês?", "controle.xlsx"))

Rodar testes:

    python -m unittest discover -s tests
