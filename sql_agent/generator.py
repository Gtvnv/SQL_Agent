"""Gerador_SQL: monta o prompt, chama o LLM e extrai a consulta SQLite."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

import sqlglot
from sqlglot.errors import SqlglotError

from sql_agent.llm import LlmClient
from sql_agent.schema import SchemaInfo

NAO_DISPONIVEL = "NAO_DISPONIVEL"
MAX_EXEMPLOS = 10
TIMEOUT_LLM_S = 30.0

_BLOCO = re.compile(r"```[ \t]*(?:sql(?=\s|$))?[ \t]*\r?\n?(.*?)```", re.DOTALL | re.IGNORECASE)
_SELECT_OU_WITH = re.compile(r"\b(?:select|with)\b", re.IGNORECASE)


class GeracaoError(Exception):
    """Resposta do LLM sem uma única consulta SQL utilizável."""


def format_sql_block(sql: str) -> str:
    """Formata `sql` como bloco de código Markdown."""
    return f"```sql\n{sql}\n```"


def extract_sql(resposta: str) -> str:
    """Extrai a única consulta SQL de `resposta` (função pura).

    Devolve `NAO_DISPONIVEL` se o LLM indicar que os dados não existem.
    Levanta `GeracaoError` para resposta vazia, sem SELECT/WITH reconhecível
    ou com mais de uma instrução (um `;` final isolado é ignorado).
    """
    texto = resposta or ""
    bloco = _BLOCO.search(texto)
    sql = (bloco.group(1) if bloco else texto).strip()

    if sql.rstrip(";").strip().upper() == NAO_DISPONIVEL:
        return NAO_DISPONIVEL
    if not sql or not _SELECT_OU_WITH.search(sql):
        raise GeracaoError("falha na geração")

    try:
        instrucoes = [i for i in sqlglot.parse(sql, read="sqlite") if i is not None]
    except SqlglotError:
        raise GeracaoError("falha na geração") from None
    if not instrucoes:
        raise GeracaoError("falha na geração")
    if len(instrucoes) > 1:
        raise GeracaoError("mais de uma instrução")
    return sql


def _formatar_exemplos(exemplos: Iterable[Mapping[str, Any]] | None) -> str:
    itens = list(exemplos or [])[:MAX_EXEMPLOS]
    return "\n\n".join(
        f"Pergunta: {e['pergunta']}\nSQL:\n{format_sql_block(str(e['sql']).strip())}"
        for e in itens
    )


def montar_prompt_sistema(
    esquema: SchemaInfo, exemplos: Sequence[Mapping[str, Any]] | None = None
) -> str:
    """Prompt de sistema com esquema, regras e até 10 exemplos few-shot."""
    partes = [
        "Você converte perguntas em português em consultas SQL para SQLite.",
        "Responda somente com a consulta SQL SQLite, sem explicações.",
        "Gere apenas consultas de somente leitura (SELECT ou WITH ... SELECT), "
        "uma única instrução. Nunca gere INSERT, UPDATE, DELETE, DROP, ALTER, "
        "CREATE, ATTACH, DETACH, VACUUM ou PRAGMA.",
        f"Se os dados necessários não existirem no esquema, responda exatamente {NAO_DISPONIVEL}.",
        "Esquema do banco:\n" + esquema.para_prompt(),
    ]
    fewshot = _formatar_exemplos(exemplos)
    if fewshot:
        partes.append("Exemplos:\n" + fewshot)
    return "\n\n".join(partes)


def gerar(
    pergunta: str,
    esquema: SchemaInfo,
    client: LlmClient,
    exemplos: Sequence[Mapping[str, Any]] | None = None,
    timeout_s: float = TIMEOUT_LLM_S,
) -> str:
    """Gera a SQL para `pergunta`. Exceções do LLM e `GeracaoError` propagam."""
    system = montar_prompt_sistema(esquema, exemplos)
    return extract_sql(client.completar(system, f"Pergunta: {pergunta}", timeout_s))


def corrigir(
    pergunta: str,
    sql: str,
    erro: str,
    esquema: SchemaInfo,
    client: LlmClient,
    exemplos: Sequence[Mapping[str, Any]] | None = None,
    timeout_s: float = TIMEOUT_LLM_S,
) -> str:
    """Pede ao LLM uma SQL corrigida a partir da pergunta, da SQL e do erro."""
    system = montar_prompt_sistema(esquema, exemplos)
    user = (
        f"Pergunta: {pergunta}\n\n"
        f"A consulta abaixo falhou na execução.\n"
        f"SQL:\n{format_sql_block(sql)}\n\n"
        f"Erro: {erro}\n\n"
        "Corrija a consulta e responda somente com a SQL SQLite corrigida."
    )
    return extract_sql(client.completar(system, user, timeout_s))
