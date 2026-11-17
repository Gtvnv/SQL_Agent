"""Testes de exemplo da Interface_CLI (sql_agent.cli.main)."""
from __future__ import annotations

from pathlib import Path

import pytest

from sql_agent import cli
from tests.conftest import FakeLlmClient

# **Validates: Requirements 1.3, 1.4, 6.2, 6.4, 6.7, 8.4**

SQL_PRODUTOS = "```sql\nSELECT nome FROM produtos ORDER BY id\n```"
SQL_VAZIO = "```sql\nSELECT nome FROM produtos WHERE id = 999\n```"


class Entradas:
    """Entrada injetada: devolve as linhas em ordem e depois `sair`."""

    def __init__(self, *linhas: str) -> None:
        self._linhas = list(linhas) + ["sair"]
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._linhas.pop(0)


def _executar(tmp_path: Path, db_path: Path, llm, entradas, extra_env=None):
    saidas: list[str] = []
    env = {
        "LLM_API_KEY": "chave-secreta-xyz",
        "LLM_MODEL": "modelo-teste",
        "DB_PATH": str(db_path),
        "AUDIT_PATH": str(tmp_path / "audit.jsonl"),
    }
    env.update(extra_env or {})
    ctx = tmp_path / "ctx"
    ctx.mkdir(exist_ok=True)
    codigo = cli.main(
        env=env,
        entrada=entradas,
        saida=saidas.append,
        llm=llm,
        dotenv_path=tmp_path / "inexistente.env",
        dir_contexto=ctx,
    )
    return codigo, "\n".join(saidas)


def test_comando_sair_retorna_zero_sem_chamar_llm(tmp_path, db_path):
    llm = FakeLlmClient()
    codigo, _ = _executar(tmp_path, db_path, llm, Entradas())
    assert codigo == 0
    assert llm.chamadas == []


def test_varias_perguntas_na_mesma_sessao(tmp_path, db_path):
    llm = FakeLlmClient(respostas=[SQL_PRODUTOS, "Lista os produtos.", SQL_PRODUTOS, "De novo."])
    entradas = Entradas("quais produtos?", "e agora?")
    codigo, saida = _executar(tmp_path, db_path, llm, entradas)

    assert codigo == 0
    assert len(entradas.prompts) == 3  # duas perguntas + sair
    assert saida.count("SQL gerada:") == 2
    assert "Dom Casmurro" in saida
    assert "Explicação: Lista os produtos." in saida
    assert "Explicação: De novo." in saida


def test_inicializacao_sem_chave_api_falha_sem_llm_nem_banco(tmp_path, db_path, monkeypatch):
    abertura: list[object] = []
    monkeypatch.setattr(cli, "_abrir_banco", lambda *a, **k: abertura.append(a))
    llm = FakeLlmClient()
    entradas = Entradas("nunca lida")

    codigo, saida = _executar(tmp_path, db_path, llm, entradas, extra_env={"LLM_API_KEY": ""})

    assert codigo != 0
    assert "LLM_API_KEY" in saida
    assert llm.chamadas == []
    assert abertura == []
    assert entradas.prompts == []


def test_resultado_sem_linhas_exibe_mensagem(tmp_path, db_path):
    llm = FakeLlmClient(respostas=[SQL_VAZIO, "Nada encontrado."])
    _, saida = _executar(tmp_path, db_path, llm, Entradas("produto 999?"))
    assert cli.MSG_SEM_REGISTROS in saida


def test_truncamento_exibe_aviso_com_limite(tmp_path, db_path):
    llm = FakeLlmClient(respostas=[SQL_PRODUTOS, "Lista."])
    _, saida = _executar(
        tmp_path, db_path, llm, Entradas("quais produtos?"), extra_env={"MAX_LINHAS": "1"}
    )
    assert cli.mensagem_truncamento(1) in saida
    assert "MAX_LINHAS=1" in saida
    assert "Dom Casmurro" in saida
    assert "Zelda" not in saida


def test_explicacao_indisponivel_exibe_mensagem(tmp_path, db_path):
    llm = FakeLlmClient(respostas=[SQL_PRODUTOS, ""])
    _, saida = _executar(tmp_path, db_path, llm, Entradas("quais produtos?"))
    assert "Dom Casmurro" in saida
    assert cli.MSG_SEM_EXPLICACAO in saida
    assert "Explicação:" not in saida


@pytest.mark.parametrize("texto", ["", "   ", "x" * (cli.LIMITE_ENTRADA + 1)])
def test_entrada_invalida_nao_chama_llm(tmp_path, db_path, texto):
    llm = FakeLlmClient()
    codigo, saida = _executar(tmp_path, db_path, llm, Entradas(texto))
    assert codigo == 0
    assert "Entrada inválida" in saida
    assert llm.chamadas == []
