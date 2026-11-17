"""Property 3: Extração de esquema é completa e fiel."""

import sqlite3

from hypothesis import given, settings, strategies as st

from sql_agent.schema import extrair_esquema

# Feature: text-to-sql-agent, Property 3: Extração de esquema é completa e fiel
# **Validates: Requirements 2.1**

_TIPOS = ["INTEGER", "TEXT", "REAL", "BLOB", "NUMERIC", "VARCHAR(50)", ""]


@st.composite
def _esquemas(draw):
    """Gera um modelo de esquema: lista de tabelas com colunas, PK e FK.

    Cada tabela é (nome, [(coluna, tipo, pk, fk | None)], autoincrement).
    """
    n_tabelas = draw(st.integers(1, 5))
    nomes_tab = [f"t_{i}" for i in range(n_tabelas)]
    colunas_por_tab: dict[str, list[str]] = {}
    for nome in nomes_tab:
        n_cols = draw(st.integers(1, 6))
        colunas_por_tab[nome] = [f"c_{j}" for j in range(n_cols)]

    tabelas = []
    for nome in nomes_tab:
        cols = colunas_por_tab[nome]
        pks = draw(st.sets(st.sampled_from(cols), max_size=min(3, len(cols))))
        colunas = []
        for col in cols:
            tipo = draw(st.sampled_from(_TIPOS))
            fk = None
            if col not in pks and draw(st.booleans()):
                destino_tab = draw(st.sampled_from(nomes_tab))
                destino_col = draw(st.sampled_from(colunas_por_tab[destino_tab]))
                fk = (destino_tab, destino_col)
            colunas.append((col, tipo, col in pks, fk))
        # AUTOINCREMENT exige PK única do tipo INTEGER; cria a tabela sqlite_sequence.
        auto = False
        if len(pks) == 1:
            idx = cols.index(next(iter(pks)))
            if colunas[idx][1] == "INTEGER":
                auto = draw(st.booleans())
        tabelas.append((nome, colunas, auto))
    return tabelas


def _criar_banco(tabelas) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    for nome, colunas, auto in tabelas:
        defs = []
        pks = [c for c, _, pk, _ in colunas if pk]
        for col, tipo, pk, fk in colunas:
            d = f'"{col}" {tipo}'.rstrip()
            if auto and pk:
                d += " PRIMARY KEY AUTOINCREMENT"
            defs.append(d)
        if pks and not auto:
            defs.append("PRIMARY KEY (" + ", ".join(f'"{c}"' for c in pks) + ")")
        for col, _, _, fk in colunas:
            if fk:
                defs.append(f'FOREIGN KEY ("{col}") REFERENCES "{fk[0]}" ("{fk[1]}")')
        conn.execute(f'CREATE TABLE "{nome}" ({", ".join(defs)})')
    conn.commit()
    return conn


@settings(max_examples=100, deadline=None)
@given(_esquemas())
def test_extracao_esquema_completa_e_fiel(tabelas):
    conn = _criar_banco(tabelas)
    try:
        esquema = extrair_esquema(conn, {})
    finally:
        conn.close()

    extraidas = {t.nome: t for t in esquema.tabelas}

    # Todas as tabelas de usuário, sem duplicatas e sem tabelas sqlite_*.
    assert len(extraidas) == len(esquema.tabelas)
    assert set(extraidas) == {nome for nome, _, _ in tabelas}
    assert not any(n.startswith("sqlite_") for n in extraidas)

    for nome, colunas, _ in tabelas:
        obtidas = extraidas[nome].colunas
        assert [c.nome for c in obtidas] == [c[0] for c in colunas]
        for obtida, (col, tipo, pk, fk) in zip(obtidas, colunas):
            assert obtida.tipo == tipo, (nome, col)
            assert obtida.pk == pk, (nome, col)
            assert obtida.fk == fk, (nome, col)
