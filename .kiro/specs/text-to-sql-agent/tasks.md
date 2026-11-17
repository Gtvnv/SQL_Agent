# Implementation Plan: Agente Text-to-SQL

## Overview

A implementação segue o design em Python 3.11+ e usa `sqlite3`, `sqlglot`, `tabulate`, `python-dotenv`, `pyyaml`, `pytest` e `hypothesis`. A ordem é: estrutura e configuração, banco de exemplo, componentes isolados (esquema, LLM, gerador, validador, executor, explicador, auditoria), orquestração (Agente), CLI, avaliação e documentação. Cada etapa se integra à anterior, sem código órfão. Os testes automatizados usam um `LlmClient` falso e nunca acessam a rede.

Cada teste de propriedade fica em um arquivo próprio (`tests/test_prop_NN_*.py`), usa `hypothesis` com `max_examples=100` e traz o comentário `Feature: text-to-sql-agent, Property {n}: {texto}`.

## Tasks

- [ ] 1. Estrutura do projeto e configuração
  - [x] 1.1 Criar a estrutura base do repositório
    - Criar o pacote `sql_agent/` com módulos vazios, `tests/` com `conftest.py` (fixtures de banco temporário e `FakeLlmClient`), `requirements.txt` (ou `pyproject.toml`), `.gitignore` (incluindo `.env`), `.env.example` com todas as variáveis (`LLM_API_KEY`, `LLM_MODEL`, `DB_PATH`, `MAX_CORRECOES`, `MAX_LINHAS`, `QUERY_TIMEOUT_S`, `AUDIT_PATH`) sem valores secretos e `LICENSE` de código aberto com ano e titular
    - _Requirements: 8.3, 11.7_

  - [x] 1.2 Implementar `config.py`
    - Implementar `Config` (dataclass congelada, `api_key` com `repr=False`), `ConfigError`, `carregar_config(env, dotenv)` com precedência do ambiente sobre o `.env`, padrões 3/100/10 com avisos para valores inválidos ou fora da faixa, e a função `mascarar`
    - Erro com nome `LLM_API_KEY` para chave ausente, vazia ou só com espaços, e `LLM_MODEL` para modelo ausente
    - _Requirements: 5.2, 5.3, 6.3, 6.5, 8.1, 8.2, 8.4, 8.5, 8.6_

  - [x] 1.3 Property 13: Configuração numérica inválida usa o padrão
    - **Property 13: Configuração numérica inválida usa o padrão**
    - **Validates: Requirements 5.3, 6.3, 6.5**

  - [x] 1.4 Property 16: Variável de ambiente prevalece sobre o `.env`
    - **Property 16: Variável de ambiente prevalece sobre o `.env`**
    - **Validates: Requirements 8.2**

  - [x] 1.5 Property 17: Chave de API ausente ou em branco impede a inicialização
    - **Property 17: Chave de API ausente ou em branco impede a inicialização**
    - **Validates: Requirements 8.4**

  - [x] 1.6 Property 18: A chave de API nunca aparece nas saídas
    - **Property 18: A chave de API nunca aparece nas saídas**
    - **Validates: Requirements 8.6**

  - [x] 1.7 Escrever testes unitários da configuração
    - Testar modelo ausente, valores válidos mantidos e leitura do `.env`
    - _Requirements: 8.1, 8.5_

- [x] 2. Banco de exemplo e arquivos de contexto
  - [x] 2.1 Implementar `db/create_db.py`
    - Criar as 6 tabelas (categorias, produtos, clientes, funcionarios, pedidos, itens_pedido conforme o ER do design) com chaves estrangeiras, no mínimo 10 linhas por tabela e 100 no total, com valores numéricos, de data e de texto
    - Rodar em transação única: criar arquivo temporário, popular e substituir com `os.replace`; ser idempotente; em falha, sair com código diferente de zero, informar o passo e não deixar dados parciais
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 2.2 Escrever testes do `create_db.py`
    - Execução dupla com comparação de tabelas, chaves e contagens; falha injetada sem dados parciais; contagem de tabelas, FKs e linhas
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 2.3 Criar `db/schema_descriptions.yaml` e `db/few_shot.yaml`
    - Descrições de colunas (até 500 caracteres cada) e no máximo 10 pares `{pergunta, sql}` válidos sobre o Banco_Exemplo
    - _Requirements: 2.3, 3.7_

