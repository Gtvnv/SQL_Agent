# Agente Text-to-SQL

Agente de linha de comando que recebe uma pergunta em português, gera uma consulta SQLite com um LLM, valida que ela é somente leitura, executa em uma conexão `mode=ro`, tenta se autocorrigir em caso de erro e responde com uma tabela e uma explicação em português. Toda interação é registrada em um log de auditoria.

## Descrição do problema

Responder perguntas sobre dados em um banco relacional exige conhecer SQL e o esquema do banco. Pessoas de negócio dependem de quem sabe escrever as consultas, e entregar a um LLM o poder de gerar SQL livremente traz riscos: a consulta pode apagar ou alterar dados, referenciar tabelas inexistentes, devolver volumes enormes de linhas ou demorar demais. Este projeto resolve a pergunta "como consultar dados em linguagem natural sem abrir mão de segurança e de rastreabilidade?" usando um banco de exemplo de uma loja.

## Objetivos

- Converter perguntas em português para SQL SQLite com um LLM, usando o esquema real do banco e exemplos few-shot como contexto.
- Garantir que só consultas de leitura (`SELECT` ou `WITH ... SELECT`, uma única instrução) cheguem ao banco, com defesa em profundidade (validador de SQL e conexão somente leitura).
- Autocorrigir erros de execução reenviando ao LLM a pergunta, a SQL e a mensagem de erro, até um limite configurável.
- Exibir a SQL gerada, o resultado em tabela e uma explicação curta em português.
- Registrar cada pergunta em um log de auditoria (JSON Lines) sem nunca expor a chave de API.
- Medir a qualidade com um conjunto de avaliação reproduzível.

## Arquitetura

A CLI chama o `Agente`, que orquestra os componentes: `Gerador_SQL` (LLM), `Validador_SQL` (`sqlglot`), `Executor_SQL` (SQLite em modo `ro`), `Explicador` (LLM) e `Log_Auditoria`. O `Extrator_Esquema` lê o esquema do banco na inicialização e o injeta no prompt.

```text
Usuário -> Interface_CLI -> Agente -> Gerador_SQL -> LlmClient
                              |-> Validador_SQL
                              |-> Executor_SQL -> Banco_Exemplo (somente leitura)
                              |-> Explicador   -> LlmClient
                              |-> Log_Auditoria (audit.jsonl)
```

Documentação detalhada em `/docs`:

- [Arquitetura (com diagrama)](docs/arquitetura.md)
- [Fluxo do Agente](docs/fluxo-do-agente.md)
- [Engenharia de prompt](docs/engenharia-de-prompt.md)
- [Esquema do Banco_Exemplo](docs/esquema-do-banco.md)
- [Decisões de segurança](docs/decisoes-de-seguranca.md)

## Tecnologias

| Tecnologia | Uso |
|---|---|
| Python 3.11+ | Linguagem |
| `sqlite3` (biblioteca padrão) | Banco de exemplo e execução em modo somente leitura |
| `sqlglot` | Análise e validação da SQL (dialeto SQLite) |
| `tabulate` | Tabelas no terminal |
| `python-dotenv` | Leitura do `.env` |
| `pyyaml` | Descrições de colunas, few-shot e conjunto de avaliação |
| `pytest` e `hypothesis` | Testes de exemplo e de propriedade |
| API de chat completions (compatível com OpenAI) | LLM, via `urllib` da biblioteca padrão |

## Pré-requisitos

- Python 3.11 ou superior.
- Uma chave de API de um provedor compatível com a API de chat completions da OpenAI (`LLM_API_KEY`) e o nome do modelo (`LLM_MODEL`).
- Acesso à internet apenas para as chamadas ao LLM. Os testes automatizados não usam rede.

## Instalação

