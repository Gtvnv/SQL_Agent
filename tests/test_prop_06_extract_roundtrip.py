"""Property 6: extract_sql inverte format_sql_block."""

from hypothesis import given, settings, strategies as st

from sql_agent.generator import extract_sql, format_sql_block

_ident = st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True)
_espaco = st.sampled_from([" ", "  ", "\t", "\n", "\r\n", " \n "])
_ws = st.lists(_espaco, max_size=3).map("".join)
_literal = st.one_of(
    st.integers(-1000, 1000).map(str),
    st.from_regex(r"[A-Za-z0-9 ]{0,10}", fullmatch=True).map(lambda s: f"'{s}'"),
)


@st.composite
def _consultas(draw):
    tabela = draw(_ident)
    colunas = draw(st.lists(_ident, min_size=1, max_size=4, unique=True))
    sql = f"SELECT {', '.join(colunas)} FROM {tabela}"
    if draw(st.booleans()):
        sql += f" WHERE {draw(_ident)} {draw(st.sampled_from(['=', '>', '<', '<>']))} {draw(_literal)}"
    if draw(st.booleans()):
        sql += f" ORDER BY {draw(_ident)}"
    if draw(st.booleans()):
        sql = f"WITH t AS ({sql}) SELECT * FROM t"
    return sql


# Feature: text-to-sql-agent, Property 6: Extração de SQL de bloco Markdown é inversa da formatação
# **Validates: Requirements 3.3, 9.6**
@settings(max_examples=100, deadline=None)
@given(
    sql=_consultas(),
    interno_antes=_ws,
    interno_depois=_ws,
    fora_antes=_ws,
    fora_depois=_ws,
    com_identificador=st.booleans(),
)
def test_extract_sql_inverte_format_sql_block(
    sql, interno_antes, interno_depois, fora_antes, fora_depois, com_identificador
):
    base = format_sql_block(sql)
    assert extract_sql(base) == sql

    abertura = "```sql\n" if com_identificador else "```\n"
    bloco = f"{abertura}{interno_antes}{sql}{interno_depois}\n```"
    assert extract_sql(f"{fora_antes}{bloco}{fora_depois}") == sql
