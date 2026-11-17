"""Avaliação de qualidade: compara o resultado da SQL gerada com o da esperada."""

from __future__ import annotations

import dataclasses
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

import yaml
from dotenv import dotenv_values

from sql_agent.agent import STATUS_SUCESSO, Agente
from sql_agent.config import ConfigError, carregar_config, mascarar
from sql_agent.executor import ExecutorSql, ResultadoExecucao
from sql_agent.llm import HttpLlmClient
from sql_agent.schema import extrair_esquema_ou_sair

TIMEOUT_PAR_S = 30.0
MAX_LINHAS_AVALIACAO = 1_000_000

_RE_ORDER_BY = re.compile(r"\border\s+by\b", re.IGNORECASE)

_DIR_RAIZ = Path(__file__).resolve().parent.parent
_DATASET_PADRAO = _DIR_RAIZ / "eval" / "dataset.yaml"
_DIR_DB = _DIR_RAIZ / "db"


class AgenteAvaliavel(Protocol):
    """Qualquer objeto com `responder(pergunta)` (ex.: `Agente`)."""

    def responder(self, pergunta: str) -> Any: ...


@dataclass
class Falha:
    pergunta: str
    sql_gerada: str
    motivo: str


@dataclass
class RelatorioAvaliacao:
    acertos: int = 0
    total: int = 0
    falhas: list[Falha] = field(default_factory=list)

    @property
    def taxa(self) -> float:
        """Percentual de acertos com 1 casa decimal (0.0 se não há pares)."""
        if self.total == 0:
            return 0.0
        return round(100.0 * self.acertos / self.total, 1)

    def formatar(self) -> str:
        linhas = [
            f"Total de perguntas: {self.total}",
            f"Acertos: {self.acertos}",
            f"Taxa de acerto: {self.taxa:.1f}%",
        ]
        if self.falhas:
            linhas.append("Falhas:")
            for i, f in enumerate(self.falhas, 1):
                linhas.append(f"  {i}. Pergunta: {f.pergunta}")
                linhas.append(f"     SQL gerada: {f.sql_gerada or '(nenhuma)'}")
                linhas.append(f"     Motivo: {f.motivo}")
        return "\n".join(linhas)


def tem_order_by(sql: str) -> bool:
    return bool(_RE_ORDER_BY.search(sql or ""))


def _linhas(resultado: Any) -> list[tuple]:
    if isinstance(resultado, ResultadoExecucao):
        resultado = resultado.linhas
    return [tuple(l) for l in resultado]


def comparar_resultados(gerado: Any, esperado: Any, ordenado: bool) -> bool:
    """Igualdade de resultados: multiconjunto sem ORDER BY, ordem exata com ele.

    Aceita listas de linhas ou `ResultadoExecucao`; nomes de colunas são ignorados.
    """
    g, e = _linhas(gerado), _linhas(esperado)
    if ordenado:
        return g == e
    return Counter(g) == Counter(e)


