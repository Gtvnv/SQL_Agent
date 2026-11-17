"""Property 5: Descrições de itens inexistentes são ignoradas com aviso."""

import sqlite3

from hypothesis import given, settings, strategies as st

from sql_agent.schema import extrair_esquema

# Feature: text-to-sql-agent, Property 5: Descrições de itens inexistentes são ignoradas com aviso
# **Validates: Requirements 2.4**

_SUFIXO = st.text(alphabet="abcdefghij", min_size=1, max_size=6)
_TEXTO = st.text(alphabet="abc def", min_size=1, max_size=30)


@st.composite
def _cenario(draw):
    """Esquema real (nomes `t_*`/`c_*`) e descrições com itens inexistentes (`x_*`/`y_*`)."""
    nomes_tab = draw(st.lists(_SUFIXO, min_size=1, max_size=4, unique=True))
    esquema = {}
    for nome in nomes_tab:
        cols = draw(st.lists(_SUFIXO, min_size=1, max_size=4, unique=True))
        esquema[f"t_{nome}"] = [f"c_{c}" for c in cols]

    # Descrições válidas (opcionais) que devem continuar sendo aplicadas.
    validas = {}
    for tab, cols in esquema.items():
        escolhidas = draw(st.lists(st.sampled_from(cols), max_size=len(cols), unique=True))
        if escolhidas:
            validas[tab] = {c: draw(_TEXTO) for c in escolhidas}

    # Tabelas inexistentes.
    tabs_inexistentes = draw(st.lists(_SUFIXO, max_size=3, unique=True))
    inexistentes_tab = [f"x_{t}" for t in tabs_inexistentes]
    # Colunas inexistentes em tabelas existentes.
    colunas_inexistentes = []
    for tab in esquema:
        for c in draw(st.lists(_SUFIXO, max_size=2, unique=True)):
            colunas_inexistentes.append((tab, f"y_{c}"))

    return esquema, validas, inexistentes_tab, colunas_inexistentes


def _criar_banco(esquema):
    conn = sqlite3.connect(":memory:")
    for tab, cols in esquema.items():
        defs = ", ".join(f'"{c}" TEXT' for c in cols)
        conn.execute(f'CREATE TABLE "{tab}" ({defs})')
    return conn


@settings(max_examples=100, deadline=None)
@given(dados=_cenario(), texto=_TEXTO)
def test_descricoes_inexistentes_sao_ignoradas_com_aviso(dados, texto):
    esquema, validas, tabs_inexistentes, cols_inexistentes = dados
    conn = _criar_banco(esquema)
    try:
        base = extrair_esquema(conn, validas)

        com_extras = {tab: dict(cols) for tab, cols in validas.items()}
        for tab in tabs_inexistentes:
            com_extras[tab] = {"qualquer": texto}
        for tab, col in cols_inexistentes:
            com_extras.setdefault(tab, {})[col] = texto

        resultado = extrair_esquema(conn, com_extras)
    finally:
        conn.close()

    # O esquema resultante é igual ao obtido sem as descrições inexistentes.
    assert resultado.tabelas == base.tabelas
    assert resultado.para_prompt() == base.para_prompt()
    assert base.avisos == []

    # Um aviso identifica cada item não encontrado.
    for tab in tabs_inexistentes:
        assert any(tab in aviso for aviso in resultado.avisos)
    for tab, col in cols_inexistentes:
        assert any(f"{tab}.{col}" in aviso for aviso in resultado.avisos)
    assert len(resultado.avisos) == len(tabs_inexistentes) + len(cols_inexistentes)
