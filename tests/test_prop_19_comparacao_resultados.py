"""Property 19: Comparação de resultados na avaliação."""

from collections import Counter

from hypothesis import given, settings, strategies as st

from sql_agent.evaluation import comparar_resultados

# Feature: text-to-sql-agent, Property 19: Comparação de resultados na avaliação
# **Validates: Requirements 9.2**

_VALOR = st.one_of(
    st.none(),
    st.integers(min_value=-5, max_value=5),
    st.text(alphabet="abc", max_size=2),
)
_LINHA = st.tuples(_VALOR, _VALOR)
_LINHAS = st.lists(_LINHA, max_size=8)


@settings(max_examples=100, deadline=None)
@given(a=_LINHAS, b=_LINHAS, ordenado=st.booleans())
def test_comparacao_conforme_definicao(a, b, ordenado):
    esperado = (a == b) if ordenado else (Counter(a) == Counter(b))
    assert comparar_resultados(a, b, ordenado) is esperado


@settings(max_examples=100, deadline=None)
@given(linhas=_LINHAS, dados=st.data())
def test_qualquer_permutacao_igual_sem_order_by(linhas, dados):
    permutada = dados.draw(st.permutations(linhas))
    assert comparar_resultados(permutada, linhas, ordenado=False)


@settings(max_examples=100, deadline=None)
@given(linhas=_LINHAS, dados=st.data())
def test_com_order_by_so_igual_na_mesma_ordem(linhas, dados):
    permutada = dados.draw(st.permutations(linhas))
    assert comparar_resultados(permutada, linhas, ordenado=True) == (
        list(permutada) == list(linhas)
    )
    assert comparar_resultados(linhas, linhas, ordenado=True)


@settings(max_examples=100, deadline=None)
@given(linhas=_LINHAS, extra=_LINHA)
def test_multiplicidade_importa(linhas, extra):
    assert not comparar_resultados(linhas + [extra], linhas, ordenado=False)
