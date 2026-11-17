"""Property 7: Respostas sem SQL única são rejeitadas."""

import re

import pytest
from hypothesis import given, settings, strategies as st

from sql_agent.generator import GeracaoError, extract_sql, format_sql_block

_PALAVRA_SQL = re.compile(r"\b(?:select|with)\b", re.IGNORECASE)

# Texto livre (inclusive vazio/branco) sem SELECT/WITH e sem o marcador NAO_DISPONIVEL.
_sem_sql = st.text(max_size=200).filter(
    lambda t: not _PALAVRA_SQL.search(t) and "NAO_DISPONIVEL" not in t.upper() and "```" not in t
)

_inteiro = st.integers(min_value=0, max_value=10_000)


# Feature: text-to-sql-agent, Property 7: Respostas sem SQL única são rejeitadas
# **Validates: Requirements 3.4, 3.5**
@settings(max_examples=100, deadline=None)
@given(texto=_sem_sql)
def test_resposta_sem_sql_e_rejeitada(texto):
    with pytest.raises(GeracaoError):
        extract_sql(texto)


# Feature: text-to-sql-agent, Property 7: Respostas sem SQL única são rejeitadas
# **Validates: Requirements 3.4, 3.5**
@settings(max_examples=100, deadline=None)
@given(texto=_sem_sql)
def test_bloco_markdown_sem_sql_e_rejeitado(texto):
    with pytest.raises(GeracaoError):
        extract_sql(format_sql_block(texto))


# Feature: text-to-sql-agent, Property 7: Respostas sem SQL única são rejeitadas
# **Validates: Requirements 3.4, 3.5**
@settings(max_examples=100, deadline=None)
@given(
    a=_inteiro,
    b=_inteiro,
    em_bloco=st.booleans(),
    ponto_virgula_final=st.booleans(),
)
def test_multiplas_instrucoes_sao_rejeitadas(a, b, em_bloco, ponto_virgula_final):
    sql = f"SELECT {a}; SELECT {b}" + (";" if ponto_virgula_final else "")
    resposta = format_sql_block(sql) if em_bloco else sql
    with pytest.raises(GeracaoError):
        extract_sql(resposta)
