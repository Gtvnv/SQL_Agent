# Decisões de segurança

O LLM é tratado como fonte não confiável: a pergunta do usuário pode tentar induzi-lo a gerar SQL destrutiva (prompt injection), e o próprio modelo pode errar. Por isso a proteção não depende do prompt.

## 1. Defesa em profundidade para somente leitura

| Camada | Mecanismo | O que impede |
|---|---|---|
| Prompt | Regra de somente leitura no prompt de sistema | Reduz a chance de o modelo gerar escrita. Não é garantia |
| Extração | `extract_sql` rejeita resposta com mais de uma instrução | Encadeamento do tipo `SELECT ...; DROP TABLE ...` |
| Validador | `sqlglot` (dialeto SQLite): só `SELECT`/`WITH`, uma instrução, sem nós de escrita ou definição (`INSERT`, `UPDATE`, `DELETE`, `REPLACE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`, `DETACH`, `VACUUM`, `PRAGMA`) | SQL de escrita ou definição, antes de tocar no banco |
| Executor | Conexão `file:...?mode=ro` (`uri=True`), sem fallback de escrita | Qualquer escrita que passe pelas camadas anteriores falha com erro do SQLite |

O validador analisa a árvore sintática, não o texto. Palavras como `DELETE` dentro de um literal de texto (`WHERE nome = 'DELETE'`) não causam rejeição indevida, e comentários não escondem comandos.

## 2. Validação contra o esquema

O validador resolve aliases, CTEs e subconsultas e rejeita tabelas e colunas que não existem no esquema, informando o nome. Isso barra consultas inventadas pelo modelo antes da execução.

## 3. Sem autocorreção para SQL rejeitada

Quando o validador rejeita, a pergunta termina. Reenviar a consulta rejeitada ao LLM para "consertar" daria ao atacante mais tentativas de contornar o filtro. Só erros de execução do SQLite entram na autocorreção, que é limitada por `MAX_CORRECOES`.

## 4. Limites de recursos

- `QUERY_TIMEOUT_S` (padrão 10 s): `set_progress_handler` interrompe consultas longas.
- `MAX_LINHAS` (padrão 100): o executor busca no máximo `MAX_LINHAS + 1` linhas e indica truncamento.
- Pergunta limitada a 1.000 caracteres na CLI.
- Timeouts nas chamadas ao LLM (30 s na geração e correção, 15 s na explicação).
- Em erro, nenhum resultado parcial é exibido.

## 5. Segredos

- `LLM_API_KEY` vem do ambiente ou do `.env`. O `.env` está no `.gitignore`, e `.env.example` não tem valores secretos.
- A chave é um campo com `repr=False` em `Config`, e `HttpLlmClient` não a inclui em `repr` nem em mensagens de erro.
- O `Agente` e a CLI passam mensagens, SQL, explicação e registros de auditoria por `mascarar`, que remove o valor da chave.
- Chave ausente, vazia ou só com espaços impede a inicialização, sem chamar o LLM nem abrir o banco.

## 6. Auditoria

Cada pergunta gera um registro JSON Lines com data e hora UTC, pergunta, SQL, resultado da validação, motivo de reprovação, tentativas e status. Isso permite rastrear tentativas de uso indevido. A gravação tem limite de 2 s e, se falhar, a CLI avisa que a interação não foi auditada. O log pode conter dados digitados pelo usuário e deve ter o acesso controlado.

## 7. Limites conhecidos

- A leitura continua permitida em todas as tabelas do banco. Não há controle de acesso por usuário, coluna ou linha.
- O validador não avalia custo da consulta além do tempo limite (por exemplo, junções cartesianas lentas são interrompidas apenas pelo timeout).
- A pergunta e o esquema são enviados ao provedor do LLM. Não use dados sensíveis sem avaliar a política do provedor.
- O arquivo `audit.jsonl` não é rotacionado.
