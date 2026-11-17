"""Property 16: Variável de ambiente prevalece sobre o `.env`."""

from hypothesis import given, settings, strategies as st

from sql_agent.config import carregar_config

# Feature: text-to-sql-agent, Property 16: Variável de ambiente prevalece sobre o `.env`
# **Validates: Requirements 8.2**

_texto = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), max_codepoint=127),
    min_size=1,
    max_size=20,
)

_faixas = {
    "MAX_CORRECOES": (1, 10),
    "MAX_LINHAS": (1, 10000),
    "QUERY_TIMEOUT_S": (1, 300),
}


@st.composite
def _env_e_dotenv(draw):
    """Gera `env` e `dotenv` com valores válidos para um subconjunto comum de variáveis."""
    env: dict[str, str] = {}
    dotenv: dict[str, str] = {}
    for nome in ("LLM_API_KEY", "LLM_MODEL", "DB_PATH", "AUDIT_PATH"):
        env[nome] = draw(_texto)
        dotenv[nome] = draw(_texto)
    for nome, (lo, hi) in _faixas.items():
        env[nome] = str(draw(st.integers(lo, hi)))
        dotenv[nome] = str(draw(st.integers(lo, hi)))
    return env, dotenv


@settings(max_examples=100, deadline=None)
@given(_env_e_dotenv())
def test_ambiente_prevalece_sobre_dotenv(par):
    env, dotenv = par
    cfg = carregar_config(env, dotenv)

    assert cfg.api_key == env["LLM_API_KEY"]
    assert cfg.model == env["LLM_MODEL"]
    assert cfg.db_path == env["DB_PATH"]
    assert cfg.audit_path == env["AUDIT_PATH"]
    assert cfg.max_correcoes == int(env["MAX_CORRECOES"])
    assert cfg.max_linhas == int(env["MAX_LINHAS"])
    assert cfg.timeout_consulta_s == int(env["QUERY_TIMEOUT_S"])
    assert cfg.avisos == []


@settings(max_examples=100, deadline=None)
@given(_env_e_dotenv(), st.sets(st.sampled_from(sorted(_faixas) + ["LLM_MODEL", "DB_PATH"])))
def test_dotenv_so_vale_quando_ambiente_nao_define(par, ausentes):
    env, dotenv = par
    env = {k: v for k, v in env.items() if k not in ausentes}
    cfg = carregar_config(env, dotenv)

    efetivo = {**dotenv, **env}
    assert cfg.model == efetivo["LLM_MODEL"]
    assert cfg.db_path == efetivo["DB_PATH"]
    assert cfg.max_linhas == int(efetivo["MAX_LINHAS"])
