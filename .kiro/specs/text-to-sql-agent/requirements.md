# Requirements Document

## Introduction

O Agente Text-to-SQL é um agente de IA que converte perguntas em linguagem natural (português) em consultas SQL, executa essas consultas em um banco de dados de exemplo e devolve o resultado ao usuário com uma explicação. O projeto atende ao Desafio DIO e, por isso, também exige um repositório público no GitHub com README.md detalhado, documentação técnica complementar e capturas de tela opcionais na pasta `/images`.

Premissas adotadas (ajustáveis na revisão): banco SQLite com dados de exemplo (sem necessidade de servidor), Python como linguagem, um LLM acessado por API como motor de geração de SQL, e interface de linha de comando (CLI). O agente opera somente em modo leitura.

## Glossary

- **Agente**: Sistema de IA que recebe uma pergunta em linguagem natural e produz, valida, executa e explica uma consulta SQL.
- **Pergunta**: Texto em linguagem natural informado pelo usuário.
- **Gerador_SQL**: Componente que usa o LLM para transformar a Pergunta em uma consulta SQL.
- **LLM**: Modelo de linguagem acessado por API, usado pelo Gerador_SQL.
- **Extrator_Esquema**: Componente que lê do banco de dados as tabelas, colunas, tipos e chaves e as monta como contexto para o LLM.
- **Validador_SQL**: Componente que verifica se uma consulta SQL é sintaticamente válida e segura antes da execução.
- **Executor_SQL**: Componente que executa a consulta validada no banco de dados e retorna as linhas.
- **Explicador**: Componente que descreve em português o resultado e a consulta gerada.
- **Banco_Exemplo**: Banco de dados SQLite com esquema e dados de demonstração, criado por script versionado no repositório.
- **Interface_CLI**: Interface de linha de comando pela qual o usuário interage com o Agente.
- **Consulta_Somente_Leitura**: Consulta SQL formada por uma única instrução SELECT (ou WITH seguido de SELECT).
- **Repositório**: Repositório público no GitHub com o código e a documentação do projeto.
- **Conjunto_Avaliação**: Conjunto versionado de pares (Pergunta, SQL esperado) usado para medir a qualidade do Agente.
- **Log_Auditoria**: Registro persistente de cada Pergunta, SQL gerada, status de validação e resultado.

## Requirements

### Requirement 1: Perguntas em linguagem natural

**User Story:** Como usuário, quero fazer perguntas em português sobre os dados, para obter respostas sem precisar escrever SQL.

#### Acceptance Criteria

1. WHEN o usuário envia uma Pergunta não vazia pela Interface_CLI, THE Agente SHALL retornar, em até 30 segundos, a consulta SQL gerada, as linhas resultantes (limitadas a no máximo 100 linhas exibidas) e uma explicação em português com no máximo 1.000 caracteres.
2. WHEN o usuário envia uma Pergunta vazia ou composta apenas de espaços, THE Interface_CLI SHALL exibir uma mensagem solicitando uma Pergunta válida, sem acionar o LLM, e SHALL manter a sessão ativa aguardando nova entrada.
3. WHEN o usuário envia o comando de saída, THE Interface_CLI SHALL encerrar a sessão em até 2 segundos e finalizar o processo com código de saída 0.
4. WHILE a sessão estiver ativa, THE Interface_CLI SHALL aceitar uma nova Pergunta após a conclusão de cada resposta, sem limite de quantidade de Perguntas por sessão.
5. IF a Pergunta exceder 1.000 caracteres, THEN THE Interface_CLI SHALL rejeitar a Pergunta com uma mensagem indicando o limite de 1.000 caracteres, sem acionar o LLM, e SHALL manter a sessão ativa.
6. IF o LLM não responder em 30 segundos, retornar erro, ou gerar uma consulta SQL que falhe na execução, THEN THE Agente SHALL exibir uma mensagem de erro indicando a falha e a etapa em que ocorreu, sem exibir linhas parciais, e THE Interface_CLI SHALL manter a sessão ativa para a próxima Pergunta.

### Requirement 2: Contexto do esquema do banco

**User Story:** Como usuário, quero que o Agente conheça a estrutura do banco, para que as consultas usem tabelas e colunas reais.

#### Acceptance Criteria

