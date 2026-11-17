# Engenharia de prompt

O agente usa o LLM em três chamadas: gerar a SQL, corrigir a SQL e explicar o resultado. Os prompts estão em `sql_agent/generator.py` e `sql_agent/explainer.py`.

## Prompt de sistema da geração

`montar_prompt_sistema` junta, nesta ordem, em português:

1. O papel: converter perguntas em português em consultas SQL para SQLite.
2. A instrução de responder somente com a consulta SQLite, sem explicações.
3. A regra de somente leitura: apenas `SELECT` ou `WITH ... SELECT`, uma única instrução, e nunca `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`, `DETACH`, `VACUUM` ou `PRAGMA`.
4. A saída de escape: se os dados não existirem no esquema, responder exatamente `NAO_DISPONIVEL`. Isso evita que o modelo invente tabelas ou colunas.
5. O esquema do banco (`SchemaInfo.para_prompt`), com tabelas, colunas, tipos, PKs, FKs e as descrições de `db/schema_descriptions.yaml` (até 500 caracteres cada).
6. Até 10 exemplos few-shot de `db/few_shot.yaml`, cada um como `Pergunta:` seguida da SQL em bloco ` ```sql `.

A mensagem do usuário é `Pergunta: <texto>`. O timeout da chamada é de 30 s.

## Esquema como contexto

O esquema vem do próprio banco (`sqlite_master`, `PRAGMA table_info`, `PRAGMA foreign_key_list`), sem manutenção manual. As descrições em YAML explicam o significado das colunas (por exemplo, que `itens_pedido.preco_unitario` é o preço no momento da venda e que o valor do item é `quantidade * preco_unitario`). Descrições de tabelas ou colunas inexistentes são ignoradas com aviso.

## Few-shot

Os 10 pares de `db/few_shot.yaml` cobrem contagem, filtro, média, junção, agrupamento com `LEFT JOIN`, ordenação com `LIMIT`, soma por pedido e filtro por intervalo de datas. Mostram o dialeto SQLite e as convenções do banco (datas em texto `AAAA-MM-DD`). Exemplos além do décimo são ignorados.

## Extração da resposta

`extract_sql` procura um bloco de código com três crases (com ou sem `sql`) e usa o conteúdo. Sem bloco, usa o texto inteiro. Depois:

- `NAO_DISPONIVEL` (com ou sem `;` final) vira o sinal de dados indisponíveis.
- Texto vazio ou sem `SELECT`/`WITH` levanta `GeracaoError("falha na geração")`.
- Mais de uma instrução (contadas com `sqlglot.parse`, ignorando `;` final isolado) levanta `GeracaoError("mais de uma instrução")`.

## Prompt de correção

`corrigir` usa o mesmo prompt de sistema. A mensagem do usuário contém a pergunta, a SQL que falhou em bloco ` ```sql `, a mensagem de erro do SQLite (com a chave de API mascarada, se aparecer) e o pedido para responder somente com a SQL corrigida. O mesmo `extract_sql` processa a resposta.

## Prompt do Explicador

O prompt de sistema pede a um modelo que explique a consulta a usuários não técnicos, em português e texto simples, com uma descrição curta do que a consulta faz e um resumo do resultado com o número de linhas, em até 1.000 caracteres. A mensagem do usuário inclui pergunta, SQL, nomes das colunas, número de linhas (com nota de truncamento) e as 5 primeiras linhas. Timeout de 15 s. A resposta é cortada em 1.000 caracteres.

## Prompt injection

O prompt instrui o modelo a não gerar escrita, mas essa instrução não é uma garantia. A proteção real está fora do LLM: o validador e a conexão somente leitura tratam a resposta do modelo como entrada não confiável. Veja [decisões de segurança](decisoes-de-seguranca.md).
