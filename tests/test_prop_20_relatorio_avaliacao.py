"""Property 20: Relatório de avaliação é consistente e resiliente a falhas."""

import sqlite3
import tempfile
import time
from pathlib import Path

from hypothesis import given, settings, strategies as st

from sql_agent.agent import STATUS_FALHA, STATUS_SUCESSO, Resposta
from sql_agent.evaluation import avaliar
from sql_agent.executor import ExecutorSql, ResultadoExecucao

# Feature: text-to-sql-agent, Property 20: Relatório de avaliação é consistente e resiliente a falhas
# **Validates: Requirements 9.2, 9.3, 9.4**

SQL_ESPERADA = "SELECT id FROM t ORDER BY id"
TIMEOUT_S = 0.05

_TMP = tempfile.TemporaryDirectory()
_DB = Path(_TMP.name) / "avaliacao.db"
_conn = sqlite3.connect(_DB)
_conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
_conn.executemany("INSERT INTO t (id) VALUES (?)", [(1,), (2,), (3,)])
_conn.commit()
_conn.close()

EXECUTOR = ExecutorSql(_DB, max_linhas=100, timeout_s=2)

DESFECHOS = ["acerto", "sql_errada", "erro_llm", "rejeicao", "erro_execucao", "timeout"]


class AgenteFake:
    def __init__(self, desfechos: dict[str, str]) -> None:
        self.desfechos = desfechos

    def responder(self, pergunta: str) -> Resposta:
        d = self.desfechos[pergunta]
        sql = f"SELECT /* {d} */ id FROM t"
        if d == "acerto":
            return Resposta(
                sql=SQL_ESPERADA,
                resultado=EXECUTOR.executar(SQL_ESPERADA),
                status=STATUS_SUCESSO,
            )
        if d == "sql_errada":
            res = ResultadoExecucao(["id"], [(999,)], False, 100)
            return Resposta(sql=sql, resultado=res, status=STATUS_SUCESSO)
        if d == "erro_llm":
            return Resposta(
                erro="LLM indisponível", etapa_falha="geracao", status=STATUS_FALHA
            )
        if d == "rejeicao":
            return Resposta(
                sql="DELETE FROM t",
                erro="apenas leitura",
                etapa_falha="validacao",
                status=STATUS_FALHA,
            )
        if d == "erro_execucao":
            return Resposta(
                sql="SELECT x FROM t",
                erro="no such column: x",
                etapa_falha="execucao",
                status=STATUS_FALHA,
            )
        time.sleep(0.3)  # timeout
        return Resposta(sql=sql, status=STATUS_FALHA)


@settings(max_examples=100, deadline=None)
@given(st.lists(st.sampled_from(DESFECHOS), min_size=0, max_size=8))
def test_relatorio_consistente_e_resiliente(lista):
    dataset = [
        {"pergunta": f"pergunta {i}", "sql_esperada": SQL_ESPERADA}
        for i in range(len(lista))
    ]
    desfechos = {f"pergunta {i}": d for i, d in enumerate(lista)}

    rel = avaliar(dataset, AgenteFake(desfechos), EXECUTOR, timeout_s=TIMEOUT_S)

    acertos = lista.count("acerto")
    assert rel.total == len(lista)
    assert rel.acertos == acertos
    assert rel.taxa == (round(100 * acertos / len(lista), 1) if lista else 0.0)

    # todos os pares processados; cada falha listada com pergunta, SQL e motivo
    assert len(rel.falhas) == len(lista) - acertos
    esperadas = [(f"pergunta {i}", d) for i, d in enumerate(lista) if d != "acerto"]
    assert [f.pergunta for f in rel.falhas] == [p for p, _ in esperadas]
    for falha, (_, d) in zip(rel.falhas, esperadas):
        assert falha.motivo
        if d == "timeout":
            assert "tempo limite" in falha.motivo
        if d in ("sql_errada", "rejeicao", "erro_execucao"):
            assert falha.sql_gerada
        if d == "erro_llm":
            assert "LLM" in falha.motivo
        if d == "rejeicao":
            assert "validador" in falha.motivo
        if d == "erro_execucao":
            assert "execução" in falha.motivo

    texto = rel.formatar()
    for falha in rel.falhas:
        assert falha.pergunta in texto and falha.motivo in texto
