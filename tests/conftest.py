"""Fixtures compartilhadas: banco temporário e cliente LLM falso."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pytest


@dataclass
class FakeLlmClient:
    """Cliente LLM falso: devolve respostas enfileiradas e registra as chamadas.

    Cada item de `respostas` é uma string (retornada) ou uma exceção (lançada).
    Quando a fila acaba, repete a última resposta.
    """

    respostas: list = field(default_factory=list)
    chamadas: list[tuple[str, str, float]] = field(default_factory=list)

    def completar(self, system: str, user: str, timeout_s: float) -> str:
        self.chamadas.append((system, user, timeout_s))
        if not self.respostas:
            return ""
        item = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def fake_llm() -> FakeLlmClient:
    return FakeLlmClient()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Banco SQLite temporário com um esquema pequeno de loja."""
    caminho = tmp_path / "teste.sqlite"
    conn = sqlite3.connect(caminho)
    conn.executescript(
        """
        CREATE TABLE categorias (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
        CREATE TABLE produtos (
            id INTEGER PRIMARY KEY, nome TEXT NOT NULL, preco REAL,
            categoria_id INTEGER REFERENCES categorias(id)
        );
        INSERT INTO categorias VALUES (1, 'Livros'), (2, 'Games');
        INSERT INTO produtos VALUES (1, 'Dom Casmurro', 39.9, 1), (2, 'Zelda', 299.0, 2);
        """
    )
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def conn(db_path: Path):
    """Conexão somente leitura ao banco temporário."""
    c = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    yield c
    c.close()
