"""Testes unitários do Explicador e do Log_Auditoria (Requisitos 6.7, 10.4, 10.5)."""
from __future__ import annotations

import builtins
import json
import time

from sql_agent import audit
from sql_agent.audit import RegistroAuditoria, gravar
from sql_agent.executor import ResultadoExecucao
from sql_agent.explainer import LIMITE_TEXTO, explicar
from sql_agent.llm import LlmTimeout, LlmRedeError


def _resultado() -> ResultadoExecucao:
    return ResultadoExecucao(colunas=["nome"], linhas=[("a",), ("b",)], truncado=False, limite=100)


def _registro() -> RegistroAuditoria:
    return RegistroAuditoria(
        pergunta="Quantos produtos?",
        sql="SELECT COUNT(*) FROM produtos",
        validacao="aprovada",
        tentativas=1,
        status="sucesso",
    )


# ---------------------------------------------------------------- Explicador

def test_explicador_devolve_none_em_falha_de_rede(fake_llm):
    fake_llm.respostas = [LlmRedeError("falha")]
    assert explicar("p", "SELECT 1", _resultado(), fake_llm) is None


def test_explicador_devolve_none_em_timeout(fake_llm):
    fake_llm.respostas = [LlmTimeout("tempo")]
    assert explicar("p", "SELECT 1", _resultado(), fake_llm) is None


def test_explicador_limita_texto_a_1000_caracteres(fake_llm):
    fake_llm.respostas = ["x" * 5000]
    texto = explicar("p", "SELECT 1", _resultado(), fake_llm)
    assert texto is not None
    assert len(texto) == LIMITE_TEXTO == 1000


def test_explicador_devolve_texto_curto_inalterado(fake_llm):
    fake_llm.respostas = ["Retorna 2 linhas."]
    assert explicar("p", "SELECT 1", _resultado(), fake_llm) == "Retorna 2 linhas."
    assert fake_llm.chamadas[0][2] == 15.0


# ------------------------------------------------------------------ Auditoria

def test_gravar_devolve_false_com_caminho_invalido(tmp_path):
    caminho = tmp_path / "inexistente" / "audit.jsonl"
    assert gravar(_registro(), str(caminho)) is False


def test_gravar_normal_em_ate_2s_com_campos_exigidos(tmp_path):
    caminho = tmp_path / "audit.jsonl"
    inicio = time.monotonic()
    ok = gravar(_registro(), str(caminho))
    duracao = time.monotonic() - inicio

    assert ok is True
    assert duracao <= 2.0
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 1
    dados = json.loads(linhas[0])
    for campo in (
        "timestamp_utc", "pergunta", "pergunta_truncada", "sql", "sql_truncada",
        "validacao", "motivo_reprovacao", "tentativas", "status",
    ):
        assert campo in dados
    assert dados["pergunta"] == "Quantos produtos?"
    assert dados["validacao"] == "aprovada"
    assert dados["tentativas"] == 1
    assert dados["status"] == "sucesso"


def test_gravar_devolve_false_quando_excede_2s(tmp_path, monkeypatch):
    caminho = tmp_path / "audit.jsonl"
    open_real = builtins.open

    def open_lento(*args, **kwargs):
        time.sleep(2.5)
        return open_real(*args, **kwargs)

    monkeypatch.setattr(audit, "open", open_lento, raising=False)
    inicio = time.monotonic()
    ok = gravar(_registro(), str(caminho))
    duracao = time.monotonic() - inicio

    assert ok is False
    assert duracao < 2.4