- [ ] 3. Extrator de esquema
  - [x] 3.1 Implementar `schema.py`
    - Implementar `Coluna`, `Tabela`, `SchemaInfo` (com `para_prompt`) e `extrair_esquema(conn, descricoes)` usando `sqlite_master`, `PRAGMA table_info` e `PRAGMA foreign_key_list`, excluindo `sqlite_%`
    - Truncar descrições em 500 caracteres, ignorar descrições de itens inexistentes com aviso, limitar a leitura a 10 s e encerrar com código diferente de zero em falha de acesso
    - _Requirements: 2.1, 2.3, 2.4, 2.5_

  - [x] 3.2 Property 3: Extração de esquema é completa e fiel
    - **Property 3: Extração de esquema é completa e fiel**
    - **Validates: Requirements 2.1**

  - [x] 3.3 Property 5: Descrições de itens inexistentes são ignoradas com aviso
    - **Property 5: Descrições de itens inexistentes são ignoradas com aviso**
    - **Validates: Requirements 2.4**

  - [x] 3.4 Escrever testes unitários do Extrator_Esquema
    - Caso de sucesso, banco inacessível e descrição truncada
    - _Requirements: 2.1, 2.3, 2.5, 9.5_
- [x] 4. Cliente LLM e Gerador_SQL
  - [x] 4.1 Implementar `llm.py`
    - Definir o `Protocol` `LlmClient` (`completar(system, user, timeout_s)`), as exceções `LlmTimeout`, `LlmRedeError`, `LlmLimiteError` e o adaptador de API HTTP que lê chave e modelo da `Config` e traduz erros do provedor para essas exceções
    - _Requirements: 1.6, 5.6, 8.1_

  - [x] 4.2 Implementar `generator.py`
    - Implementar `gerar`, `corrigir`, `extract_sql` e `format_sql_block` (funções puras), `GeracaoError` e a montagem do prompt com esquema completo, instrução de responder só com SQL SQLite, regra de somente leitura, até 10 exemplos few-shot e instrução `NAO_DISPONIVEL`
    - `extract_sql` usa `sqlglot.parse` para detectar várias instruções e ignora `;` final isolado
    - _Requirements: 2.2, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 5.1_

  - [x] 4.3 Property 4: O prompt contém todo o contexto configurado
    - **Property 4: O prompt contém todo o contexto configurado**
    - **Validates: Requirements 2.2, 2.3, 3.7**

  - [x] 4.4 Property 6: Extração de SQL de bloco Markdown é inversa da formatação
    - **Property 6: Extração de SQL de bloco Markdown é inversa da formatação**
    - **Validates: Requirements 3.3, 9.6**

  - [x] 4.5 Property 7: Respostas sem SQL única são rejeitadas
    - **Property 7: Respostas sem SQL única são rejeitadas**
    - **Validates: Requirements 3.4, 3.5**

  - [x] 4.6 Escrever testes unitários da extração de SQL
    - Casos de sucesso e falha (resposta vazia, duas instruções) e `NAO_DISPONIVEL`
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 9.5_

- [ ] 5. Validador_SQL
  - [x] 5.1 Implementar `validator.py`
    - Implementar `ResultadoValidacao` e `validar(sql, esquema)` com `sqlglot` (dialeto SQLite): falha de parse, uma única instrução, somente SELECT/WITH, nós de escrita/definição com a palavra-chave detectada (ignorando literais de texto) e checagem de tabelas e colunas contra o esquema, resolvendo aliases, CTEs e subconsultas
    - _Requirements: 3.1, 4.1, 4.2, 4.3, 4.5, 4.6_

  - [x] 5.2 Property 8: Consultas de leitura válidas são aprovadas
    - **Property 8: Consultas de leitura válidas são aprovadas**
    - **Validates: Requirements 3.1, 4.1**

  - [x] 5.3 Property 9: Instruções de escrita ou definição são rejeitadas
    - **Property 9: Instruções de escrita ou definição são rejeitadas**
    - **Validates: Requirements 4.2, 4.6**

  - [x] 5.4 Property 10: Múltiplas instruções são rejeitadas
    - **Property 10: Múltiplas instruções são rejeitadas**
    - **Validates: Requirements 4.3**

  - [x] 5.5 Property 11: Referências inexistentes ao esquema são rejeitadas
    - **Property 11: Referências inexistentes ao esquema são rejeitadas**
    - **Validates: Requirements 4.5**

  - [x] 5.6 Escrever testes unitários do Validador_SQL
    - Casos de aprovação e rejeição de INSERT, UPDATE, DELETE e DROP, além de tempo de validação abaixo de 500 ms
    - _Requirements: 4.1, 4.2, 9.5_

