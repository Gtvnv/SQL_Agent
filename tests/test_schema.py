"""Testes unitários do Extrator_Esquema.

Validates: Requirements 2.1, 2.3, 2.5, 9.5
"""

import sqlite3

import pytest

from sql_agent.schema import (
    LIMITE_DESCRICAO,
    ErroEsquema,
    extrair_esquema,
    extrair_esquema_ou_sair,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE categorias (id INTEGER PRIMARY KEY, nome TEXT);
        CREATE TABLE produtos (
            id INTEGER PRIMARY KEY,
            nome TEXT,
            preco REAL,
            categoria_id INTEGER REFERENCES categorias(id)
        );
        """
    )
    yield c
    c.close()


def test_sucesso_extrai_tabelas_colunas_e_chaves(conn):
    esquema = extrair_esquema(conn)

    por_nome = {t.nome: t for t in esquema.tabelas}
    assert set(por_nome) == {"categorias", "produtos"}

    cols = {c.nome: c for c in por_nome["produtos"].colunas}
    assert list(cols) == ["id", "nome", "preco", "categoria_id"]
    assert cols["id"].pk is True
    assert cols["preco"].tipo == "REAL"
    assert cols["categoria_id"].fk == ("categorias", "id")
    assert cols["nome"].fk is None
    assert esquema.avisos == []

    prompt = esquema.para_prompt()
    assert "produtos" in prompt and "categoria_id" in prompt


def test_descricao_e_aplicada_na_coluna(conn):
    esquema = extrair_esquema(conn, {"produtos": {"preco": "Preço em reais"}})
    col = next(c for t in esquema.tabelas if t.nome == "produtos" for c in t.colunas if c.nome == "preco")
    assert col.descricao == "Preço em reais"
    assert "Preço em reais" in esquema.para_prompt()


def test_descricao_truncada_em_500_caracteres(conn):
    texto = "a" * (LIMITE_DESCRICAO + 200)
    esquema = extrair_esquema(conn, {"produtos": {"nome": texto}})
    col = next(c for t in esquema.tabelas if t.nome == "produtos" for c in t.colunas if c.nome == "nome")
    assert LIMITE_DESCRICAO == 500
    assert col.descricao == "a" * 500


def test_banco_inacessivel_levanta_erro_esquema():
    c = sqlite3.connect(":memory:")
    c.close()  # conexão fechada: qualquer acesso falha
    with pytest.raises(ErroEsquema):
        extrair_esquema(c)


def test_arquivo_que_nao_e_banco_levanta_erro_esquema(tmp_path):
    arquivo = tmp_path / "invalido.db"
    arquivo.write_bytes(b"isto nao e um banco sqlite" * 100)
    c = sqlite3.connect(str(arquivo))
    try:
        with pytest.raises(ErroEsquema):
            extrair_esquema(c)
    finally:
        c.close()


def test_extrair_esquema_ou_sair_encerra_com_codigo_diferente_de_zero(capsys):
    c = sqlite3.connect(":memory:")
    c.close()
    with pytest.raises(SystemExit) as info:
        extrair_esquema_ou_sair(c)
    assert info.value.code != 0
    assert "esquema" in capsys.readouterr().err.lower()
