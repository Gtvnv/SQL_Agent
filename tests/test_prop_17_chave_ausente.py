"""Property 17: Chave de API ausente ou em branco impede a inicialização."""

import pytest
from hypothesis import given, settings, strategies as st

from sql_agent.config import ConfigError, carregar_config

# Feature: text-to-sql-agent, Property 17: Chave de API ausente ou em branco impede a inicialização
# **Validates: Requirements 8.4**

_BRANCOS = st.text(alphabet=" \t\n\r\x0b\x0c\u00a0\u2003", max_size=30)
_MODELO = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=20
)
_CHAVE_VALIDA = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=40
)
# Valor opcional da chave: ausente (None) ou em branco.
_AUSENTE_OU_BRANCA = st.one_of(st.none(), _BRANCOS)


def _montar(chave, modelo):
    mapa = {"LLM_MODEL": modelo}
    if chave is not None:
        mapa["LLM_API_KEY"] = chave
    return mapa


@settings(max_examples=100)
@given(chave_env=_AUSENTE_OU_BRANCA, chave_dotenv=_AUSENTE_OU_BRANCA, modelo=_MODELO)
def test_chave_ausente_ou_em_branco_gera_config_error(chave_env, chave_dotenv, modelo):
    env = _montar(chave_env, modelo)
    dotenv = _montar(chave_dotenv, modelo)
    with pytest.raises(ConfigError) as exc:
        carregar_config(env, dotenv)
    assert "LLM_API_KEY" in str(exc.value)


@settings(max_examples=100)
@given(chave_valida=_CHAVE_VALIDA, branca=_BRANCOS, modelo=_MODELO)
def test_chave_em_branco_no_ambiente_prevalece_sobre_dotenv_valido(
    chave_valida, branca, modelo
):
    env = _montar(branca, modelo)
    dotenv = _montar(chave_valida, modelo)
    with pytest.raises(ConfigError) as exc:
        carregar_config(env, dotenv)
    assert "LLM_API_KEY" in str(exc.value)
