"""Property 2: Falhas por pergunta não encerram a sessão."""

import shutil
import sqlite3
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from sql_agent.agent import STATUS_FALHA, STATUS_SUCESSO, Agente
from sql_agent.config import Config
from sql_agent.executor import ErroExecucao, ExecutorSql
from sql_agent.llm import LlmLimiteError, LlmRedeError, LlmTimeout
from sql_agent.schema import extrair_esquema

SQL_OK = "SELECT id, nome FROM produtos ORDER BY id"

# tipo de falha -> (resposta do LLM ou exceção, executor falha?, etapas aceitas)
FALHAS = {
    "timeout": (LlmTimeout("timeout"), False, {"geracao"}),
    "rede": (LlmRedeError("rede"), False, {"geracao"}),
    "limite": (LlmLimiteError("limite"), False, {"geracao"}),
    "validador": (
        "DELETE FROM produtos WHERE id IN (SELECT id FROM produtos)",
        False,
        {"validacao"},
    ),
    "execucao": (SQL_OK, True, {"execucao", "correcao"}),
}


class _LlmRoteirizado:
    """Devolve (ou lança) o item atual em todas as chamadas."""

    def __init__(self) -> None:
        self.atual: object = SQL_OK

    def completar(self, system: str, user: str, timeout_s: float) -> str:
        if isinstance(self.atual, BaseException):
            raise self.atual
        return str(self.atual)


class _ExecutorAlternavel:
    def __init__(self, real: ExecutorSql) -> None:
        self.real = real
        self.falhar = False

    def executar(self, sql: str):
        if self.falhar:
            raise ErroExecucao("no such column: simulada")
        return self.real.executar(sql)


# Feature: text-to-sql-agent, Property 2: Falhas por pergunta não encerram a sessão
# **Validates: Requirements 1.6, 4.7, 5.6**
@settings(max_examples=100, deadline=None)
@given(
    tipos=st.lists(st.sampled_from(sorted(FALHAS)), min_size=1, max_size=4),
    max_correcoes=st.integers(min_value=1, max_value=3),
)
def test_falhas_nao_encerram_sessao(tipos: list[str], max_correcoes: int) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "t.sqlite"
        c = sqlite3.connect(db)
        c.executescript(
            "CREATE TABLE produtos (id INTEGER PRIMARY KEY, nome TEXT);"
            "INSERT INTO produtos VALUES (1, 'a'), (2, 'b');"
        )
        c.commit()
        c.close()
        ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        esquema = extrair_esquema(ro, {})
        ro.close()

        cfg = Config(
            api_key="chave-secreta-teste",
            model="m",
            db_path=str(db),
            max_correcoes=max_correcoes,
            audit_path=str(tmp / "audit.jsonl"),
        )
        llm = _LlmRoteirizado()
        executor = _ExecutorAlternavel(ExecutorSql(db, max_linhas=100, timeout_s=5))
        agente = Agente(cfg, esquema, llm, executor)

        for tipo in tipos:
            efeito, exec_falha, etapas = FALHAS[tipo]
            llm.atual = efeito
            executor.falhar = exec_falha
            r = agente.responder("pergunta que falha")
            assert r.status == STATUS_FALHA
            assert r.etapa_falha in etapas
            assert r.resultado is None
            assert r.erro

            # A pergunta seguinte é processada normalmente.
            llm.atual = SQL_OK
            executor.falhar = False
            ok = agente.responder("pergunta seguinte")
            assert ok.status == STATUS_SUCESSO
            assert ok.etapa_falha is None
            assert ok.resultado is not None
            assert ok.resultado.linhas == [(1, "a"), (2, "b")]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
