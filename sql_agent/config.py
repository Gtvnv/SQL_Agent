"""Configuração do Agente: carregamento, validação e mascaramento de segredos."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

MASCARA = "***"

PADRAO_DB_PATH = "db/loja.sqlite"
PADRAO_AUDIT_PATH = "audit.jsonl"

# nome da variável -> (padrão, mínimo, máximo)
_FAIXAS: dict[str, tuple[int, int, int]] = {
    "MAX_CORRECOES": (3, 1, 10),
    "MAX_LINHAS": (100, 1, 10000),
    "QUERY_TIMEOUT_S": (10, 1, 300),
}

_INTEIRO = re.compile(r"[+-]?[0-9]+")


class ConfigError(Exception):
    """Configuração obrigatória ausente. A mensagem contém o nome da variável."""


@dataclass(frozen=True)
class Config:
    api_key: str = field(repr=False)
    model: str
    db_path: str = PADRAO_DB_PATH
    max_correcoes: int = 3
    max_linhas: int = 100
    timeout_consulta_s: int = 10
    audit_path: str = PADRAO_AUDIT_PATH
    avisos: list[str] = field(default_factory=list)


def mascarar(texto: str, api_key: str | None) -> str:
    """Substitui toda ocorrência da chave de API em `texto` por uma máscara."""
    if not api_key or not api_key.strip():
        return texto
    resultado = texto.replace(api_key, MASCARA)
    chave_limpa = api_key.strip()
    if chave_limpa != api_key:
        resultado = resultado.replace(chave_limpa, MASCARA)
    return resultado


def _valor(nome: str, env: Mapping[str, str], dotenv: Mapping[str, str]) -> str | None:
    """Valor da variável; o ambiente do processo prevalece sobre o `.env`."""
    if nome in env:
        return env[nome]
    return dotenv.get(nome)


def _inteiro_na_faixa(
    nome: str, bruto: str | None, avisos: list[str]
) -> int:
    padrao, minimo, maximo = _FAIXAS[nome]
    if bruto is None:
        return padrao
    texto = bruto.strip()
    if not _INTEIRO.fullmatch(texto):
        avisos.append(
            f"{nome}: valor inválido ignorado; usando o padrão {padrao}."
        )
        return padrao
    numero = int(texto)
    if not minimo <= numero <= maximo:
        avisos.append(
            f"{nome}: valor fora da faixa {minimo}..{maximo} ignorado; "
            f"usando o padrão {padrao}."
        )
        return padrao
    return numero


def _texto_ou_padrao(valor: str | None, padrao: str) -> str:
    if valor is None or not valor.strip():
        return padrao
    return valor.strip()


def carregar_config(env: Mapping[str, str], dotenv: Mapping[str, str]) -> Config:
    """Monta a Config. Valores de `env` têm precedência sobre `dotenv`."""
    api_key = _valor("LLM_API_KEY", env, dotenv)
    if api_key is None or not api_key.strip():
        raise ConfigError("LLM_API_KEY")

    model = _valor("LLM_MODEL", env, dotenv)
    if model is None or not model.strip():
        raise ConfigError("LLM_MODEL")

    avisos: list[str] = []
    valores = {
        nome: _inteiro_na_faixa(nome, _valor(nome, env, dotenv), avisos)
        for nome in _FAIXAS
    }

    return Config(
        api_key=api_key.strip(),
        model=model.strip(),
        db_path=_texto_ou_padrao(_valor("DB_PATH", env, dotenv), PADRAO_DB_PATH),
        max_correcoes=valores["MAX_CORRECOES"],
        max_linhas=valores["MAX_LINHAS"],
        timeout_consulta_s=valores["QUERY_TIMEOUT_S"],
        audit_path=_texto_ou_padrao(
            _valor("AUDIT_PATH", env, dotenv), PADRAO_AUDIT_PATH
        ),
        avisos=avisos,
    )