1. WHEN o Agente é iniciado, THE Extrator_Esquema SHALL ler do Banco_Exemplo, em até 10 segundos, os nomes de todas as tabelas de usuário, e para cada tabela os nomes das colunas, os tipos de dados, as chaves primárias e as chaves estrangeiras (incluindo a tabela e a coluna referenciadas).
2. WHEN o Gerador_SQL recebe uma Pergunta, THE Gerador_SQL SHALL incluir no contexto enviado ao LLM o esquema extraído na inicialização, contendo 100% das tabelas e colunas lidas pelo Extrator_Esquema.
3. WHERE o arquivo de configuração define descrições de colunas, THE Extrator_Esquema SHALL associar cada descrição à tabela e coluna correspondentes e incluí-las no contexto enviado ao LLM, com no máximo 500 caracteres por descrição.
4. IF o arquivo de configuração de descrições referencia uma tabela ou coluna inexistente no Banco_Exemplo, THEN THE Extrator_Esquema SHALL ignorar essa descrição, exibir um aviso identificando a tabela ou coluna não encontrada e continuar a inicialização.
5. IF o Extrator_Esquema não consegue acessar o Banco_Exemplo ou não conclui a leitura em 10 segundos, THEN THE Agente SHALL exibir uma mensagem de erro indicando o motivo da falha, não aceitar Perguntas e encerrar com código de saída diferente de zero.

### Requirement 3: Geração de SQL

**User Story:** Como usuário, quero que a pergunta seja convertida em SQL correta, para confiar nos resultados.

#### Acceptance Criteria

1. WHEN o Gerador_SQL recebe uma Pergunta com 1 a 1.000 caracteres, THE Gerador_SQL SHALL produzir exatamente uma instrução SQL no dialeto SQLite, que começa com SELECT ou WITH e contém um único ponto e vírgula final opcional.
2. THE Gerador_SQL SHALL incluir no contexto enviado ao LLM uma instrução para responder somente com a consulta SQL, sem texto explicativo antes ou depois.
3. WHEN a resposta do LLM contém a consulta dentro de um bloco de código Markdown (delimitado por três crases, com ou sem o identificador "sql"), THE Gerador_SQL SHALL extrair apenas o conteúdo SQL do bloco, sem os delimitadores e sem espaços em branco no início e no fim.
4. IF a resposta do LLM contém mais de uma instrução SQL, THEN THE Gerador_SQL SHALL rejeitar a resposta, não executar nenhuma consulta e retornar ao Agente um erro indicando que a geração produziu mais de uma instrução.
5. IF a resposta do LLM está vazia ou não contém uma instrução SQL reconhecível, THEN THE Gerador_SQL SHALL retornar ao Agente um erro indicando falha na geração, e THE Agente SHALL informar o usuário da falha sem executar consulta no banco.
6. IF a Pergunta não pode ser respondida com as tabelas existentes no esquema do banco, THEN THE Agente SHALL informar ao usuário, sem executar consulta no banco, que os dados necessários não estão disponíveis no banco.
7. WHERE exemplos de perguntas e SQL (few-shot) estão configurados, THE Gerador_SQL SHALL incluir todos os exemplos configurados, limitados a 10 pares, no contexto enviado ao LLM.

### Requirement 4: Segurança somente leitura

**User Story:** Como responsável pelo banco, quero que o Agente nunca altere os dados, para proteger a integridade do banco.

#### Acceptance Criteria

1. WHEN o Gerador_SQL produz uma consulta, THE Validador_SQL SHALL verificar, antes da execução e em no máximo 500 ms, se a consulta é uma Consulta_Somente_Leitura, aceitando somente consultas cuja única instrução começa com SELECT ou WITH (após remoção de espaços e comentários) e não contém instruções de escrita ou de definição.
2. IF a consulta contém qualquer instrução de escrita ou de definição (INSERT, UPDATE, DELETE, REPLACE, DROP, ALTER, CREATE, ATTACH, DETACH, VACUUM, ou PRAGMA que altere configuração ou dados), em qualquer combinação de maiúsculas e minúsculas, THEN THE Validador_SQL SHALL rejeitar a consulta, THE Executor_SQL SHALL não executar a consulta, e THE Agente SHALL informar ao usuário uma mensagem indicando que a consulta foi rejeitada por conter operação de escrita ou de definição e qual palavra-chave foi detectada.
3. IF a consulta contém mais de uma instrução separada por ponto e vírgula (um ponto e vírgula final isolado não conta como separador), THEN THE Validador_SQL SHALL rejeitar a consulta, THE Executor_SQL SHALL não executar nenhuma das instruções, e THE Agente SHALL informar ao usuário uma mensagem indicando que somente uma instrução por consulta é permitida.
4. THE Executor_SQL SHALL abrir a conexão com o Banco_Exemplo em modo somente leitura, de modo que qualquer tentativa de escrita pela conexão falhe sem alterar o conteúdo do Banco_Exemplo.
5. IF a consulta referencia tabelas ou colunas inexistentes no esquema do Banco_Exemplo, THEN THE Validador_SQL SHALL rejeitar a consulta antes da execução, e THE Agente SHALL informar ao usuário uma mensagem indicando o nome da tabela ou coluna não encontrada.
6. WHEN uma Pergunta contém instruções que tentam alterar o comportamento do Agente (prompt injection), THE Agente SHALL aplicar o Validador_SQL à consulta gerada e SHALL executar a consulta somente se ela for uma Consulta_Somente_Leitura válida.
7. IF o Validador_SQL rejeita uma consulta, THEN THE Agente SHALL manter o Banco_Exemplo inalterado e SHALL permitir que o usuário envie uma nova Pergunta na mesma sessão.
8. IF a conexão somente leitura com o Banco_Exemplo não puder ser aberta, THEN THE Executor_SQL SHALL não executar a consulta, e THE Agente SHALL informar ao usuário uma mensagem indicando falha de acesso ao banco, sem recorrer a conexão com permissão de escrita.

