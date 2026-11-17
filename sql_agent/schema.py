"""Extrator_Esquema: lê tabelas, colunas, chaves e descrições do banco SQLite."""

from __future__ import annotations

import sqlite3
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

LIMITE_DESCRICAO = 500
TIMEOUT_LEITURA_S = 10.0


class ErroEsquema(Exception):
    """Falha ao acessar o banco ou ao concluir a leitura do esquema no prazo."""


@dataclass
class Coluna:
    nome: str
    tipo: str
    pk: bool = False
    fk: tuple[str, str] | None = None  # (tabela referenciada, coluna referenciada)
    descricao: str | None = None


@dataclass
class Tabela:
    nome: str
    colunas: list[Coluna] = field(default_factory=list)


@dataclass
class SchemaInfo:
    tabelas: list[Tabela] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def para_prompt(self) -> str:
        """Texto com todas as tabelas, colunas, chaves e descrições."""
        blocos: list[str] = []
        for tabela in self.tabelas:
            linhas = [f"Tabela {tabela.nome}:"]
            for col in tabela.colunas:
                partes = [f"  - {col.nome} {col.tipo}".rstrip()]
                if col.pk:
                    partes.append("PRIMARY KEY")
                if col.fk:
                    partes.append(f"REFERENCES {col.fk[0]}({col.fk[1]})")
                linha = " ".join(partes)
                if col.descricao:
                    linha += f" -- {col.descricao}"
                linhas.append(linha)
            blocos.append("\n".join(linhas))
        return "\n\n".join(blocos)


def _quote(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def _ler(conn: sqlite3.Connection, deadline: float) -> list[Tabela]:
    def verificar_prazo() -> None:
        if time.monotonic() > deadline:
            raise ErroEsquema("tempo limite excedido ao ler o esquema")

    nomes = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    infos: dict[str, list[tuple]] = {}
    for nome in nomes:
        verificar_prazo()
        infos[nome] = conn.execute(f"PRAGMA table_info({_quote(nome)})").fetchall()

    tabelas: list[Tabela] = []
    for nome in nomes:
        verificar_prazo()
        fks: dict[str, tuple[str, str]] = {}
        for row in conn.execute(f"PRAGMA foreign_key_list({_quote(nome)})"):
            destino_tab, origem, destino_col = row[2], row[3], row[4]
            if destino_col is None:  # FK implícita para a PK da tabela de destino
                pks = [c[1] for c in infos.get(destino_tab, []) if c[5]]
                destino_col = pks[0] if pks else ""
            fks[origem] = (destino_tab, destino_col)
        colunas = [
            Coluna(
                nome=c[1],
                tipo=c[2] or "",
                pk=bool(c[5]),
                fk=fks.get(c[1]),
            )
            for c in infos[nome]
        ]
        tabelas.append(Tabela(nome=nome, colunas=colunas))
    return tabelas


def _aplicar_descricoes(
    tabelas: list[Tabela], descricoes: Mapping[str, Any] | None, avisos: list[str]
) -> None:
    """`descricoes` tem a forma {tabela: {coluna: texto}}."""
    por_nome = {t.nome: t for t in tabelas}
    for nome_tab, cols in (descricoes or {}).items():
        tabela = por_nome.get(nome_tab)
        if tabela is None:
            avisos.append(
                f"Descrição ignorada: tabela '{nome_tab}' não encontrada no banco."
            )
            continue
        if not isinstance(cols, Mapping):
            avisos.append(
                f"Descrição ignorada: formato inválido para a tabela '{nome_tab}'."
            )
            continue
        por_col = {c.nome: c for c in tabela.colunas}
        for nome_col, texto in cols.items():
            coluna = por_col.get(nome_col)
            if coluna is None:
                avisos.append(
                    f"Descrição ignorada: coluna '{nome_tab}.{nome_col}' "
                    "não encontrada no banco."
                )
                continue
            coluna.descricao = str(texto)[:LIMITE_DESCRICAO]


def extrair_esquema(
    conn: sqlite3.Connection,
    descricoes: Mapping[str, Any] | None = None,
    timeout_s: float = TIMEOUT_LEITURA_S,
) -> SchemaInfo:
    """Extrai o esquema de `conn`.

    Levanta `ErroEsquema` se o banco não puder ser lido ou se a leitura
    exceder `timeout_s` (10 s por padrão).
    """
    deadline = time.monotonic() + timeout_s

    def interromper() -> int:
        return 1 if time.monotonic() > deadline else 0

    try:
        conn.set_progress_handler(interromper, 1000)
        tabelas = _ler(conn, deadline)
    except ErroEsquema:
        raise
    except sqlite3.Error as exc:
        if time.monotonic() > deadline:
            raise ErroEsquema("tempo limite excedido ao ler o esquema") from exc
        raise ErroEsquema(f"falha ao acessar o banco de dados: {exc}") from exc
    finally:
        try:
            conn.set_progress_handler(None, 0)
        except sqlite3.Error:
            pass

    avisos: list[str] = []
    _aplicar_descricoes(tabelas, descricoes, avisos)
    return SchemaInfo(tabelas=tabelas, avisos=avisos)


def extrair_esquema_ou_sair(
    conn: sqlite3.Connection,
    descricoes: Mapping[str, Any] | None = None,
    timeout_s: float = TIMEOUT_LEITURA_S,
) -> SchemaInfo:
    """Como `extrair_esquema`, mas exibe o motivo e encerra com código 1 em falha."""
    try:
        return extrair_esquema(conn, descricoes, timeout_s)
    except ErroEsquema as exc:
        print(f"Erro ao ler o esquema do banco: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
