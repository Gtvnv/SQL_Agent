"""Testes unitários da configuração (Requisitos 8.1, 8.5)."""

from __future__ import annotations

import pytest
from dotenv import dotenv_values

from sql_agent.config import Config, ConfigError, carregar_config


def test_modelo_ausente_gera_erro_com_nome_da_variavel():
    with pytest.raises(ConfigError) as exc:
        carregar_config({"LLM_API_KEY": "segredo"}, {})
    assert "LLM_MODEL" in str(exc.value)


@pytest.mark.parametrize("modelo", ["", "   "])
def test_modelo_vazio_ou_em_branco_gera_erro(modelo):
    with pytest.raises(ConfigError) as exc:
        carregar_config({"LLM_API_KEY": "segredo", "LLM_MODEL": modelo}, {})
    assert "LLM_MODEL" in str(exc.value)


def test_valores_validos_sao_mantidos():
    env = {
        "LLM_API_KEY": "segredo",
        "LLM_MODEL": "modelo-x",
        "DB_PATH": "meu/banco.sqlite",
        "MAX_CORRECOES": "5",
        "MAX_LINHAS": "250",
        "QUERY_TIMEOUT_S": "20",
        "AUDIT_PATH": "meu/audit.jsonl",
    }
    cfg = carregar_config(env, {})
    assert isinstance(cfg, Config)
    assert cfg.api_key == "segredo"
    assert cfg.model == "modelo-x"
    assert cfg.db_path == "meu/banco.sqlite"
    assert cfg.max_correcoes == 5
    assert cfg.max_linhas == 250
    assert cfg.timeout_consulta_s == 20
    assert cfg.audit_path == "meu/audit.jsonl"
    assert cfg.avisos == []


def test_leitura_do_dotenv_em_arquivo_temporario(tmp_path):
    arquivo = tmp_path / ".env"
    arquivo.write_text(
        "LLM_API_KEY=chave-do-arquivo\n"
        "LLM_MODEL=modelo-do-arquivo\n"
        "MAX_LINHAS=42\n",
        encoding="utf-8",
    )
    cfg = carregar_config({}, dotenv_values(arquivo))
    assert cfg.api_key == "chave-do-arquivo"
    assert cfg.model == "modelo-do-arquivo"
    assert cfg.max_linhas == 42
    assert cfg.max_correcoes == 3
    assert cfg.timeout_consulta_s == 10


def test_dotenv_sem_modelo_gera_erro(tmp_path):
    arquivo = tmp_path / ".env"
    arquivo.write_text("LLM_API_KEY=chave\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        carregar_config({}, dotenv_values(arquivo))
    assert "LLM_MODEL" in str(exc.value)
