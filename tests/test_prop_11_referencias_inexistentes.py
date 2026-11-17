"""Property 11: Referências inexistentes ao esquema são rejeitadas."""

from hypothesis import given, settings, strategies as st

from sql_agent.schema import Coluna, SchemaInfo, Tabela
from sql_agent.validator import validar

# Feature: text-to-sql-agent, Property 11: Referências inexistentes ao esquema são rejeitadas
# **Validates: Requirements 4.5**

_SUFIXO = st.text(alphabet="abcdefghij", min_size=1, max_size=6)


@st.composite
def _cenario(draw):
    """Esquema (`t_*`/`c_*`), uma consulta com referência inexistente (`x_*`/`y_*`) e o nome ausente."""
    nomes = draw(st.lists(_SUFIXO, min_size=1, max_size=4, unique=True))
    tabelas = []
    for nome in nomes:
        cols = draw(st.lists(_SUFIXO, min_size=1, max_size=4, unique=True))
        tabelas.append(
            Tabela(f"t_{nome}", [Coluna(f"c_{c}", "TEXT") for c in cols])
        )
    esquema = SchemaInfo(tabelas=tabelas)

    tab = draw(st.sampled_from(tabelas))
    col = draw(st.sampled_from(tab.colunas)).nome
    ausente = draw(_SUFIXO)
    forma = draw(st.sampled_from(["tabela", "coluna", "coluna_qualificada", "coluna_alias", "where"]))

    if forma == "tabela":
        nome_ausente = f"x_{ausente}"
        sql = f"SELECT * FROM {nome_ausente}"
    elif forma == "coluna":
        nome_ausente = f"y_{ausente}"
        sql = f"SELECT {nome_ausente} FROM {tab.nome}"
    elif forma == "coluna_qualificada":
        nome_ausente = f"y_{ausente}"
        sql = f"SELECT {tab.nome}.{nome_ausente} FROM {tab.nome}"
    elif forma == "coluna_alias":
        nome_ausente = f"y_{ausente}"
        sql = f"SELECT a.{nome_ausente} FROM {tab.nome} AS a"
    else:
        nome_ausente = f"y_{ausente}"
        sql = f"SELECT {col} FROM {tab.nome} WHERE {nome_ausente} = 1"
    return esquema, sql, nome_ausente


@settings(max_examples=100, deadline=None)
@given(dados=_cenario())
def test_referencias_inexistentes_sao_rejeitadas(dados):
    esquema, sql, nome_ausente = dados

    resultado = validar(sql, esquema)

    assert resultado.aprovada is False
    assert resultado.motivo is not None
    assert nome_ausente in resultado.motivo
