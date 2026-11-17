"""Testes unitários da extração de SQL e de gerar/corrigir."""
from __future__ import annotations

import pytest

from sql_agent.generator import (
    NAO_DISPONIVEL,
    GeracaoError,
    corrigir,
    extract_sql,
    format_sql_block,
    gerar,
)
from sql_agent.llm import LlmTimeout
from sql_agent.schema import extrair_esquema
from tests.conftest import FakeLlmClient

SQL = "SELECT nome FROM produtos"


# --- extract_sql: sucesso (3.3) ---

def test_extrai_bloco_com_sql():
    assert extract_sql(f"Aqui:\n```sql\n{SQL}\n```") == SQL


def test_extrai_bloco_sem_sql():
    assert extract_sql(f"```\n{SQL}\n```") == SQL


def test_extrai_resposta_sem_bloco():
    assert extract_sql(f"  {SQL}  ") == SQL


def test_ignora_ponto_e_virgula_final():
    assert extract_sql(f"```sql\n{SQL};\n```") == f"{SQL};"


def test_aceita_with():
    sql = "WITH t AS (SELECT 1 AS x) SELECT x FROM t"
    assert extract_sql(format_sql_block(sql)) == sql


# --- extract_sql: falha (3.4, 3.5) ---

@pytest.mark.parametrize("resposta", ["", "   \n", None])
def test_resposta_vazia_falha(resposta):
    with pytest.raises(GeracaoError):
        extract_sql(resposta)


def test_texto_sem_sql_falha():
    with pytest.raises(GeracaoError):
        extract_sql("Não sei responder isso.")


def test_duas_instrucoes_falha():
    with pytest.raises(GeracaoError):
        extract_sql("SELECT 1; SELECT 2")


def test_duas_instrucoes_em_bloco_falha():
    with pytest.raises(GeracaoError):
        extract_sql("```sql\nSELECT 1;\nSELECT 2;\n```")


# --- NAO_DISPONIVEL (3.6) ---

@pytest.mark.parametrize(
    "resposta", [NAO_DISPONIVEL, f"  {NAO_DISPONIVEL}\n", f"```\n{NAO_DISPONIVEL}\n```"]
)
def test_nao_disponivel(resposta):
    assert extract_sql(resposta) == NAO_DISPONIVEL


# --- gerar / corrigir com FakeLlmClient ---

def test_gerar_devolve_sql_e_envia_pergunta_e_esquema(conn):
    esquema = extrair_esquema(conn, {})
    llm = FakeLlmClient(respostas=[format_sql_block(SQL)])
    assert gerar("Quais produtos?", esquema, llm) == SQL
    system, user, _ = llm.chamadas[0]
    assert "Quais produtos?" in user
    assert "produtos" in system and "categorias" in system
    assert NAO_DISPONIVEL in system


def test_gerar_nao_disponivel(conn):
    llm = FakeLlmClient(respostas=[NAO_DISPONIVEL])
    assert gerar("Qual o clima?", extrair_esquema(conn, {}), llm) == NAO_DISPONIVEL


def test_gerar_resposta_invalida_levanta(conn):
    llm = FakeLlmClient(respostas=[""])
    with pytest.raises(GeracaoError):
        gerar("x", extrair_esquema(conn, {}), llm)


def test_gerar_propaga_erro_do_llm(conn):
    llm = FakeLlmClient(respostas=[LlmTimeout("lento")])
    with pytest.raises(LlmTimeout):
        gerar("x", extrair_esquema(conn, {}), llm)


def test_corrigir_envia_sql_e_erro(conn):
    nova = "SELECT nome FROM produtos WHERE preco > 0"
    llm = FakeLlmClient(respostas=[format_sql_block(nova)])
    out = corrigir("Quais?", "SELECT x FROM produtos", "no such column: x",
                   extrair_esquema(conn, {}), llm)
    assert out == nova
    _, user, _ = llm.chamadas[0]
    assert "SELECT x FROM produtos" in user and "no such column: x" in user


def test_corrigir_duas_instrucoes_levanta(conn):
    llm = FakeLlmClient(respostas=["SELECT 1; SELECT 2"])
    with pytest.raises(GeracaoError):
        corrigir("q", "SELECT 1", "erro", extrair_esquema(conn, {}), llm)
