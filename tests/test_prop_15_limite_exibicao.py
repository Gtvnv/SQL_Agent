"""Property 15: Limite de exibição e aviso de truncamento."""

import shutil
import sqlite3
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from sql_agent.executor import ExecutorSql


# Feature: text-to-sql-agent, Property 15: Limite de exibição e aviso de truncamento
# **Validates: Requirements 6.3, 6.4**
@settings(max_examples=100, deadline=None)
@given(n=st.integers(min_value=0, max_value=300), limite=st.integers(min_value=1, max_value=200))
def test_limite_exibicao_e_truncamento(n: int, limite: int) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "t.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO t (id, v) VALUES (?, ?)", [(i, f"v{i}") for i in range(n)])
        conn.commit()
        conn.close()

        resultado = ExecutorSql(db, max_linhas=limite).executar("SELECT id, v FROM t ORDER BY id")

        assert len(resultado.linhas) == min(n, limite)
        assert resultado.truncado == (n > limite)
        # A CLI (tarefa 10.1) usa `limite` na mensagem de truncamento.
        assert resultado.limite == limite
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
