"""Validador_SQL: aprova somente consultas de leitura que respeitam o esquema."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import Scope, traverse_scope

from sql_agent.schema import SchemaInfo

DIALETO = "sqlite"

# Silencia o aviso de "fallback para Command" emitido pelo sqlglot.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

PALAVRAS_ESCRITA = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "REPLACE",
    "DROP",
    "ALTER",
    "CREATE",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "PRAGMA",
)

_TIPO_PARA_PALAVRA: tuple[tuple[type[exp.Expression], str], ...] = (
    (exp.Insert, "INSERT"),
    (exp.Update, "UPDATE"),
    (exp.Delete, "DELETE"),
    (exp.Drop, "DROP"),
    (exp.Alter, "ALTER"),
    (exp.Create, "CREATE"),
    (exp.Attach, "ATTACH"),
    (exp.Detach, "DETACH"),
    (exp.Pragma, "PRAGMA"),
    (exp.TruncateTable, "TRUNCATE"),
)


@dataclass
class ResultadoValidacao:
    aprovada: bool
    motivo: str | None = None
    palavra_chave: str | None = None


def _reprovar(motivo: str, palavra: str | None = None) -> ResultadoValidacao:
    return ResultadoValidacao(False, motivo, palavra)


def _palavra_escrita(no: exp.Expression) -> str | None:
    """Palavra-chave de escrita/definição representada por `no`, se houver."""
    if isinstance(no, exp.Command):
        palavra = str(no.this).upper()
        return palavra if palavra in PALAVRAS_ESCRITA else None
    if isinstance(no, exp.Insert):
        # INSERT OR REPLACE / REPLACE INTO
        alt = str(no.args.get("alternative") or "").upper()
        return "REPLACE" if alt == "REPLACE" else "INSERT"
    for tipo, palavra in _TIPO_PARA_PALAVRA:
        if isinstance(no, tipo):
            return palavra
    return None


def _achar_palavra_escrita(arvores: list[exp.Expression]) -> str | None:
    for arvore in arvores:
        for no in arvore.walk():
            palavra = _palavra_escrita(no)
            if palavra:
                return palavra
    return None


def _primeira_palavra(sql: str) -> str | None:
    """Primeira palavra-chave de escrita do texto (usado quando o parse falha)."""
    try:
        tokens = sqlglot.tokenize(sql, read=DIALETO)
    except SqlglotError:
        tokens = []
    for token in tokens:
        texto = token.text.upper()
        if texto in PALAVRAS_ESCRITA and token.token_type.name != "STRING":
            return texto
    m = re.match(r"\s*([A-Za-z]+)", sql)
    if m and m.group(1).upper() in PALAVRAS_ESCRITA:
        return m.group(1).upper()
    return None


# ---------------------------------------------------------------------------
# Checagem de tabelas e colunas
# ---------------------------------------------------------------------------

class _Opaca:
    """Fonte cujas colunas não conhecemos (ex.: função de tabela)."""


_OPACA = _Opaca()


def _colunas_da_fonte(fonte, indice: dict[str, set[str]]):
    """Conjunto de colunas (minúsculas) de uma fonte, ou `_OPACA`/None se estrela."""
    if isinstance(fonte, Scope):
        expr = fonte.expression
        pai = expr.parent
        nomes = list(getattr(pai, "alias_column_names", []) or [])
        if not nomes:
            nomes = list(expr.named_selects)
        if any(isinstance(s, exp.Star) or (isinstance(s, exp.Column) and isinstance(s.this, exp.Star))
               for s in _projecoes(expr)):
            return _OPACA  # SELECT * / t.*: não enumeramos as colunas
        return {n.lower() for n in nomes}
    if isinstance(fonte, exp.Table):
        if not isinstance(fonte.this, exp.Identifier):
            return _OPACA
        return indice.get(fonte.name.lower())
    return _OPACA


def _projecoes(expr: exp.Expression) -> list[exp.Expression]:
    if isinstance(expr, exp.SetOperation):
        return _projecoes(expr.left)
    if isinstance(expr, exp.Select):
        return list(expr.expressions)
    return []


def _verificar_esquema(arvore: exp.Expression, esquema: SchemaInfo) -> str | None:
    indice: dict[str, set[str]] = {
        t.nome.lower(): {c.nome.lower() for c in t.colunas} for t in esquema.tabelas
    }
    nomes_tabelas = {t.nome.lower(): t.nome for t in esquema.tabelas}

    try:
        escopos = list(traverse_scope(arvore))
    except SqlglotError as exc:
        return f"não foi possível analisar a consulta: {exc}"

    # Tabelas
    for escopo in escopos:
        for fonte in escopo.sources.values():
            if isinstance(fonte, exp.Table) and isinstance(fonte.this, exp.Identifier):
                if fonte.name.lower() not in nomes_tabelas:
                    return f"tabela '{fonte.name}' não existe no esquema"

    # Colunas: cada coluna pertence ao escopo mais próximo que a contém.
    por_expressao = {id(e.expression): e for e in escopos}
    for coluna in arvore.find_all(exp.Column):
        escopo = _escopo_da_coluna(coluna, por_expressao)
        if escopo is None:
            continue
        if isinstance(coluna.this, exp.Star):
            qual = coluna.table
            if qual and _resolver_fonte(escopo, qual) is None:
                return f"tabela ou alias '{qual}' não existe na consulta"
            continue
        nome = coluna.name
        nome_l = nome.lower()
        qual = coluna.table
        if qual:
            achado = _resolver_fonte(escopo, qual)
            if achado is None:
                return f"tabela ou alias '{qual}' não existe na consulta"
            cols = _colunas_da_fonte(achado, indice)
            if cols is not _OPACA and (cols is None or nome_l not in cols):
                return f"coluna '{qual}.{nome}' não existe no esquema"
            continue
        if not _coluna_resolvida(escopo, nome_l, indice):
            return f"coluna '{nome}' não existe no esquema"
    return None


def _escopo_da_coluna(coluna: exp.Column, por_expressao: dict[int, Scope]) -> Scope | None:
    no: exp.Expression | None = coluna.parent
    while no is not None:
        escopo = por_expressao.get(id(no))
        if escopo is not None:
            return escopo
        no = no.parent
    return None


def _aliases_explicitos(expr: exp.Expression) -> set[str]:
    return {p.alias.lower() for p in _projecoes(expr) if isinstance(p, exp.Alias)}


def _resolver_fonte(escopo: Scope, qualificador: str):
    """Procura o alias/tabela no escopo e nos escopos externos (subconsultas correlacionadas)."""
    q = qualificador.lower()
    atual: Scope | None = escopo
    while atual is not None:
        for nome, fonte in atual.sources.items():
            if nome.lower() == q:
                return fonte
        atual = atual.parent
    return None


def _coluna_resolvida(escopo: Scope, nome: str, indice: dict[str, set[str]]) -> bool:
    atual: Scope | None = escopo
    while atual is not None:
        for fonte in atual.sources.values():
            cols = _colunas_da_fonte(fonte, indice)
            if cols is _OPACA or (cols is not None and nome in cols):
                return True
        # Alias explícito de projeção (SQLite permite em WHERE/GROUP BY/HAVING/ORDER BY).
        if nome in _aliases_explicitos(atual.expression):
            return True
        atual = atual.parent
    return False


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def validar(sql: str, esquema: SchemaInfo) -> ResultadoValidacao:
    """Valida `sql` (SQLite): leitura única e referências existentes no esquema."""
    try:
        instrucoes = sqlglot.parse(sql or "", read=DIALETO)
    except SqlglotError as exc:
        palavra = _primeira_palavra(sql or "")
        if palavra:
            return _reprovar(
                f"instrução de escrita ou definição não permitida: {palavra}", palavra
            )
        return _reprovar(f"não foi possível interpretar a consulta: {exc}")

    arvores = [i for i in instrucoes if i is not None]
    if not arvores:
        return _reprovar("consulta vazia")

    palavra = _achar_palavra_escrita(arvores)
    if palavra:
        return _reprovar(
            f"instrução de escrita ou definição não permitida: {palavra}", palavra
        )

    if len(arvores) > 1:
        return _reprovar("somente uma instrução por consulta")

    arvore = arvores[0]
    if not isinstance(arvore, (exp.Select, exp.SetOperation)):
        return _reprovar("somente consultas SELECT ou WITH ... SELECT são permitidas")

    motivo = _verificar_esquema(arvore, esquema)
    if motivo:
        return _reprovar(motivo)
    return ResultadoValidacao(True)