### Requirement 5: Autocorreção de consultas

**User Story:** Como usuário, quero que o Agente corrija consultas com erro, para receber uma resposta mesmo quando a primeira tentativa falha.

#### Acceptance Criteria

1. IF o Executor_SQL retorna erro de execução, THEN THE Agente SHALL enviar ao LLM a Pergunta, a consulta com falha e a mensagem de erro do Executor_SQL, e SHALL executar a consulta corrigida retornada pelo LLM no Executor_SQL.
2. THE Agente SHALL limitar as tentativas de correção a 3 por Pergunta, com valor configurável entre 1 e 10, e SHALL contar como tentativa cada envio de consulta com falha ao LLM, sem contar a execução inicial.
3. IF o valor configurado para o limite de tentativas de correção estiver fora do intervalo de 1 a 10 ou não for um inteiro, THEN THE Agente SHALL usar o valor padrão 3 e informar o usuário de que o valor configurado foi ignorado.
4. WHEN uma consulta corrigida é executada com sucesso pelo Executor_SQL, THE Agente SHALL interromper as tentativas de correção e exibir ao usuário o resultado da consulta corrigida.
5. IF as tentativas de correção se esgotam sem sucesso, THEN THE Agente SHALL informar ao usuário que não foi possível responder, exibir a mensagem do último erro retornado pelo Executor_SQL e manter a sessão ativa para uma nova Pergunta.
6. IF a chamada à API do LLM falha por erro de rede ou limite de requisições durante uma tentativa de correção, THEN THE Agente SHALL exibir uma mensagem de erro indicando a causa (rede ou limite de requisições), interromper as tentativas da Pergunta atual e manter a sessão ativa para uma nova Pergunta.

### Requirement 6: Apresentação dos resultados

**User Story:** Como usuário, quero ver os resultados de forma clara e entender como foram obtidos, para verificar a resposta.

#### Acceptance Criteria

1. WHEN o Executor_SQL retorna uma ou mais linhas, THE Interface_CLI SHALL exibi-las em formato de tabela contendo uma linha de cabeçalho com os nomes das colunas na ordem retornada pela consulta e uma linha de tabela para cada registro retornado.
2. WHEN o Executor_SQL retorna zero linhas, THE Agente SHALL exibir uma mensagem em português indicando que nenhum registro foi encontrado e SHALL NOT exibir tabela de resultados.
3. WHEN o Executor_SQL retorna mais linhas do que o limite de exibição, THE Executor_SQL SHALL limitar o resultado exibido ao limite de exibição, cujo valor padrão é 100 linhas e cujo valor configurável aceito é de 1 a 10.000 linhas.
4. WHEN o resultado exibido é truncado pelo limite de exibição, THE Interface_CLI SHALL exibir uma mensagem informando que o resultado foi truncado e o valor do limite aplicado.
5. IF uma consulta excede o tempo limite de execução, cujo valor padrão é 10 segundos e cujo valor configurável aceito é de 1 a 300 segundos, THEN THE Executor_SQL SHALL interromper a consulta, e THE Agente SHALL exibir uma mensagem em português indicando que o tempo limite foi excedido e informando o valor do limite aplicado, sem exibir resultados parciais.
6. WHEN o Executor_SQL retorna resultado, THE Explicador SHALL gerar, em até 15 segundos, uma explicação em português contendo uma descrição do que a consulta SQL executada faz e um resumo do resultado que inclui o número de linhas retornadas.
7. IF o Explicador falha ou excede 15 segundos ao gerar a explicação, THEN THE Interface_CLI SHALL exibir a tabela de resultados normalmente e uma mensagem em português indicando que a explicação não está disponível.

