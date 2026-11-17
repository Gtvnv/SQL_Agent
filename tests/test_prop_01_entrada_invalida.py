"""Property 1: Entrada inválida é rejeitada sem acionar o LLM."""

import shutil
import sqlite3
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from sql_agent.cli import LIMITE_ENTRADA, MSG_LONGA, MSG_VAZIA, main, validar_entrada

SQL_OK = "SELECT id, nome FROM produtos ORDER BY id"
BRANCOS = " \t\n\r\x0b\x0c\u00a0\u2003"

vazias = st.text(alphabet=BRANCOS, max_size=50)
longas = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=LIMITE_ENTRADA + 1,
    max_size=LIMITE_ENTRADA + 300,
)
validas = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc", "Zs", "Zl", "Zp")),
    min_size=1,
    max_size=LIMITE_ENTRADA,
).filter(lambda t: t.strip().lower() != "sair")


class _Llm:
    def __init__(self) -> None:
        self.chamadas: list[str] = []

    def completar(self, system: str, user: str, timeout_s: float) -> str:
        self.chamadas.append(user)
        return SQL_OK


def _executar_sessao(entradas: list[str]):
    """Roda main com as entradas; devolve (código, saídas, llm, chamadas por prompt)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "t.sqlite"
        c = sqlite3.connect(db)
        c.executescript(
            "CREATE TABLE produtos (id INTEGER PRIMARY KEY, nome TEXT);"
            "INSERT INTO produtos VALUES (1, 'a'), (2, 'b');"
        )
        c.commit()
        c.close()
        ctx = tmp / "ctx"
        ctx.mkdir()
        env = {
            "LLM_API_KEY": "chave-secreta-teste",
            "LLM_MODEL": "modelo-teste",
            "DB_PATH": str(db),
            "AUDIT_PATH": str(tmp / "audit.jsonl"),
        }
        llm = _Llm()
        fila = list(entradas)
        saidas: list[str] = []
        chamadas_no_prompt: list[int] = []

        def entrada(_prompt: str) -> str:
            chamadas_no_prompt.append(len(llm.chamadas))
            return fila.pop(0)

        codigo = main(
            env=env,
            entrada=entrada,
            saida=saidas.append,
            llm=llm,
            dotenv_path=str(tmp / "nao_existe.env"),
            dir_contexto=ctx,
        )
        return codigo, saidas, llm, chamadas_no_prompt
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Feature: text-to-sql-agent, Property 1: Entrada inválida é rejeitada sem acionar o LLM
# **Validates: Requirements 1.2, 1.5**
@settings(max_examples=100, deadline=None)
@given(texto=vazias)
def test_entrada_vazia_rejeitada_sem_llm(texto: str) -> None:
    assert validar_entrada(texto) == MSG_VAZIA
    codigo, saidas, llm, no_prompt = _executar_sessao([texto, "sair"])
    assert codigo == 0
    assert MSG_VAZIA in saidas
    assert llm.chamadas == []
    assert len(no_prompt) == 2  # sessão seguiu ativa após a rejeição


# Feature: text-to-sql-agent, Property 1: Entrada inválida é rejeitada sem acionar o LLM
# **Validates: Requirements 1.2, 1.5**
@settings(max_examples=100, deadline=None)
@given(texto=longas, valida=validas)
def test_entrada_longa_rejeitada_sem_llm_e_sessao_continua(texto: str, valida: str) -> None:
    assert validar_entrada(texto) == MSG_LONGA
    codigo, saidas, llm, no_prompt = _executar_sessao([texto, valida, "sair"])
    assert codigo == 0
    assert MSG_LONGA in saidas
    # Nenhuma chamada ao LLM até a pergunta válida seguinte ser lida.
    assert no_prompt[:2] == [0, 0]
    # A pergunta válida seguinte é processada (aciona o LLM).
    assert len(llm.chamadas) >= 1
    assert any("SQL gerada" in s for s in saidas)


# Feature: text-to-sql-agent, Property 1: Entrada inválida é rejeitada sem acionar o LLM
# **Validates: Requirements 1.2, 1.5**
@settings(max_examples=100, deadline=None)
@given(texto=validas)
def test_entrada_valida_aceita(texto: str) -> None:
    assert validar_entrada(texto) is None
    codigo, saidas, llm, _ = _executar_sessao([texto, "sair"])
    assert codigo == 0
    assert MSG_VAZIA not in saidas and MSG_LONGA not in saidas
    assert len(llm.chamadas) >= 1
