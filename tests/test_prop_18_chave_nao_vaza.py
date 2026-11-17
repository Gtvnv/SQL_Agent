"""Property 18: A chave de API nunca aparece nas saídas."""

import json
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies as st

from sql_agent.audit import RegistroAuditoria, gravar
from sql_agent.config import MASCARA, ConfigError, carregar_config, mascarar

# Feature: text-to-sql-agent, Property 18: A chave de API nunca aparece nas saídas
# **Validates: Requirements 8.6**

# Chave com prefixo fixo e corpo longo: não colide com texto fixo das saídas.
chaves = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    min_size=16,
    max_size=64,
).map(lambda s: "sk-" + s)

textos = st.text(max_size=60)


def _embutir(prefixo: str, chave: str, sufixo: str) -> str:
    return f"{prefixo}{chave}{sufixo}"


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(chave=chaves, modelo=st.text(alphabet="abcdefgh-0123456789", min_size=1, max_size=20))
def test_repr_e_str_da_config_nao_contem_a_chave(chave, modelo):
    cfg = carregar_config({"LLM_API_KEY": chave, "LLM_MODEL": modelo}, {})
    assert chave not in repr(cfg)
    assert chave not in str(cfg)
    assert chave not in repr(cfg.avisos)


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(chave=chaves, prefixo=textos, sufixo=textos)
def test_mascarar_remove_a_chave_de_mensagens_de_erro(chave, prefixo, sufixo):
    mensagem = _embutir(prefixo, chave, sufixo)
    # Mensagem de exceção que carrega a chave (ex.: erro do provedor).
    mascarada = mascarar(str(RuntimeError(mensagem)), chave)
    assert chave not in mascarada
    assert MASCARA in mascarada


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(chave=chaves, espacos=st.text(alphabet=" \t", max_size=5), prefixo=textos)
def test_mascarar_remove_chave_com_espacos_nas_bordas(chave, espacos, prefixo):
    mascarada = mascarar(prefixo + chave + espacos, espacos + chave + espacos)
    assert chave not in mascarada


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(chave=chaves)
def test_mensagem_de_config_error_nao_contem_a_chave(chave):
    try:
        carregar_config({"LLM_API_KEY": chave}, {})  # modelo ausente
    except ConfigError as exc:
        assert chave not in str(exc)
        assert "LLM_MODEL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ConfigError esperado")


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(chave=chaves, pergunta=textos, sql=textos, motivo=textos)
def test_registros_de_auditoria_nao_contem_a_chave(chave, pergunta, sql, motivo):
    # O Agente mascara todo texto antes de montar o registro de auditoria.
    reg = RegistroAuditoria(
        pergunta=mascarar(_embutir(pergunta, chave, ""), chave),
        sql=mascarar(_embutir("SELECT '", chave, f"' {sql}"), chave),
        validacao="reprovada",
        tentativas=1,
        status="falha",
        motivo_reprovacao=mascarar(_embutir(motivo, chave, ""), chave),
    )
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "audit.jsonl"
        assert gravar(reg, str(caminho)) is True
        conteudo = caminho.read_text(encoding="utf-8")
    assert chave not in conteudo
    # Linha continua sendo JSON válido.
    json.loads(conteudo.split("\n")[0])
