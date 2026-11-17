"""Explicador: descreve a consulta e resume o resultado usando o LLM."""

from __future__ import annotations

from .llm import LlmClient

TIMEOUT_S = 15.0
LIMITE_TEXTO = 1000
AMOSTRA_LINHAS = 5

SYSTEM_PROMPT = (
    "Você explica consultas SQL a usuários não técnicos. Responda em português, "
    "em texto simples, com: (1) uma descrição curta do que a consulta faz e "
    "(2) um resumo do resultado informando o número de linhas retornadas. "
    "Use no máximo 1000 caracteres."
)


def _montar_prompt(pergunta: str, sql: str, resultado) -> str:
    linhas = list(resultado.linhas)
    total = len(linhas)
    sufixo = " (resultado truncado pelo limite de exibição)" if getattr(resultado, "truncado", False) else ""
    amostra = "\n".join(str(tuple(l)) for l in linhas[:AMOSTRA_LINHAS]) or "(nenhuma linha)"
    return (
        f"Pergunta: {pergunta}\n"
        f"SQL:\n{sql}\n"
        f"Colunas: {', '.join(map(str, resultado.colunas))}\n"
        f"Número de linhas: {total}{sufixo}\n"
        f"Primeiras linhas:\n{amostra}"
    )


def explicar(pergunta: str, sql: str, resultado, llm: LlmClient) -> str | None:
    """Devolve a explicação (até 1.000 caracteres) ou ``None`` em falha ou timeout."""
    try:
        texto = llm.completar(SYSTEM_PROMPT, _montar_prompt(pergunta, sql, resultado), TIMEOUT_S)
    except Exception:
        return None
    if not isinstance(texto, str):
        return None
    texto = texto.strip()
    if not texto:
        return None
    return texto[:LIMITE_TEXTO]