### Requirement 7: Banco de dados de exemplo

**User Story:** Como desenvolvedor, quero um banco de exemplo reproduzível, para demonstrar e testar o Agente em qualquer máquina.

#### Acceptance Criteria

1. THE Repositório SHALL conter um script que cria o Banco_Exemplo com no mínimo 4 e no máximo 10 tabelas, em que cada tabela está relacionada a pelo menos outra tabela por chave estrangeira declarada.
2. THE Repositório SHALL conter dados de exemplo no Banco_Exemplo com no mínimo 10 linhas em cada tabela e no mínimo 100 linhas no total, incluindo pelo menos um valor numérico, um valor de data e um valor de texto por tabela, de modo que cada tipo de pergunta a seguir retorne pelo menos 1 linha: filtro por valor, agregação (contagem, soma ou média) com agrupamento, junção entre 2 ou mais tabelas e ordenação.
3. WHEN o script de criação é executado com sucesso duas vezes seguidas sobre o mesmo arquivo de banco, THE script SHALL terminar a segunda execução sem erro e produzir o mesmo estado final do Banco_Exemplo, com o mesmo conjunto de tabelas, as mesmas chaves estrangeiras e a mesma contagem de linhas por tabela da primeira execução.
4. IF o script de criação falha durante a execução, THEN THE script SHALL encerrar com código de saída diferente de zero, exibir uma mensagem indicando o passo que falhou e não deixar o Banco_Exemplo com dados parcialmente carregados.
5. THE Repositório SHALL documentar o diagrama entidade-relacionamento do Banco_Exemplo em formato de texto versionável, listando todas as tabelas, suas chaves primárias, suas chaves estrangeiras e a cardinalidade de cada relacionamento.

### Requirement 8: Configuração e credenciais

**User Story:** Como desenvolvedor, quero configurar o Agente por variáveis de ambiente, para trocar de modelo e proteger credenciais.

#### Acceptance Criteria

1. WHEN o Agente inicia, THE Agente SHALL ler a chave de API do LLM, o nome do modelo e os demais parâmetros configuráveis a partir de variáveis de ambiente ou do arquivo `.env`.
2. WHERE uma variável está definida simultaneamente no ambiente do processo e no arquivo `.env`, THE Agente SHALL usar o valor da variável de ambiente do processo.
3. THE Repositório SHALL conter um arquivo `.env.example` que lista todas as variáveis de configuração lidas pelo Agente, sem nenhum valor secreto, e um `.gitignore` que exclui o arquivo `.env`.
4. IF a chave de API do LLM não está definida ou é uma string vazia ou composta apenas de espaços, THEN THE Agente SHALL exibir uma mensagem de erro que contém o nome da variável ausente, encerrar com código de saída diferente de zero em até 2 segundos após o início e não executar nenhuma chamada ao LLM nem ao banco de dados.
5. IF o nome do modelo não está definido, THEN THE Agente SHALL exibir uma mensagem de erro que contém o nome da variável ausente e encerrar com código de saída diferente de zero.
6. THE Agente SHALL omitir o valor da chave de API de toda saída exibida ao usuário, de mensagens de erro e do Log_Auditoria.

### Requirement 9: Avaliação de qualidade e testes

**User Story:** Como desenvolvedor, quero medir a qualidade do Agente, para comprovar que as conversões funcionam.

#### Acceptance Criteria

1. THE Repositório SHALL conter um Conjunto_Avaliação com pelo menos 15 pares (Pergunta, SQL esperado), com pelo menos 2 pares para cada uma das categorias: filtros, agregações, junções, ordenação e agrupamento.
2. WHEN o script de avaliação é executado, THE script SHALL, para cada par, executar a SQL gerada e a SQL esperada no mesmo banco de dados e considerar o par como acerto somente se ambos os conjuntos de linhas retornados tiverem as mesmas linhas e valores, desconsiderando a ordem das linhas, exceto quando a SQL esperada contiver ORDER BY, caso em que a ordem das linhas também deve coincidir.
3. WHEN o script de avaliação termina, THE script SHALL exibir a taxa de acerto como percentual com 1 casa decimal (acertos divididos pelo total de pares), a contagem de acertos e o total, e listar cada par com falha com a pergunta, a SQL gerada e o motivo da falha.
4. IF a geração ou a execução da SQL de um par falhar (erro do LLM, SQL rejeitada pelo Validador_SQL, erro de execução ou tempo de execução superior a 30 segundos), THEN THE script SHALL registrar esse par como falha com o motivo, contá-lo no total de pares e continuar a avaliação dos pares restantes.
5. THE Repositório SHALL conter testes automatizados do Validador_SQL, do Extrator_Esquema e da extração de SQL da resposta do LLM, executáveis sem chamar a API do LLM e sem acesso à rede, com pelo menos 1 caso de sucesso e 1 caso de falha para cada um dos três componentes, e com pelo menos 1 teste do Validador_SQL que rejeite uma instrução de escrita (INSERT, UPDATE, DELETE, DROP).
6. FOR ALL consultas SQL válidas de leitura, formatar a consulta em um bloco de código Markdown e extraí-la novamente SHALL produzir a consulta original (propriedade de ida e volta), verificada com pelo menos 100 consultas geradas ou fixas por execução da suíte de testes.

