"""Property 14: Renderização de tabela preserva colunas e linhas."""

from hypothesis import given, settings
from hypothesis import strategies as st

from sql_agent.cli import renderizar_tabela
from sql_agent.executor import ResultadoExecucao

# Nomes de colunas únicos, sem espaços (para permitir parse por célula).
_nome_coluna = st.from_regex(r"[A-Za-z][A-Za-z0-9_]{0,9}", fullmatch=True)
# Texto começa com letra para o tabulate não o converter em número.
_valor = st.one_of(
    st.integers(min_value=-10_000, max_value=10_000),
    st.from_regex(r"[A-Za-z][A-Za-z0-9]{0,9}", fullmatch=True),
)


@st.composite
def _resultados(draw) -> ResultadoExecucao:
    colunas = draw(st.lists(_nome_coluna, min_size=1, max_size=6, unique=True))
    linhas = draw(
        st.lists(
            st.tuples(*[_valor] * len(colunas)),
            min_size=1,
            max_size=20,
        )
    )
    return ResultadoExecucao(colunas=colunas, linhas=linhas, truncado=False, limite=100)


def _celulas(linha: str) -> list[str]:
    return [c.strip() for c in linha.strip().strip("|").split("|")]


# Feature: text-to-sql-agent, Property 14: Renderização de tabela preserva colunas e linhas
# **Validates: Requirements 6.1**
@settings(max_examples=100, deadline=None)
@given(resultado=_resultados())
def test_renderizacao_preserva_colunas_e_linhas(resultado: ResultadoExecucao) -> None:
    saida = renderizar_tabela(resultado)
    linhas_dados = [l for l in saida.splitlines() if l.startswith("|")]

    # Cabeçalho com os nomes das colunas na ordem retornada.
    assert _celulas(linhas_dados[0]) == resultado.colunas
    # Uma linha para cada registro, na mesma ordem.
    corpo = linhas_dados[1:]
    assert len(corpo) == len(resultado.linhas)
    for renderizada, registro in zip(corpo, resultado.linhas):
        assert _celulas(renderizada) == [str(v) for v in registro]
