"""Interface_CLI: laço de perguntas em linguagem natural no terminal."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml
from dotenv import dotenv_values
from tabulate import tabulate

from sql_agent.agent import STATUS_SUCESSO, Agente
from sql_agent.config import Config, ConfigError, carregar_config, mascarar
from sql_agent.executor import ExecutorSql, ResultadoExecucao
from sql_agent.llm import HttpLlmClient, LlmClient
from sql_agent.schema import extrair_esquema_ou_sair

LIMITE_ENTRADA = 1000
COMANDO_SAIR = "sair"
PROMPT = "pergunta> "

MSG_VAZIA = "Entrada inválida: digite uma pergunta (não pode ser vazia)."
MSG_LONGA = f"Entrada inválida: a pergunta excede {LIMITE_ENTRADA} caracteres."
MSG_SEM_REGISTROS = "Nenhum registro encontrado."
MSG_SEM_EXPLICACAO = "explicação não disponível"

_DIR_DB = Path(__file__).resolve().parent.parent / "db"


def validar_entrada(texto: str) -> str | None:
    """Devolve a mensagem de erro para entrada inválida, ou None se válida."""
    if not texto or not texto.strip():
        return MSG_VAZIA
    if len(texto) > LIMITE_ENTRADA:
        return MSG_LONGA
    return None


def mensagem_truncamento(limite: int) -> str:
    return (
        f"Aviso: resultado truncado; exibindo apenas as primeiras {limite} linhas "
        f"(limite MAX_LINHAS={limite})."
    )


def renderizar_tabela(resultado: ResultadoExecucao) -> str:
    """Tabela com todas as colunas e linhas do resultado (ou aviso de vazio)."""
    if not resultado.linhas:
        return MSG_SEM_REGISTROS
    return tabulate(resultado.linhas, headers=resultado.colunas, tablefmt="grid")


def _carregar_yaml(caminho: Path, esperado: type) -> Any:
    """Lê um YAML opcional; arquivo ausente ou inválido vira vazio."""
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return esperado()
    return dados if isinstance(dados, esperado) else esperado()


def _carregar_exemplos(dir_contexto: Path) -> list[dict]:
    itens = _carregar_yaml(dir_contexto / "few_shot.yaml", list)
    return [
        i for i in itens
        if isinstance(i, dict) and "pergunta" in i and "sql" in i
    ]


def _abrir_banco(config: Config, saida: Callable[[str], Any]) -> sqlite3.Connection | None:
    try:
        uri = f"{Path(config.db_path).resolve().as_uri()}?mode=ro"
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        saida(f"Erro ao acessar o banco de dados: {exc}")
        return None


def _exibir_resposta(resp, config: Config, saida: Callable[[str], Any]) -> None:
    if resp.sql:
        saida(f"SQL gerada:\n{resp.sql}")
    if resp.status == STATUS_SUCESSO and resp.resultado is not None:
        saida(renderizar_tabela(resp.resultado))
        if resp.resultado.truncado:
            saida(mensagem_truncamento(resp.resultado.limite))
        saida(f"Explicação: {resp.explicacao}" if resp.explicacao else MSG_SEM_EXPLICACAO)
    else:
        saida(mascarar(resp.erro or "Não foi possível responder à pergunta.", config.api_key))
    for aviso in resp.avisos:
        saida(aviso)


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    entrada: Callable[[str], str] = input,
    saida: Callable[[str], Any] = print,
    llm: LlmClient | None = None,
    dotenv_path: str | os.PathLike = ".env",
    dir_contexto: str | os.PathLike | None = None,
) -> int:
    """Executa a CLI. Retorna o código de saída do processo."""
    ambiente = os.environ if env is None else env
    try:
        config = carregar_config(ambiente, dotenv_values(dotenv_path))
    except ConfigError as exc:
        saida(f"Erro de configuração: variável obrigatória ausente ou vazia: {exc}")
        return 2

    for aviso in config.avisos:
        saida(f"Aviso de configuração: {aviso}")

    contexto = Path(dir_contexto) if dir_contexto is not None else _DIR_DB
    descricoes = _carregar_yaml(contexto / "schema_descriptions.yaml", dict)
    exemplos = _carregar_exemplos(contexto)

    conn = _abrir_banco(config, saida)
    if conn is None:
        return 1
    try:
        try:
            esquema = extrair_esquema_ou_sair(conn, descricoes)
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) and exc.code else 1
    finally:
        conn.close()
    for aviso in esquema.avisos:
        saida(f"Aviso: {aviso}")

    cliente = llm if llm is not None else HttpLlmClient(config)
    executor = ExecutorSql(config.db_path, config.max_linhas, config.timeout_consulta_s)
    agente = Agente(config, esquema, cliente, executor, exemplos)

    saida(f"Agente Text-to-SQL pronto. Digite sua pergunta ou '{COMANDO_SAIR}' para encerrar.")
    while True:
        try:
            texto = entrada(PROMPT)
        except (EOFError, KeyboardInterrupt):
            return 0
        if texto.strip().lower() == COMANDO_SAIR:
            return 0
        erro = validar_entrada(texto)
        if erro:
            saida(erro)
            continue
        try:
            resp = agente.responder(texto.strip())
            _exibir_resposta(resp, config, saida)
        except Exception as exc:  # a sessão nunca deve cair por uma pergunta
            saida(mascarar(f"Erro ao processar a pergunta: {exc}", config.api_key))