### Requirement 10: Auditoria das interações

**User Story:** Como responsável pela auditoria, quero registrar as interações, para rastrear o que o Agente executou.

#### Acceptance Criteria

1. WHEN o Agente conclui o processamento de uma Pergunta, THE Agente SHALL gravar no Log_Auditoria exatamente um registro contendo: data e hora em UTC com precisão de segundos, texto da Pergunta (até 4.000 caracteres), SQL gerada (até 10.000 caracteres), resultado da validação (aprovada ou reprovada, com o motivo da reprovação quando reprovada), número de tentativas (inteiro de 1 a 3) e status final (sucesso ou falha).
2. IF a Pergunta ou a SQL gerada excede o limite de caracteres do registro, THEN THE Agente SHALL gravar o texto truncado no limite e marcar o campo como truncado no registro.
3. IF o Agente não gera SQL para a Pergunta, THEN THE Agente SHALL gravar o registro no Log_Auditoria com o campo da SQL gerada vazio e o status final igual a falha.
4. WHEN o Agente grava um registro no Log_Auditoria, THE Agente SHALL concluir a gravação em até 2 segundos.
5. IF a gravação no Log_Auditoria falha ou excede 2 segundos, THEN THE Agente SHALL exibir ao usuário um aviso indicando que a interação não foi auditada, entregar a resposta da Pergunta sem alteração de conteúdo e não repetir a gravação.

### Requirement 11: Documentação e entrega no GitHub

**User Story:** Como participante do Desafio DIO, quero um repositório público bem documentado, para compartilhar o conhecimento técnico e cumprir a entrega.

#### Acceptance Criteria

1. THE Repositório SHALL conter um arquivo README.md na raiz, escrito em português, com uma seção dedicada para cada um dos 9 itens a seguir: descrição do problema, objetivos, arquitetura, tecnologias, pré-requisitos, instruções de instalação, instruções de execução, exemplos de uso e limitações conhecidas, sendo que nenhuma seção pode estar vazia.
2. THE Repositório SHALL conter na pasta `/docs` pelo menos 1 arquivo de documentação técnica para cada um dos 5 temas a seguir: arquitetura (incluindo pelo menos 1 diagrama), fluxo do Agente, engenharia de prompt utilizada, esquema do Banco_Exemplo e decisões de segurança.
3. THE Repositório SHALL conter uma pasta `/images` com pelo menos 3 capturas de tela da execução do Agente, nos formatos PNG ou JPG, sendo que cada captura SHALL ser referenciada pelo menos 1 vez no README.md com caminho relativo válido.
4. THE README.md SHALL apresentar pelo menos 5 exemplos de Perguntas, sendo que cada exemplo SHALL conter a Pergunta em linguagem natural, a SQL gerada e o resultado correspondente retornado pelo Banco_Exemplo.
5. THE README.md SHALL apresentar os resultados do Conjunto_Avaliação, incluindo o número total de Perguntas avaliadas, o número de respostas corretas e a taxa de acerto expressa em percentual com 1 casa decimal.
6. WHEN o Repositório for acessado no GitHub por um usuário não autenticado, THE Repositório SHALL estar visível com visibilidade pública e permitir a leitura do README.md, da pasta `/docs` e da pasta `/images`.
7. THE Repositório SHALL conter na raiz um arquivo de licença de código aberto (LICENSE ou LICENSE.md) com o texto completo da licença, o ano e o nome do titular dos direitos autorais.
8. IF um arquivo ou link de imagem referenciado no README.md ou em `/docs` não existir no Repositório, THEN THE Repositório SHALL ser considerado incompleto para a entrega, e a referência inválida SHALL ser corrigida antes da publicação.