def _responder_com_timeout(agente: AgenteAvaliavel, pergunta: str, timeout_s: float):
    """Executa `agente.responder` em thread; devolve (resposta, erro, estourou)."""
    caixa: dict[str, Any] = {}

    def _alvo() -> None:
        try:
            caixa["resp"] = agente.responder(pergunta)
        except BaseException as exc:  # noqa: BLE001 - registrado como falha
            caixa["erro"] = exc

    t = threading.Thread(target=_alvo, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None, None, True
    return caixa.get("resp"), caixa.get("erro"), False


_MOTIVOS_ETAPA = {
    "geracao": "erro do LLM na geração da SQL",
    "dados_indisponiveis": "dados indisponíveis (NAO_DISPONIVEL)",
    "validacao": "SQL rejeitada pelo validador",
    "execucao": "erro de execução da SQL",
    "correcao": "erro do LLM na correção da SQL",
}


def avaliar(
    dataset: Sequence[Mapping[str, Any]],
    agente: AgenteAvaliavel,
    executor: ExecutorSql,
    timeout_s: float = TIMEOUT_PAR_S,
) -> RelatorioAvaliacao:
    """Avalia cada par; falhas (LLM, validador, execução, timeout) não interrompem."""
    rel = RelatorioAvaliacao()
    for par in dataset:
        rel.total += 1
        pergunta = str(par.get("pergunta", ""))
        sql_esperada = str(par.get("sql_esperada", ""))
        sql_gerada = ""
        try:
            resp, erro, estourou = _responder_com_timeout(agente, pergunta, timeout_s)
            if estourou:
                motivo = f"tempo limite de {timeout_s:g} s excedido"
            elif erro is not None:
                motivo = f"erro inesperado do agente: {type(erro).__name__}: {erro}"
            else:
                sql_gerada = getattr(resp, "sql", "") or ""
                if getattr(resp, "status", None) != STATUS_SUCESSO or resp.resultado is None:
                    etapa = getattr(resp, "etapa_falha", None)
                    base = _MOTIVOS_ETAPA.get(etapa, "falha ao responder")
                    detalhe = getattr(resp, "erro", None)
                    motivo = f"{base}: {detalhe}" if detalhe else base
                else:
                    esperado = executor.executar(sql_esperada)
                    if comparar_resultados(
                        resp.resultado, esperado, tem_order_by(sql_esperada)
                    ):
                        rel.acertos += 1
                        continue
                    motivo = "resultado diferente do esperado"
        except Exception as exc:  # ex.: SQL esperada inválida
            motivo = f"erro ao avaliar o par: {type(exc).__name__}: {exc}"
        rel.falhas.append(Falha(pergunta, sql_gerada, motivo))
    return rel


def carregar_dataset(caminho: str | os.PathLike) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    if not isinstance(dados, list):
        raise ValueError(f"Conjunto de avaliação inválido em {caminho}: esperado uma lista.")
    return [d for d in dados if isinstance(d, dict) and "pergunta" in d and "sql_esperada" in d]


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    saida: Callable[[str], Any] = print,
    dotenv_path: str | os.PathLike = ".env",
) -> int:
    """Executa a avaliação com o LLM real e imprime o relatório."""
    ambiente = os.environ if env is None else env
    try:
        config = carregar_config(ambiente, dotenv_values(dotenv_path))
    except ConfigError as exc:
        saida(f"Erro de configuração: variável obrigatória ausente ou vazia: {exc}")
        return 2

    caminho = Path(argv[0]) if argv else _DATASET_PADRAO
    try:
        dataset = carregar_dataset(caminho)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        saida(f"Erro ao ler o conjunto de avaliação: {exc}")
        return 1

    # Auditoria separada da usada pela CLI; sem truncar resultados na comparação.
    audit_path = str(Path(config.audit_path).with_name("audit_avaliacao.jsonl"))
    config = dataclasses.replace(
        config, audit_path=audit_path, max_linhas=MAX_LINHAS_AVALIACAO
    )

    import sqlite3

    try:
        uri = f"{Path(config.db_path).resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        saida(f"Erro ao acessar o banco de dados: {exc}")
        return 1
    try:
        try:
            descricoes = {}
            p = _DIR_DB / "schema_descriptions.yaml"
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    carregado = yaml.safe_load(f)
                descricoes = carregado if isinstance(carregado, dict) else {}
            esquema = extrair_esquema_ou_sair(conn, descricoes)
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) and exc.code else 1
    finally:
        conn.close()

    exemplos: list[dict] = []
    pf = _DIR_DB / "few_shot.yaml"
    if pf.exists():
        try:
            with open(pf, encoding="utf-8") as f:
                carregado = yaml.safe_load(f)
            if isinstance(carregado, list):
                exemplos = [
                    i for i in carregado
                    if isinstance(i, dict) and "pergunta" in i and "sql" in i
                ]
        except (OSError, yaml.YAMLError):
            pass

    executor = ExecutorSql(config.db_path, config.max_linhas, config.timeout_consulta_s)
    agente = Agente(config, esquema, HttpLlmClient(config), executor, exemplos)
    relatorio = avaliar(dataset, agente, executor)
    saida(mascarar(relatorio.formatar(), config.api_key))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
