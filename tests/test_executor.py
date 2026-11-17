"""Testes unitários do Executor_SQL."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from sql_agent.executor import (
    ErroAcessoBanco,
    ErroExecucao,
    ExecutorSql,
    TempoExcedido,
)


def _hash(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def test_consulta_simples_retorna_colunas_e_linhas(db_path):
    r = ExecutorSql(db_path).executar("SELECT id, nome FROM categorias ORDER BY id")
    assert r.colunas == ["id", "nome"]
    assert r.linhas == [(1, "Livros"), (2, "Games")]
    assert r.truncado is False


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO categorias VALUES (3, 'Novo')",
        "UPDATE produtos SET preco = 0",
        "DELETE FROM produtos",
        "DROP TABLE produtos",
    ],
)
def test_escrita_pela_conexao_ro_falha_sem_alterar_arquivo(db_path, sql):
    antes = _hash(db_path)
    with pytest.raises(ErroExecucao):
        ExecutorSql(db_path).executar(sql)
    assert _hash(db_path) == antes


def test_banco_inacessivel_gera_erro_acesso_banco(tmp_path):
    inexistente = tmp_path / "nao_existe.sqlite"
    with pytest.raises(ErroAcessoBanco):
        ExecutorSql(inexistente).executar("SELECT 1")
    assert not inexistente.exists()


def test_zero_linhas_retorna_resultado_vazio_com_colunas(db_path):
    r = ExecutorSql(db_path).executar("SELECT id, nome FROM categorias WHERE id < 0")
    assert r.linhas == []
    assert r.colunas == ["id", "nome"]
    assert r.truncado is False


def test_consulta_lenta_excede_limite_de_1s(db_path):
    sql = (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 1000000000) "
        "SELECT count(*) FROM c"
    )
    inicio = time.monotonic()
    with pytest.raises(TempoExcedido):
        ExecutorSql(db_path, timeout_s=1).executar(sql)
    assert time.monotonic() - inicio < 5


def test_erro_de_execucao_nao_devolve_resultado_parcial(db_path):
    with pytest.raises(ErroExecucao):
        ExecutorSql(db_path).executar("SELECT * FROM tabela_inexistente")


def test_truncamento_respeita_max_linhas(db_path):
    r = ExecutorSql(db_path, max_linhas=1).executar("SELECT id FROM categorias ORDER BY id")
    assert r.linhas == [(1,)]
    assert r.truncado is True
    assert r.limite == 1
