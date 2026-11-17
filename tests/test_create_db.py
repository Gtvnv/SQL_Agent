"""Testes do db/create_db.py (Requirements 7.1, 7.2, 7.3, 7.4)."""
from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parent.parent / "db" / "create_db.py"
_spec = importlib.util.spec_from_file_location("create_db", _CAMINHO)
create_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(create_db)


def _tabelas(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]


def _fks(conn):
    return sorted(
        (t, r[2], r[3], r[4])
        for t in _tabelas(conn)
        for r in conn.execute(f'PRAGMA foreign_key_list("{t}")'))


def _contagens(conn):
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in _tabelas(conn)}


def _descrever(caminho):
    conn = sqlite3.connect(caminho)
    try:
        return _tabelas(conn), _fks(conn), _contagens(conn)
    finally:
        conn.close()


def _hash(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def test_execucao_dupla_e_idempotente(tmp_path):
    destino = tmp_path / "loja.sqlite"
    assert create_db.main([str(destino)]) == 0
    primeira = _descrever(destino)
    assert create_db.main([str(destino)]) == 0
    assert _descrever(destino) == primeira
    assert not destino.with_name("loja.sqlite.tmp").exists()


def test_quantidade_de_tabelas_fks_e_linhas(tmp_path):
    destino = tmp_path / "loja.sqlite"
    assert create_db.main([str(destino)]) == 0
    tabelas, fks, contagens = _descrever(destino)
    assert 4 <= len(tabelas) <= 10
    assert len(fks) >= 1
    assert all(n >= 10 for n in contagens.values())
    assert sum(contagens.values()) >= 100


def test_banco_sem_violacao_de_chave_estrangeira(tmp_path):
    destino = tmp_path / "loja.sqlite"
    create_db.criar_banco(destino)
    conn = sqlite3.connect(destino)
    try:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_falha_preserva_arquivo_final_e_remove_tmp(tmp_path, monkeypatch, capsys):
    destino = tmp_path / "loja.sqlite"
    assert create_db.main([str(destino)]) == 0
    antes = _hash(destino)

    def falhar(conn):
        conn.execute("INSERT INTO categorias (nome) VALUES ('parcial')")
        raise sqlite3.OperationalError("falha injetada")

    monkeypatch.setattr(create_db, "popular", falhar)
    assert create_db.main([str(destino)]) == 1

    assert _hash(destino) == antes
    assert not destino.with_name("loja.sqlite.tmp").exists()
    err = capsys.readouterr().err
    assert "popular tabelas" in err and "falha injetada" in err


def test_falha_sem_arquivo_previo_nao_deixa_dados(tmp_path, monkeypatch):
    destino = tmp_path / "loja.sqlite"

    def falhar(conn):
        raise sqlite3.OperationalError("falha injetada")

    monkeypatch.setattr(create_db, "criar_esquema", falhar)
    with pytest.raises(RuntimeError, match="criar tabelas"):
        create_db.criar_banco(destino)
    assert not destino.exists()
    assert not destino.with_name("loja.sqlite.tmp").exists()
