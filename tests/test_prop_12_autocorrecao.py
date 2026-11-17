"""Property 12: Autocorreção respeita o limite e para no primeiro sucesso."""

import shutil
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from sql_agent.agent import ETAPA_EXECUCAO, STATUS_FALHA, STATUS_SUCESSO, Agente
from sql_agent.config import Config
from sql_agent.executor import ErroExecucao, ResultadoExecucao
from sql_agent.schema import Coluna, SchemaInfo, Tabela

MARCA_CORRECAO = "falhou na execução"


def _sql(i: int) -> str:
    return f"SELECT id FROM produtos WHERE id = {i}"


class FakeLlmClient:
    """Devolve uma SQL distinta a cada geração/correção e registra as chamadas."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[str, str]] = []
        self.proxima = 0

    def completar(self, system: str, user: str, timeout_s: float) -> str:
        self.chamadas.append((system, user))
        if user.startswith("Pergunta:"):  # geração ou correção
            sql = _sql(self.proxima)
            self.proxima += 1
            return f"```sql\n{sql}\n```"
        return "Explicação."  # Explicador

    def correcoes(self) -> list[str]:
        return [u for _, u in self.chamadas if MARCA_CORRECAO in u]


class FakeExecutor:
    """Falha `falhas` vezes com ErroExecucao e depois devolve um resultado."""

    def __init__(self, falhas: int) -> None:
        self.falhas = falhas
        self.sqls: list[str] = []

    def executar(self, sql: str) -> ResultadoExecucao:
        self.sqls.append(sql)
        n = len(self.sqls)
        if n <= self.falhas:
            raise ErroExecucao(f"erro-{n}-boom")
        return ResultadoExecucao(colunas=["id"], linhas=[(n,)], truncado=False, limite=100)


def _esquema() -> SchemaInfo:
    return SchemaInfo(
        tabelas=[
            Tabela(
                "produtos",
                [Coluna("id", "INTEGER", pk=True), Coluna("nome", "TEXT")],
            )
        ]
    )


# Feature: text-to-sql-agent, Property 12: Autocorreção respeita o limite e para no primeiro sucesso
# **Validates: Requirements 5.1, 5.2, 5.4, 5.5**
@settings(max_examples=100, deadline=None)
@given(
    n=st.integers(min_value=1, max_value=10),
    falhas=st.integers(min_value=0, max_value=14),
    pergunta=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), max_codepoint=0x24F),
        min_size=1,
        max_size=40,
    ),
)
def test_autocorrecao_respeita_limite_e_para_no_sucesso(n: int, falhas: int, pergunta: str) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        cfg = Config(
            api_key="chave-secreta-xyz",
            model="m",
            max_correcoes=n,
            audit_path=str(tmp / "audit.jsonl"),
        )
        llm = FakeLlmClient()
        executor = FakeExecutor(falhas)
        resp = Agente(cfg, _esquema(), llm, executor).responder(pergunta)

        correcoes = llm.correcoes()
        if falhas <= n:
            # Sucesso após `falhas` correções; para na primeira execução bem-sucedida.
            assert len(correcoes) == falhas
            assert len(executor.sqls) == falhas + 1
            assert resp.status == STATUS_SUCESSO
            assert resp.erro is None
            assert resp.tentativas == falhas + 1
            assert resp.sql == _sql(falhas)
            assert resp.resultado is not None
            assert resp.resultado.linhas == [(falhas + 1,)]
        else:
            # Limite esgotado: exatamente `n` correções e erro final do último erro.
            assert len(correcoes) == n
            assert len(executor.sqls) == n + 1
            assert resp.status == STATUS_FALHA
            assert resp.etapa_falha == ETAPA_EXECUCAO
            assert resp.resultado is None
            assert resp.tentativas == n + 1
            assert f"erro-{n + 1}-boom" in (resp.erro or "")

        # Cada pedido de correção traz pergunta, SQL que falhou e o erro correspondente.
        for i, user in enumerate(correcoes):
            assert f"Pergunta: {pergunta}" in user
            assert _sql(i) in user
            assert f"Erro: erro-{i + 1}-boom" in user
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
