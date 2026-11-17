"""Property 9: Instruções de escrita ou definição são rejeitadas."""

from hypothesis import given, settings, strategies as st

from sql_agent.schema import Coluna, SchemaInfo, Tabela
from sql_agent.validator import validar

ESQUEMA = SchemaInfo(
    tabelas=[
        Tabela("produtos", [Coluna("id", "INTEGER", pk=True), Coluna("nome", "TEXT")]),
    ]
)

# Palavra-chave -> modelos de instrução (a palavra-chave entra em `{kw}`).
MODELOS = {
    "INSERT": ["{kw} INTO produtos (id, nome) VALUES (1, 'x')"],
    "UPDATE": ["{kw} produtos SET nome = 'x' WHERE id = 1"],
    "DELETE": ["{kw} FROM produtos WHERE id = 1"],
    "REPLACE": ["{kw} INTO produtos (id, nome) VALUES (1, 'x')"],
    "DROP": ["{kw} TABLE produtos"],
    "ALTER": ["{kw} TABLE produtos ADD COLUMN extra TEXT"],
    "CREATE": ["{kw} TABLE nova (id INTEGER)"],
    "ATTACH": ["{kw} DATABASE 'outro.db' AS outro"],
    "DETACH": ["{kw} DATABASE outro"],
    "VACUUM": ["{kw}"],
    "PRAGMA": ["{kw} user_version = 5", "{kw} writable_schema = 1"],
}


@st.composite
def _instrucao_escrita(draw):
    palavra = draw(st.sampled_from(sorted(MODELOS)))
    modelo = draw(st.sampled_from(MODELOS[palavra]))
    # Caixa mista: cada letra da palavra-chave em maiúscula ou minúscula.
    escrita = "".join(
        c.upper() if draw(st.booleans()) else c.lower() for c in palavra
    )
    sql = modelo.format(kw=escrita)
    if draw(st.booleans()):
        sql += ";"
    return palavra, sql


# Feature: text-to-sql-agent, Property 9: Instruções de escrita ou definição são rejeitadas
# **Validates: Requirements 4.2, 4.6**
@settings(max_examples=100, deadline=None)
@given(caso=_instrucao_escrita())
def test_instrucao_de_escrita_ou_definicao_e_rejeitada(caso):
    palavra, sql = caso
    resultado = validar(sql, ESQUEMA)
    assert not resultado.aprovada, sql
    assert resultado.palavra_chave == palavra, sql
    assert resultado.motivo
