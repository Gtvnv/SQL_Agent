"""Property 10: Múltiplas instruções são rejeitadas."""

from hypothesis import given, settings, strategies as st

from sql_agent.schema import Coluna, SchemaInfo, Tabela
from sql_agent.validator import validar

_ESQUEMA = SchemaInfo(
    tabelas=[
        Tabela("clientes", [Coluna("id", "INTEGER", pk=True), Coluna("nome", "TEXT"), Coluna("cidade", "TEXT")]),
        Tabela("produtos", [Coluna("id", "INTEGER", pk=True), Coluna("nome", "TEXT"), Coluna("preco", "REAL")]),
    ]
)

_COLUNAS = {"clientes": ["id", "nome", "cidade"], "produtos": ["id", "nome", "preco"]}


@st.composite
def _consulta_leitura(draw):
    tabela = draw(st.sampled_from(sorted(_COLUNAS)))
    cols = draw(st.lists(st.sampled_from(_COLUNAS[tabela]), min_size=1, max_size=3, unique=True))
    sql = f"SELECT {', '.join(cols)} FROM {tabela}"
    if draw(st.booleans()):
        sql += f" WHERE {cols[0]} IS NOT NULL"
    if draw(st.booleans()):
        sql += f" ORDER BY {cols[0]}"
    if draw(st.booleans()):
        sql += f" LIMIT {draw(st.integers(min_value=1, max_value=100))}"
    return sql


_consultas = st.lists(_consulta_leitura(), min_size=2, max_size=4)


# Feature: text-to-sql-agent, Property 10: Múltiplas instruções são rejeitadas
# **Validates: Requirements 4.3**
@settings(max_examples=100, deadline=None)
@given(consultas=_consultas, ponto_virgula_final=st.booleans())
def test_multiplas_instrucoes_sao_rejeitadas(consultas, ponto_virgula_final):
    sql = "; ".join(consultas) + (";" if ponto_virgula_final else "")
    resultado = validar(sql, _ESQUEMA)
    assert not resultado.aprovada
    assert "somente uma instrução" in (resultado.motivo or "")


# Feature: text-to-sql-agent, Property 10: Múltiplas instruções são rejeitadas
# **Validates: Requirements 4.3**
@settings(max_examples=100, deadline=None)
@given(consulta=_consulta_leitura(), espaco=st.sampled_from(["", " ", "\n", "  "]))
def test_consulta_unica_com_ponto_virgula_final_e_aprovada(consulta, espaco):
    assert validar(consulta, _ESQUEMA).aprovada
    resultado = validar(consulta + espaco + ";", _ESQUEMA)
    assert resultado.aprovada, resultado.motivo
