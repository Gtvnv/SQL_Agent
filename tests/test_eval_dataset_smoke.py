"""Teste de fumaça do Conjunto_Avaliação (Requirement 9.1)."""
from __future__ import annotations

import importlib.util
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_RAIZ = Path(__file__).resolve().parent.parent
_DATASET = _RAIZ / "eval" / "dataset.yaml"
_CATEGORIAS = ("filtros", "agregacoes", "juncoes", "ordenacao", "agrupamento")

_spec = importlib.util.spec_from_file_location("create_db", _RAIZ / "db" / "create_db.py")
create_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(create_db)


@pytest.fixture(scope="module")
def dataset():
    return yaml.safe_load(_DATASET.read_text(encoding="utf-8"))


def test_pelo_menos_15_pares_com_campos(dataset):
    assert isinstance(dataset, list) and len(dataset) >= 15
    for par in dataset:
        for campo in ("pergunta", "sql_esperada", "categoria"):
            assert isinstance(par.get(campo), str) and par[campo].strip()


def test_pelo_menos_2_pares_por_categoria(dataset):
    contagem = Counter(p["categoria"] for p in dataset)
    assert set(contagem) <= set(_CATEGORIAS)
    for categoria in _CATEGORIAS:
        assert contagem[categoria] >= 2, categoria


def test_sql_esperada_executa_no_banco_exemplo(dataset, tmp_path):
    destino = tmp_path / "loja.sqlite"
    create_db.criar_banco(destino)
    conn = sqlite3.connect(f"file:{destino.as_posix()}?mode=ro", uri=True)
    try:
        for par in dataset:
            try:
                conn.execute(par["sql_esperada"]).fetchall()
            except sqlite3.Error as exc:
                pytest.fail(f"SQL falhou ({par['pergunta']}): {exc}")
    finally:
        conn.close()
