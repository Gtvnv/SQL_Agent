"""Feature: text-to-sql-agent, Property 13: Configuração numérica inválida usa o padrão

**Validates: Requirements 5.3, 6.3, 6.5**
"""

import re

from hypothesis import given, settings, strategies as st

from sql_agent.config import carregar_config

# nome da variável -> (atributo da Config, padrão, mínimo, máximo)
VARIAVEIS = {
    "MAX_CORRECOES": ("max_correcoes", 3, 1, 10),
    "MAX_LINHAS": ("max_linhas", 100, 1, 10000),
    "QUERY_TIMEOUT_S": ("timeout_consulta_s", 10, 1, 300),
}

_INTEIRO = re.compile(r"[+-]?[0-9]+")
_BASE = {"LLM_API_KEY": "chave-de-teste", "LLM_MODEL": "modelo-de-teste"}


def _nao_inteiro(texto: str) -> bool:
    return _INTEIRO.fullmatch(texto.strip()) is None


nomes = st.sampled_from(sorted(VARIAVEIS))
textos_invalidos = st.text(max_size=20).filter(_nao_inteiro)


@st.composite
def valor_invalido(draw, nome):
    _, _, minimo, maximo = VARIAVEIS[nome]
    return draw(
        st.one_of(
            textos_invalidos,
            st.integers(max_value=minimo - 1).map(str),
            st.integers(min_value=maximo + 1).map(str),
        )
    )


@st.composite
def nome_e_valor_invalido(draw):
    nome = draw(nomes)
    return nome, draw(valor_invalido(nome))


@st.composite
def nome_e_valor_valido(draw):
    nome = draw(nomes)
    _, _, minimo, maximo = VARIAVEIS[nome]
    return nome, draw(st.integers(min_value=minimo, max_value=maximo))


@settings(max_examples=100)
@given(par=nome_e_valor_invalido(), no_dotenv=st.booleans())
def test_valor_invalido_usa_padrao_e_avisa(par, no_dotenv):
    nome, bruto = par
    env, dotenv = dict(_BASE), {}
    (dotenv if no_dotenv else env)[nome] = bruto

    config = carregar_config(env, dotenv)

    # a variável inválida e as demais (ausentes) ficam no padrão
    for attr, padrao, _, _ in VARIAVEIS.values():
        assert getattr(config, attr) == padrao
    assert any(a.startswith(nome) for a in config.avisos)
    assert len(config.avisos) == 1


@settings(max_examples=100)
@given(par=nome_e_valor_valido(), no_dotenv=st.booleans())
def test_valor_valido_e_mantido_sem_aviso(par, no_dotenv):
    nome, numero = par
    env, dotenv = dict(_BASE), {}
    (dotenv if no_dotenv else env)[nome] = str(numero)

    config = carregar_config(env, dotenv)

    assert getattr(config, VARIAVEIS[nome][0]) == numero
    assert config.avisos == []
