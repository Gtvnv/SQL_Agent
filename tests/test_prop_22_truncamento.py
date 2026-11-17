"""Property 22: Truncamento de textos respeita os limites e sinaliza."""

import pytest
from hypothesis import given, settings, strategies as st

from sql_agent.audit import LIMITE_PERGUNTA, LIMITE_SQL, truncar
from sql_agent.executor import ResultadoExecucao
from sql_agent.explainer import LIMITE_TEXTO, explicar
from tests.conftest import FakeLlmClient

# Feature: text-to-sql-agent, Property 22: Truncamento de textos respeita os limites e sinaliza
# **Validates: Requirements 1.1, 10.2**

_LIMITES = [4000, 10000, 1000]
_TEXTO = st.text(max_size=12000)


def test_limites_configurados():
    assert (LIMITE_PERGUNTA, LIMITE_SQL, LIMITE_TEXTO) == (4000, 10000, 1000)


@pytest.mark.parametrize("limite", _LIMITES)
@settings(max_examples=100, deadline=None)
@given(texto=_TEXTO)
def test_truncar_respeita_limite_e_sinaliza(limite, texto):
    saida, truncado = truncar(texto, limite)
    if len(texto) <= limite:
        assert saida == texto
        assert truncado is False
    else:
        assert saida == texto[:limite]
        assert len(saida) == limite
        assert truncado is True


@pytest.mark.parametrize("limite", _LIMITES)
@settings(max_examples=100, deadline=None)
@given(extra=st.integers(min_value=0, max_value=50), char=st.characters(blacklist_categories=("Cs",)))
def test_truncar_fronteira_do_limite(limite, extra, char):
    # Textos exatamente no limite e logo acima dele.
    texto = char * (limite + extra)
    saida, truncado = truncar(texto, limite)
    assert len(saida) == min(len(texto), limite)
    assert truncado is (extra > 0)


@settings(max_examples=100, deadline=None)
@given(
    base=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=3000),
    repeticoes=st.integers(min_value=1, max_value=3),
)
def test_explicador_limita_texto_a_1000_caracteres(base, repeticoes):
    texto = (base * repeticoes) + "x"
    llm = FakeLlmClient(respostas=[texto])
    resultado = ResultadoExecucao(colunas=["a"], linhas=[(1,)], truncado=False, limite=100)

    explicacao = explicar("pergunta", "SELECT 1", resultado, llm)

    assert explicacao is not None
    assert len(explicacao) <= 1000
    assert explicacao == texto.strip()[:1000]
    if len(texto.strip()) <= 1000:
        assert explicacao == texto.strip()