- [ ] 6. Executor_SQL
  - [x] 6.1 Implementar `executor.py`
    - Implementar `ResultadoExecucao`, `ErroExecucao`, `TempoExcedido`, `ErroAcessoBanco` e `executar(sql)` com conexão `file:{db_path}?mode=ro` (`uri=True`) sem fallback de escrita, `fetchmany(max_linhas + 1)` com `truncado` e `set_progress_handler` para o tempo limite, sem resultado parcial em erro
    - _Requirements: 4.4, 4.8, 6.3, 6.5_

  - [x] 6.2 Property 15: Limite de exibição e aviso de truncamento
    - **Property 15: Limite de exibição e aviso de truncamento**
    - **Validates: Requirements 6.3, 6.4**

  - [x] 6.3 Escrever testes unitários do Executor_SQL
    - Escrita pela conexão `ro` falha com hash do arquivo igual antes e depois, banco inacessível, zero linhas e consulta lenta com limite de 1 s
    - _Requirements: 4.4, 4.8, 6.2, 6.5_

- [ ] 7. Explicador e Log_Auditoria
  - [x] 7.1 Implementar `explainer.py`
    - Implementar `explicar(pergunta, sql, resultado)` chamando o LLM com timeout de 15 s, pedindo a descrição da consulta e o resumo com o número de linhas, limitando o texto a 1.000 caracteres e devolvendo `None` em falha ou timeout
    - _Requirements: 1.1, 6.6, 6.7_

  - [x] 7.2 Implementar `audit.py`
    - Implementar `RegistroAuditoria`, `truncar(texto, limite)` e `gravar(reg)` em JSON Lines, em thread com `join(2)`, retornando `False` em falha ou excesso de tempo, sem nova tentativa; limites de 4.000 (pergunta) e 10.000 (SQL) com marcas `*_truncada`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 7.3 Property 22: Truncamento de textos respeita os limites e sinaliza
    - **Property 22: Truncamento de textos respeita os limites e sinaliza**
    - **Validates: Requirements 1.1, 10.2**

  - [x] 7.4 Escrever testes unitários do Explicador e da auditoria
    - Falha do Explicador, falha de gravação da auditoria e medição de gravação em até 2 s
    - _Requirements: 6.7, 10.4, 10.5_

- [x] 8. Checkpoint - Componentes isolados
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Agente (orquestração)
  - [x] 9.1 Implementar `agent.py`
    - Implementar `Resposta` (`sql`, `resultado`, `explicacao`, `erro`, `etapa_falha`, `tentativas`, `status`) e `responder(pergunta)`: gerar, validar, executar, autocorrigir até `max_correcoes` (contando só envios ao LLM), explicar e gravar exatamente um registro de auditoria por pergunta
    - Rejeição do Validador encerra sem autocorreção; `LlmRedeError`/`LlmLimiteError` interrompem as tentativas; `NAO_DISPONIVEL` informa ausência de dados sem executar; nunca expor a chave de API em mensagens
    - _Requirements: 1.1, 1.6, 3.6, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.4, 5.5, 5.6, 6.5, 6.7, 8.6, 10.1, 10.3, 10.5_

  - [x] 9.2 Property 12: Autocorreção respeita o limite e para no primeiro sucesso
    - **Property 12: Autocorreção respeita o limite e para no primeiro sucesso**
    - **Validates: Requirements 5.1, 5.2, 5.4, 5.5**

  - [x] 9.3 Property 2: Falhas por pergunta não encerram a sessão
    - **Property 2: Falhas por pergunta não encerram a sessão**
    - **Validates: Requirements 1.6, 4.7, 5.6**

  - [x] 9.4 Property 21: Uma pergunta gera exatamente um registro de auditoria
    - **Property 21: Uma pergunta gera exatamente um registro de auditoria**
    - **Validates: Requirements 10.1, 10.3**

  - [x] 9.5 Escrever testes de exemplo do Agente
    - Fluxo completo com LLM falso, prompt injection com cliente falso que devolve `DROP`, erros de rede e limite durante a correção e `NAO_DISPONIVEL`
    - _Requirements: 1.1, 3.6, 4.6, 5.6_

- [ ] 10. Interface_CLI
  - [x] 10.1 Implementar `cli.py` e `__main__.py`
    - Carregar a configuração e extrair o esquema na inicialização (erro com código diferente de zero em até 2 s sem chamar LLM nem banco quando faltar chave ou modelo), laço de leitura com `input()`, rejeição de entrada vazia ou acima de 1.000 caracteres sem chamar o LLM, comando `sair` com código 0
    - Exibir SQL, tabela com `tabulate`, mensagem de zero registros, aviso de truncamento com o limite, explicação (ou "explicação não disponível"), avisos de configuração e de auditoria; capturar toda exceção de domínio por pergunta mantendo a sessão ativa
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.5, 5.3, 6.1, 6.2, 6.4, 6.7, 8.4, 8.5, 10.5_

  - [x] 10.2 Property 1: Entrada inválida é rejeitada sem acionar o LLM
    - **Property 1: Entrada inválida é rejeitada sem acionar o LLM**
    - **Validates: Requirements 1.2, 1.5**

  - [x] 10.3 Property 14: Renderização de tabela preserva colunas e linhas
    - **Property 14: Renderização de tabela preserva colunas e linhas**
    - **Validates: Requirements 6.1**

  - [x] 10.4 Escrever testes de exemplo da CLI
    - Comando `sair` com código 0, várias perguntas por sessão e inicialização sem chave de API
    - _Requirements: 1.3, 1.4, 8.4_

