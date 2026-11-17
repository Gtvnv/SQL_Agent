"""Property 21: Uma pergunta gera exatamente um registro de auditoria."""

import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hypothesis import given, settings, strategies as st

from sql_agent.agent import STATUS_FALHA, STATUS_SUCESSO, Agente
from sql_agent.config import Config
from sql_agent.executor import ErroExecucao, ResultadoExecucao, TempoExcedido
from sql_agent.llm import LlmLimiteError, LlmRedeError, LlmTimeout
from sql_agent.schema import Coluna, SchemaInfo, Tabela
from tests.conftest import FakeLlmClient

# Feature: text-to-sql-agent, Property 21: Uma pergunta gera exatamente um registro de auditoria
# **Validates: Requirements 10.1, 10.3**

CAMPOS = {
    "timestamp_utc",
    "pergunta",
    "pergunta_truncada",
    "sql",
    "sql_truncada",
    "validacao",
    "motivo_reprovacao",
    "tentativas",
    "status",
}
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

ESQUEMA = SchemaInfo(
    tabelas=[
        Tabela(
            "produtos",
            [Coluna("id", "INTEGER", pk=True), Coluna("nome", "TEXT"), Coluna("preco", "REAL")],
        )
    ]
)
SQL_OK = "SELECT nome FROM produtos"
SQL_CORRIGIDA = "SELECT id FROM produtos"


class FakeExecutor:
    """Falha `falhas` vezes com ErroExecucao (ou erro dado) e depois tem sucesso."""

    def __init__(self, falhas: int = 0, erro: Exception | None = None) -> None:
        self.falhas = falhas
        self.erro = erro
        self.chamadas = 0

    def executar(self, sql: str) -> ResultadoExecucao:
        self.chamadas += 1
        if self.erro is not None:
            raise self.erro
        if self.chamadas <= self.falhas:
            raise ErroExecucao("no such column: x")
        return ResultadoExecucao(colunas=["nome"], linhas=[("a",)], truncado=False, limite=100)


def _cenario(nome: str, falhas: int):
    """Devolve (respostas do LLM, executor) para cada tipo de desfecho."""
    if nome == "sucesso":
        return [SQL_OK, "Lista nomes."], FakeExecutor()
    if nome == "sucesso_apos_correcao":
        return [SQL_OK] + [SQL_CORRIGIDA] * falhas + ["Explicação."], FakeExecutor(falhas=falhas)
    if nome == "erro_execucao_persistente":
        return [SQL_OK, SQL_CORRIGIDA], FakeExecutor(falhas=99)
    if nome == "tempo_excedido":
        return [SQL_OK], FakeExecutor(erro=TempoExcedido("tempo limite"))
    if nome == "validacao_reprovada":
        return ["DROP TABLE produtos"], FakeExecutor()
    if nome == "tabela_inexistente":
        return ["SELECT * FROM fantasma"], FakeExecutor()
    if nome == "nao_disponivel":
        return ["NAO_DISPONIVEL"], FakeExecutor()
    if nome == "resposta_vazia":
        return [""], FakeExecutor()
    if nome == "duas_instrucoes":
        return ["SELECT 1; SELECT 2"], FakeExecutor()
    if nome == "llm_rede":
        return [LlmRedeError("rede")], FakeExecutor()
    if nome == "llm_limite":
        return [LlmLimiteError("limite")], FakeExecutor()
    if nome == "llm_timeout":
        return [LlmTimeout("timeout")], FakeExecutor()
    if nome == "llm_rede_na_correcao":
        return [SQL_OK, LlmRedeError("rede")], FakeExecutor(falhas=99)
    raise AssertionError(nome)


CENARIOS = [
    "sucesso",
    "sucesso_apos_correcao",
    "erro_execucao_persistente",
    "tempo_excedido",
    "validacao_reprovada",
    "tabela_inexistente",
    "nao_disponivel",
    "resposta_vazia",
    "duas_instrucoes",
    "llm_rede",
    "llm_limite",
    "llm_timeout",
    "llm_rede_na_correcao",
]
SEM_SQL = {"nao_disponivel", "resposta_vazia", "duas_instrucoes", "llm_rede", "llm_limite", "llm_timeout"}


def _ler_linhas(caminho: Path) -> list[str]:
    if not caminho.exists():
        return []
    texto = caminho.read_text(encoding="utf-8")
    return [l for l in texto.split("\n") if l != ""]


@settings(max_examples=100, deadline=None)
@given(
    cenario=st.sampled_from(CENARIOS),
    falhas=st.integers(min_value=1, max_value=3),
    pergunta=st.text(min_size=1, max_size=300),
    perguntas_anteriores=st.integers(min_value=0, max_value=2),
)
def test_uma_pergunta_gera_exatamente_um_registro(cenario, falhas, pergunta, perguntas_anteriores):
    respostas, executor = _cenario(cenario, falhas)
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "auditoria.jsonl"
        config = Config(api_key="sk-segredo-123", model="m", audit_path=str(caminho))

        # Registros pré-existentes: só pode surgir exatamente uma linha nova.
        previas = [json.dumps({"previo": i}) for i in range(perguntas_anteriores)]
        if previas:
            caminho.write_text("\n".join(previas) + "\n", encoding="utf-8")
        antes = _ler_linhas(caminho)

        agente = Agente(config, ESQUEMA, FakeLlmClient(respostas=respostas), executor)
        inicio = datetime.now(timezone.utc).replace(microsecond=0)
        resp = agente.responder(pergunta)
        fim = datetime.now(timezone.utc)

        depois = _ler_linhas(caminho)
        assert len(depois) == len(antes) + 1
        assert depois[: len(antes)] == antes
        assert resp.auditado is True

        reg = json.loads(depois[-1])
        assert set(reg) == CAMPOS

        # Timestamp UTC com precisão de segundos.
        assert _TS.match(reg["timestamp_utc"])
        ts = datetime.strptime(reg["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert inicio - timedelta(seconds=1) <= ts <= fim + timedelta(seconds=1)

        assert reg["pergunta"] == pergunta
        assert reg["pergunta_truncada"] is False
        assert isinstance(reg["sql"], str)
        assert isinstance(reg["sql_truncada"], bool)
        assert reg["validacao"] in ("aprovada", "reprovada")
        assert isinstance(reg["tentativas"], int) and 1 <= reg["tentativas"] <= 3
        assert reg["status"] in (STATUS_SUCESSO, STATUS_FALHA)
        assert reg["status"] == resp.status

        if cenario in SEM_SQL:
            assert reg["sql"] == ""
            assert reg["status"] == STATUS_FALHA
        if cenario in ("sucesso", "sucesso_apos_correcao"):
            assert reg["status"] == STATUS_SUCESSO
            assert reg["validacao"] == "aprovada"
            assert reg["sql"] != ""
        if cenario in ("validacao_reprovada", "tabela_inexistente"):
            assert reg["status"] == STATUS_FALHA
            assert reg["validacao"] == "reprovada"
            assert reg["motivo_reprovacao"]
        # A chave de API nunca chega ao log.
        assert "sk-segredo-123" not in depois[-1]