```bash
git clone <url-do-repositorio>
cd SQL_Agent
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Crie o arquivo de configuração a partir do modelo e preencha a chave e o modelo (o `.env` está no `.gitignore` e nunca deve ser versionado):

```bash
cp .env.example .env
```

| Variável | Padrão | Descrição |
|---|---|---|
| `LLM_API_KEY` | (obrigatória) | Chave de API do LLM |
| `LLM_MODEL` | (obrigatória) | Nome do modelo |
| `DB_PATH` | `db/loja.sqlite` | Caminho do banco SQLite |
| `MAX_CORRECOES` | `3` | Correções automáticas por pergunta (1 a 10) |
| `MAX_LINHAS` | `100` | Máximo de linhas exibidas (1 a 10000) |
| `QUERY_TIMEOUT_S` | `10` | Tempo limite da consulta em segundos (1 a 300) |
| `AUDIT_PATH` | `audit.jsonl` | Arquivo do log de auditoria |

Valores numéricos inválidos ou fora da faixa usam o padrão e geram um aviso. Variáveis do ambiente do processo prevalecem sobre o `.env`.

Crie o banco de exemplo (idempotente; 6 tabelas e 145 linhas):

```bash
python db/create_db.py
```

## Execução

Iniciar o agente:

```bash
python -m sql_agent
```

Digite uma pergunta em português e pressione Enter. Para encerrar, digite `sair` (código de saída 0). Perguntas vazias ou com mais de 1.000 caracteres são rejeitadas sem chamar o LLM. Se `LLM_API_KEY` ou `LLM_MODEL` faltar, o programa informa o nome da variável e sai com código diferente de zero.

Executar os testes (não acessam a rede):

```bash
pytest
```

Executar a avaliação de qualidade (chama o LLM real e consome a API):

```bash
python -m sql_agent.evaluation
```

Capturas de tela da execução:

![Execução com sucesso](images/execucao-sucesso.png)

![Execução com rejeição pelo validador](images/execucao-rejeicao.png)

![Resultado da avaliação](images/avaliacao.png)

> **Pendente (passo manual):** as imagens acima ainda precisam ser adicionadas à pasta `images/`: `execucao-sucesso.png` (pergunta respondida com SQL, tabela e explicação), `execucao-rejeicao.png` (consulta rejeitada pelo validador) e `avaliacao.png` (saída de `python -m sql_agent.evaluation`).

## Exemplos de uso

Os resultados abaixo são reais: as SQLs vêm de `db/few_shot.yaml` e `eval/dataset.yaml` e foram executadas no banco criado por `db/create_db.py`, com a mesma formatação (`tabulate`, formato `grid`) da CLI. A SQL gerada por um LLM pode variar na forma, e a explicação em português depende do modelo, por isso não é reproduzida aqui.

### Exemplo 1: contagem

**Pergunta:** Quantos clientes existem?

```sql
SELECT COUNT(*) AS total_clientes FROM clientes
```

```text
+------------------+
|   total_clientes |
+==================+
|               15 |
+------------------+
```

### Exemplo 2: filtro

**Pergunta:** Quais são os clientes da cidade de Curitiba?

```sql
SELECT id, nome FROM clientes WHERE cidade = 'Curitiba'
```

```text
+------+--------------+
|   id | nome         |
+======+==============+
|    4 | Daniel Alves |
+------+--------------+
|    6 | Felipe Costa |
+------+--------------+
|   12 | Lucas Barros |
+------+--------------+
```

### Exemplo 3: junção

**Pergunta:** Quais são os nomes dos produtos da categoria Livros?

```sql
SELECT p.nome FROM produtos p
JOIN categorias c ON c.id = p.categoria_id
WHERE c.nome = 'Livros'
```

```text
+------------------+
| nome             |
+==================+
| Romance Clássico |
+------------------+
| Livro de Python  |
+------------------+
```

### Exemplo 4: agrupamento

**Pergunta:** Quantos pedidos existem por status?

```sql
SELECT status, COUNT(*) FROM pedidos GROUP BY status
```

```text
+-----------+------------+
| status    |   COUNT(*) |
+===========+============+
| cancelado |          5 |
+-----------+------------+
| entregue  |         15 |
+-----------+------------+
| enviado   |          5 |
+-----------+------------+
| pendente  |          5 |
+-----------+------------+
```

### Exemplo 5: ordenação

**Pergunta:** Quais são os 5 produtos mais caros?

```sql
SELECT nome, preco FROM produtos ORDER BY preco DESC LIMIT 5
```

```text
+--------------------+---------+
| nome               |   preco |
+====================+=========+
| Notebook Pro       |  4599   |
+--------------------+---------+
| Smartphone X       |  1899.9 |
+--------------------+---------+
| Cadeira Ergonômica |  1290   |
+--------------------+---------+
| Mesa de Escritório |   780.5 |
+--------------------+---------+
| Jogo de Panelas    |   459   |
+--------------------+---------+
```

### Exemplo 6: consulta rejeitada

Se o LLM (por exemplo, induzido por uma pergunta maliciosa) devolver `DROP TABLE clientes`, o `Validador_SQL` rejeita a consulta antes da execução. O motivo registrado pelo validador (executado de verdade sobre o esquema do banco de exemplo) é:

```text
instrução de escrita ou definição não permitida: DROP
```

A CLI exibe a SQL e a mensagem `Consulta reprovada pelo validador: instrução de escrita ou definição não permitida: DROP`. Nenhuma tentativa de autocorreção é feita e o banco não é tocado.

## Resultados da avaliação

O conjunto `eval/dataset.yaml` tem 17 pares `{pergunta, sql_esperada, categoria}` (filtros, agregações, junções, ordenação e agrupamento). Um par acerta quando o resultado da SQL gerada é igual ao da SQL esperada: como multiconjunto de linhas quando a esperada não tem `ORDER BY`, e na mesma ordem quando tem.

> **Pendente (passo manual):** a avaliação exige um LLM real e não foi executada ao escrever este documento. Execute `python -m sql_agent.evaluation` e substitua a linha abaixo pelos números obtidos (taxa com 1 casa decimal), adicionando também a captura `images/avaliacao.png`.

```text
Total: N | Acertos: N | Taxa: N,N%
```

Modelo usado e data da execução: _(preencher após a execução)_.

## Limitações conhecidas

- Somente SQLite e somente consultas de leitura. Não há suporte a outros bancos nem a escrita.
- A qualidade depende do modelo de LLM e do contexto fornecido. A SQL gerada pode ser válida e ainda assim responder algo diferente do pretendido.
- O esquema inteiro vai no prompt, o que limita o uso em bancos com muitas tabelas e colunas.
- Cada pergunta é independente: não há memória de conversa.
- O resultado exibido é limitado a `MAX_LINHAS` linhas (padrão 100) e a consulta tem tempo limite de `QUERY_TIMEOUT_S` segundos.
- A explicação em português é gerada pelo LLM e pode ser omitida ("explicação não disponível") se o LLM falhar ou passar de 15 s.
- A autocorreção só atua em erros de execução. Consultas rejeitadas pelo validador encerram a pergunta.
- Perguntas de até 1.000 caracteres. O log de auditoria guarda a pergunta (até 4.000 caracteres) e a SQL (até 10.000), o que pode registrar informações sensíveis digitadas pelo usuário.
- A avaliação mede acerto de resultado, não a qualidade da explicação.

## Licença

Veja o arquivo [LICENSE](LICENSE).
