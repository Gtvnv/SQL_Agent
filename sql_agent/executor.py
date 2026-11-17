"""Executor_SQL: executa consultas de leitura em conexão SQLite somente leitura."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


class ErroExecucao(Exception):
    """Erro devolvido pelo SQLite ao executar a consulta."""


class TempoExcedido(Exception):
    """A consulta ultrapassou o tempo limite."""


class ErroAcessoBanco(Exception):
    """Falha ao abrir o banco em modo somente leitura."""


@dataclass
class ResultadoExecucao:
    colunas: list[str]
    linhas: list[tuple]
    truncado: bool
    limite: int


class ExecutorSql:
    """Executa SQL sempre em conexão `mode=ro`, sem fallback de escrita."""

    # Número de instruções da VM entre chamadas do progress handler.
    _PASSO_PROGRESSO = 1000

    def __init__(self, db_path: str | Path, max_linhas: int = 100, timeout_s: float = 10) -> None:
        self.db_path = str(db_path)
        self.max_linhas = max_linhas
        self.timeout_s = timeout_s

    def _uri(self) -> str:
        return f"{Path(self.db_path).resolve().as_uri()}?mode=ro"

    def _conectar(self) -> sqlite3.Connection:
        try:
            return sqlite3.connect(self._uri(), uri=True)
        except sqlite3.Error as exc:
            raise ErroAcessoBanco(f"Falha ao acessar o banco de dados: {exc}") from exc

    def executar(self, sql: str) -> ResultadoExecucao:
        conn = self._conectar()
        try:
            limite_tempo = time.monotonic() + self.timeout_s
            excedeu = False

            def _progresso() -> int:
                nonlocal excedeu
                if time.monotonic() > limite_tempo:
                    excedeu = True
                    return 1  # diferente de zero interrompe a consulta
                return 0

            conn.set_progress_handler(_progresso, self._PASSO_PROGRESSO)
            try:
                cursor = conn.execute(sql)
                colunas = [d[0] for d in (cursor.description or [])]
                linhas = cursor.fetchmany(self.max_linhas + 1)
            except sqlite3.OperationalError as exc:
                if excedeu:
                    raise TempoExcedido(
                        f"A consulta excedeu o tempo limite de {self.timeout_s} s."
                    ) from exc
                # Banco inacessível ou corrompido durante a execução.
                msg = str(exc).lower()
                if "unable to open" in msg or "disk i/o" in msg:
                    raise ErroAcessoBanco(f"Falha ao acessar o banco de dados: {exc}") from exc
                raise ErroExecucao(str(exc)) from exc
            except sqlite3.Error as exc:
                raise ErroExecucao(str(exc)) from exc

            truncado = len(linhas) > self.max_linhas
            if truncado:
                linhas = linhas[: self.max_linhas]
            return ResultadoExecucao(
                colunas=colunas,
                linhas=[tuple(l) for l in linhas],
                truncado=truncado,
                limite=self.max_linhas,
            )
        finally:
            conn.close()
