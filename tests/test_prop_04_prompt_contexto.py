"""Property 4: O prompt contém todo o contexto configurado."""

import sqlite3

from hypothesis import given, settings, strategies as st

from sql_agent.generator import gerar, montar_prompt_sistema
from sql_agent.schema import LIMITE_DESCRICAO, extrair_esquema

# Feature: text-to-sql-agent, Property 4: O prompt contém todo o contexto configurado
# **Validates: Requirements 2.2, 2.3, 3.7**

_SUFIXO = st.text(alphabet="abcdefghij", min_size=1, max_size=6)
# Descrições de 1 a 600 caracteres (algumas excedem o limite de 500), sem quebras de linha.
_DESCRICAO = st.text(alphabet="abcdefg hijk.", min_size=1, max_size=600)
_TEXTO_EXEMPLO = st.text(alphabet="abcdefghij ,?", min_size=1, max_size=40).map(str.strip).filter(bool)


@st.composite
def _cenario(draw):
    nomes_tab = draw(st.lists(_SUFIXO, min_size=1, max_size=4, unique=True))
    esquema = {}
    descricoes = {}
    for nome in nomes_tab:
        tab = f"t_{nome}"
        cols = [f"c_{c}" for c in draw(st.lists(_SUFIXO, min_size=1, max_size=4, unique=True))]
        esquema[tab] = cols
        escolhidas = draw(st.lists(st.sampled_from(cols), max_size=len(cols), unique=True))
        if escolhidas:
            descricoes[tab] = {c: draw(_DESCRICAO) for c in escolhidas}
    exemplos = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "pergunta": _TEXTO_EXEMPLO,
                    "sql": _TEXTO_EXEMPLO.map(lambda s: f"SELECT '{s}'"),
                }
            ),
            max_size=10,
        )
    )
    return esquema, descricoes, exemplos


def _extrair(esquema, descricoes):
    conn = sqlite3.connect(":memory:")
    try:
        for tab, cols in esquema.items():
            defs = ", ".join(f'"{c}" TEXT' for c in cols)
            conn.execute(f'CREATE TABLE "{tab}" ({defs})')
        return extrair_esquema(conn, descricoes)
    finally:
        conn.close()


class _ClienteCapturaPrompt:
    def __init__(self):
        self.system = None

    def completar(self, system, user, timeout_s):
        self.system = system
        return "SELECT 1"


@settings(max_examples=100, deadline=None)
@given(dados=_cenario())
def test_prompt_contem_todo_o_contexto(dados):
    esquema, descricoes, exemplos = dados
    info = _extrair(esquema, descricoes)

    prompt = montar_prompt_sistema(info, exemplos)

    for tab, cols in esquema.items():
        assert tab in prompt
        for col in cols:
            assert col in prompt

    for cols in descricoes.values():
        for texto in cols.values():
            assert texto[:LIMITE_DESCRICAO] in prompt
            if len(texto) > LIMITE_DESCRICAO:
                assert texto[: LIMITE_DESCRICAO + 1] not in prompt

    for ex in exemplos:
        assert ex["pergunta"] in prompt
        assert ex["sql"] in prompt

    # `gerar` envia o mesmo prompt de sistema ao LLM.
    cliente = _ClienteCapturaPrompt()
    gerar("qualquer pergunta", info, cliente, exemplos)
    assert cliente.system == prompt