- [ ] 11. Avaliação de qualidade
  - [x] 11.1 Implementar `evaluation.py`
    - Implementar `comparar_resultados(gerado, esperado, ordenado)` (multiconjunto sem `ORDER BY`, ordem exata com `ORDER BY`) e `avaliar(dataset, agente)` com `RelatorioAvaliacao` (acertos, total, taxa em percentual com 1 casa, lista de falhas com pergunta, SQL gerada e motivo), timeout de 30 s por par e continuidade após falhas, além de um ponto de entrada de linha de comando
    - _Requirements: 9.2, 9.3, 9.4_

  - [x] 11.2 Criar `eval/dataset.yaml`
    - Pelo menos 15 pares `{pergunta, sql_esperada, categoria}` com pelo menos 2 por categoria (filtros, agregações, junções, ordenação, agrupamento), todos executáveis no Banco_Exemplo
    - _Requirements: 9.1_

  - [x] 11.3 Property 19: Comparação de resultados na avaliação
    - **Property 19: Comparação de resultados na avaliação**
    - **Validates: Requirements 9.2**

  - [x] 11.4 Property 20: Relatório de avaliação é consistente e resiliente a falhas
    - **Property 20: Relatório de avaliação é consistente e resiliente a falhas**
    - **Validates: Requirements 9.2, 9.3, 9.4**

  - [x] 11.5 Escrever teste de fumaça do Conjunto_Avaliação
    - Verificar pelo menos 15 pares, 2 por categoria e que cada `sql_esperada` executa no Banco_Exemplo
    - _Requirements: 9.1_

- [x] 12. Checkpoint - Sistema integrado
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Documentação do repositório
  - [x] 13.1 Escrever README.md e documentos em `/docs`
    - README em português com as 9 seções (descrição do problema, objetivos, arquitetura, tecnologias, pré-requisitos, instalação, execução, exemplos de uso, limitações), pelo menos 5 exemplos (pergunta, SQL e resultado) e espaço para os resultados da avaliação (total, acertos e taxa com 1 casa decimal)
    - Criar em `/docs` os documentos de arquitetura (com diagrama), fluxo do Agente, engenharia de prompt, esquema do Banco_Exemplo (ER em texto, com cardinalidades) e decisões de segurança
    - Referenciar no README as imagens `images/*.png` por caminho relativo
    - _Requirements: 7.5, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 13.2 Escrever testes de fumaça da documentação
    - Verificar as 9 seções não vazias do README, os 5 temas em `/docs`, LICENSE, `.env.example` com todas as variáveis lidas, `.gitignore` com `.env` e que toda imagem referenciada no README e em `/docs` existe
    - _Requirements: 8.3, 11.1, 11.2, 11.3, 11.7, 11.8_

- [x] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido.
- Cada tarefa referencia requisitos específicos para rastreabilidade.
- Testes de propriedade validam propriedades universais; testes unitários e de exemplo validam casos específicos e bordas.
- Nenhum teste automatizado chama a API real do LLM ou a rede.
- Itens que dependem de ação humana ficam fora das tarefas: as capturas de tela em `/images` (Requisito 11.3), a execução do `evaluation.py` com LLM real para preencher os números no README (Requisito 11.5) e a visibilidade pública do repositório no GitHub (Requisito 11.6).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "2.3", "3.1", "4.1"] },
    { "id": 2, "tasks": ["1.3", "1.4", "1.5", "1.6", "1.7", "2.2", "3.2", "3.3", "3.4", "4.2", "5.1", "6.1", "7.1", "7.2", "11.2"] },
    { "id": 3, "tasks": ["4.3", "4.4", "4.5", "4.6", "5.2", "5.3", "5.4", "5.5", "5.6", "6.2", "6.3", "7.3", "7.4", "9.1", "11.5"] },
    { "id": 4, "tasks": ["9.2", "9.3", "9.4", "9.5", "10.1", "11.1"] },
    { "id": 5, "tasks": ["10.2", "10.3", "10.4", "11.3", "11.4", "13.1"] },
    { "id": 6, "tasks": ["13.2"] }
  ]
}
```


