"""Testes unitários do Validador_SQL (Requisitos 4.1, 4.2, 9.5)."""
from __future__ import annotations

import time

import pytest

from sql_agent.schema import Coluna, SchemaInfo, Tabela
from sql_agent.validator import validar


@pytest.fixture(scope="module")
def esquema() -> SchemaInfo:
    return SchemaInfo(
        tabelas=[
            Tabela("categorias", [Coluna("id", "INTEGER", pk=True), Coluna("nome", "TEXT")]),
            Tabela(
                "produtos",
                [
                    Coluna("id", "INTEGER", pk=True),
                    Coluna("nome", "TEXT"),
                    Coluna("preco", "REAL"),
                    Coluna("categoria_id", "INTEGER", fk=("categorias", "id")),
                ],
            ),
        ]
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM produtos",
        "SELECT nome, preco FROM produtos WHERE preco > 10 ORDER BY preco",
        "WITH caros AS (SELECT * FROM produtos WHERE preco > 100) SELECT nome FROM caros",
        "SELECT p.nome, c.nome FROM produtos p JOIN categorias c ON c.id = p.categoria_id",
        "SELECT nome FROM produtos WHERE categoria_id IN (SELECT id FROM categorias WHERE nome = 'Games')",
        "SELECT categoria_id, COUNT(*) AS total FROM produtos GROUP BY categoria_id HAVING total > 1",
        "SELECT nome FROM produtos UNION SELECT nome FROM categorias",
    ],
)
def test_aprova_consultas_de_leitura(sql, esquema):
    r = validar(sql, esquema)
    assert r.aprovada, r.motivo
    assert r.motivo is None


@pytest.mark.parametrize(
    "sql,palavra",
    [
        ("INSERT INTO produtos (nome) VALUES ('x')", "INSERT"),
        ("UPDATE produtos SET preco = 0", "UPDATE"),
        ("DELETE FROM produtos WHERE id = 1", "DELETE"),
        ("DROP TABLE produtos", "DROP"),
    ],
)
def test_rejeita_escrita_e_identifica_palavra(sql, palavra, esquema):
    r = validar(sql, esquema)
    assert not r.aprovada
    assert r.palavra_chave == palavra
    assert palavra in r.motivo


def test_rejeita_escrita_escondida_em_segunda_instrucao(esquema):
    r = validar("SELECT * FROM produtos; DROP TABLE produtos", esquema)
    assert not r.aprovada
    assert r.palavra_chave == "DROP"


def test_rejeita_escrita_dentro_de_cte(esquema):
    r = validar("WITH x AS (DELETE FROM produtos RETURNING id) SELECT * FROM x", esquema)
    assert not r.aprovada


def test_palavra_de_escrita_em_literal_nao_reprova(esquema):
    assert validar("SELECT * FROM produtos WHERE nome = 'DROP TABLE'", esquema).aprovada


def test_rejeita_multiplas_instrucoes_de_leitura(esquema):
    assert not validar("SELECT 1; SELECT 2", esquema).aprovada


def test_rejeita_consulta_vazia(esquema):
    assert not validar("", esquema).aprovada


def test_rejeita_tabela_inexistente(esquema):
    r = validar("SELECT * FROM clientes", esquema)
    assert not r.aprovada
    assert "clientes" in r.motivo


def test_rejeita_coluna_inexistente(esquema):
    r = validar("SELECT inexistente FROM produtos", esquema)
    assert not r.aprovada
    assert "inexistente" in r.motivo


def test_tempo_de_validacao_abaixo_de_500ms(esquema):
    sql = (
        "SELECT p.nome, c.nome FROM produtos p JOIN categorias c ON c.id = p.categoria_id "
        "WHERE p.preco > (SELECT AVG(preco) FROM produtos)"
    )
    validar(sql, esquema)  # aquecimento
    inicio = time.perf_counter()
    r = validar(sql, esquema)
    assert (time.perf_counter() - inicio) < 0.5
    assert r.aprovada
    inicio = time.perf_counter()
    validar("DROP TABLE produtos", esquema)
    assert (time.perf_counter() - inicio) < 0.5
