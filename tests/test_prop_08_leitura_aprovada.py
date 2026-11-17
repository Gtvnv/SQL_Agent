"""Property 8: Consultas de leitura válidas são aprovadas."""

from hypothesis import given, settings, strategies as st

from sql_agent.schema import Coluna, SchemaInfo, Tabela
from sql_agent.validator import validar

_ESQUEMA = SchemaInfo(
    tabelas=[
        Tabela("clientes", [
            Coluna("id", "INTEGER", pk=True),
            Coluna("nome", "TEXT"),
            Coluna("cidade", "TEXT"),
        ]),
        Tabela("pedidos", [
            Coluna("id", "INTEGER", pk=True),
            Coluna("cliente_id", "INTEGER", fk=("clientes", "id")),
            Coluna("total", "REAL"),
            Coluna("data", "TEXT"),
        ]),
    ]
)
_COLUNAS = {t.nome: [c.nome for c in t.colunas] for t in _ESQUEMA.tabelas}

_PALAVRAS_PERIGOSAS = [
    "DELETE", "DROP", "INSERT", "UPDATE", "DROP TABLE x", "DELETE FROM clientes",
    "; DROP TABLE clientes; --", "ALTER", "PRAGMA", "ATTACH",
]


@st.composite
def _caixa(draw, palavra: str) -> str:
    """Palavra com maiúsculas/minúsculas misturadas."""
    flags = draw(st.lists(st.booleans(), min_size=len(palavra), max_size=len(palavra)))
    return "".join(c.upper() if f else c.lower() for c, f in zip(palavra, flags))


_espaco = st.text(alphabet=" \t\r\n", min_size=1, max_size=4)
_texto_comentario = st.one_of(
    st.text(alphabet="abc xyz123", max_size=15),
    st.sampled_from(_PALAVRAS_PERIGOSAS),
)


@st.composite
def _sep(draw) -> str:
    """Separador entre tokens: espaço em branco, opcionalmente com comentários."""
    partes = [draw(_espaco)]
    for _ in range(draw(st.integers(0, 2))):
        txt = draw(_texto_comentario)
        if draw(st.booleans()):
            partes.append(f"/*{txt}*/")
        else:
            partes.append(f"--{txt}\n")
        partes.append(draw(_espaco))
    return "".join(partes)


@st.composite
def _literal(draw) -> str:
    """Literal de texto, possivelmente contendo DELETE/DROP e aspas escapadas."""
    corpo = draw(st.one_of(
        st.sampled_from(_PALAVRAS_PERIGOSAS),
        st.text(alphabet="abcXYZ 019;-_%", max_size=12),
    ))
    extra = draw(st.sampled_from(["", "", "O''Brien ", "x -- y ", "/* z */ "]))
    return "'" + extra + corpo.replace("'", "''") + "'"


@st.composite
def _consulta(draw) -> str:
    tabela = draw(st.sampled_from(sorted(_COLUNAS)))
    cols = _COLUNAS[tabela]
    sel = draw(st.lists(st.sampled_from(cols), min_size=1, max_size=len(cols), unique=True))
    kw = lambda p: draw(_caixa(p))  # noqa: E731
    s = lambda: draw(_sep())  # noqa: E731

    usar_cte = draw(st.booleans())
    usar_alias = draw(st.booleans())
    alias = "t" if usar_alias else None
    ref = (alias + ".") if alias else ""

    lista = ("," + s()).join(
        ref + draw(_caixa(c)) if draw(st.booleans()) else ref + c for c in sel
    )
    origem = tabela if not usar_cte else "base"
    fonte = origem + ((s() + (kw("AS") + s() if draw(st.booleans()) else "") + alias) if alias else "")

    sql = ""
    if usar_cte:
        sql += (
            kw("WITH") + s() + "base" + s() + kw("AS") + s() + "(" + s()
            + kw("SELECT") + s() + "*" + s() + kw("FROM") + s() + tabela + s() + ")" + s()
        )
    sql += kw("SELECT") + s()
    if draw(st.booleans()):
        sql += kw("DISTINCT") + s()
    sql += lista + s() + kw("FROM") + s() + fonte

    texto_cols = [c for c in cols if c in ("nome", "cidade", "data")]
    if texto_cols and draw(st.booleans()):
        col = ref + draw(st.sampled_from(texto_cols))
        op = draw(st.sampled_from(["=", "<>", "LIKE"]))
        sql += s() + kw("WHERE") + s() + col + s() + op + s() + draw(_literal())
    if draw(st.booleans()):
        sql += s() + kw("ORDER") + s() + kw("BY") + s() + ref + sel[0]
    if draw(st.booleans()):
        sql += s() + kw("LIMIT") + s() + str(draw(st.integers(0, 1000)))
    if draw(st.booleans()):
        sql += s() + ";"
    return sql


# Feature: text-to-sql-agent, Property 8: Consultas de leitura válidas são aprovadas
# **Validates: Requirements 3.1, 4.1**
@settings(max_examples=100, deadline=None)
@given(sql=_consulta())
def test_consulta_de_leitura_valida_e_aprovada(sql):
    resultado = validar(sql, _ESQUEMA)
    assert resultado.aprovada, f"{sql!r} -> {resultado.motivo}"


# Feature: text-to-sql-agent, Property 8: Consultas de leitura válidas são aprovadas
# **Validates: Requirements 3.1, 4.1**
@settings(max_examples=100, deadline=None)
@given(literal=_literal(), c1=_caixa("select"), c2=_caixa("from"), c3=_caixa("where"))
def test_palavras_de_escrita_em_literais_nao_reprovam(literal, c1, c2, c3):
    sql = f"{c1} id {c2} clientes {c3} nome = {literal}"
    resultado = validar(sql, _ESQUEMA)
    assert resultado.aprovada, f"{sql!r} -> {resultado.motivo}"
