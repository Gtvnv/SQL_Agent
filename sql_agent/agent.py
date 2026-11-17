"""Agente: orquestra gerar, validar, executar, autocorrigir, explicar e auditar."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from sql_agent import audit as _audit
from sql_agent.audit import RegistroAuditoria
from sql_agent.config import Config, mascarar
from sql_agent.executor import (
    ErroAcessoBanco,
    ErroExecucao,
    ExecutorSql,
    ResultadoExecucao,
    TempoExcedido,
)
from sql_agent.explainer import explicar
from sql_agent.generator import NAO_DISPONIVEL, GeracaoError, corrigir, gerar
from sql_agent.llm import LlmClient, LlmLimiteError, LlmRedeError, LlmTimeout
from sql_agent.schema import SchemaInfo
from sql_agent.validator import validar

STATUS_SUCESSO = "sucesso"
STATUS_FALHA = "falha"

ETAPA_GERACAO = "geracao"
ETAPA_DADOS = "dados_indisponiveis"
ETAPA_VALIDACAO = "validacao"
ETAPA_EXECUCAO = "execucao"
ETAPA_CORRECAO = "correcao"
ETAPA_INTERNA = "interna"

TENTATIVAS_AUDITORIA_MIN = 1
TENTATIVAS_AUDITORIA_MAX = 3

MSG_SEM_DADOS = "Os dados necessários para responder à pergunta não estão disponíveis no banco."

_ERROS_LLM = (LlmRedeError, LlmLimiteError, LlmTimeout)


@dataclass
class Resposta:
    sql: str = ""
    resultado: ResultadoExecucao | None = None
    explicacao: str | None = None
    erro: str | None = None
    etapa_falha: str | None = None
    tentativas: int = 1  # 1 + número de correções enviadas ao LLM
    status: str = STATUS_FALHA
    auditado: bool = False
    avisos: list[str] = field(default_factory=list)


class _Falha(Exception):
    """Encerra o fluxo com falha controlada em uma etapa."""

    def __init__(self, etapa: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.etapa = etapa
        self.mensagem = mensagem


class Agente:
    def __init__(
        self,
        config: Config,
        esquema: SchemaInfo,
        llm: LlmClient,
        executor: ExecutorSql,
        exemplos: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        self._config = config
        self._esquema = esquema
        self._llm = llm
        self._executor = executor
        self._exemplos = list(exemplos or [])

    # ------------------------------------------------------------------
    def _m(self, texto: str | None) -> str:
        return mascarar(texto, self._config.api_key) if texto else (texto or "")

    def _msg_llm(self, exc: Exception, etapa: str) -> str:
        if isinstance(exc, LlmLimiteError):
            causa = "limite de requisições do provedor LLM atingido"
        elif isinstance(exc, LlmTimeout):
            causa = "tempo limite excedido ao consultar o LLM"
        else:
            causa = "falha de rede ao consultar o LLM"
        detalhe = str(exc).strip()
        return f"Falha na etapa de {etapa}: {causa}" + (f" ({detalhe})" if detalhe else "")

    # ------------------------------------------------------------------
    def responder(self, pergunta: str) -> Resposta:
        resp = Resposta()
        estado = {"validacao": "reprovada", "motivo": None}
        try:
            self._fluxo(pergunta, resp, estado)
        except _Falha as f:
            resp.status = STATUS_FALHA
            resp.etapa_falha = f.etapa
            resp.erro = f.mensagem
            resp.resultado = None
        except Exception as exc:  # defesa: a sessão nunca deve cair
            resp.status = STATUS_FALHA
            resp.etapa_falha = ETAPA_INTERNA
            resp.erro = f"Erro inesperado: {type(exc).__name__}: {exc}"
            resp.resultado = None

        resp.sql = self._m(resp.sql)
        resp.erro = self._m(resp.erro) if resp.erro else None
        resp.explicacao = self._m(resp.explicacao) if resp.explicacao else None
        if resp.status != STATUS_SUCESSO:
            resp.resultado = None
            resp.explicacao = None
        self._auditar(pergunta, resp, estado)
        return resp

    # ------------------------------------------------------------------
    def _fluxo(self, pergunta: str, resp: Resposta, estado: dict) -> None:
        cfg = self._config
        try:
            sql = gerar(pergunta, self._esquema, self._llm, self._exemplos)
        except GeracaoError as exc:
            estado["motivo"] = str(exc)
            raise _Falha(ETAPA_GERACAO, f"Falha na geração da SQL: {exc}") from None
        except _ERROS_LLM as exc:
            msg = self._msg_llm(exc, "geração")
            estado["motivo"] = "llm indisponível"
            raise _Falha(ETAPA_GERACAO, msg) from None

        if sql == NAO_DISPONIVEL:
            estado["motivo"] = "dados não disponíveis"
            raise _Falha(ETAPA_DADOS, MSG_SEM_DADOS)

        resp.sql = sql
        correcoes = 0
        while True:
            resp.tentativas = 1 + correcoes
            val = validar(sql, self._esquema)
            if not val.aprovada:
                estado["validacao"] = "reprovada"
                motivo = val.motivo or "consulta reprovada"
                if val.palavra_chave and val.palavra_chave not in motivo:
                    motivo = f"{motivo} ({val.palavra_chave})"
                estado["motivo"] = motivo
                raise _Falha(ETAPA_VALIDACAO, f"Consulta reprovada pelo validador: {motivo}")
            estado["validacao"] = "aprovada"
            estado["motivo"] = None

            try:
                resultado = self._executor.executar(sql)
            except TempoExcedido as exc:
                raise _Falha(ETAPA_EXECUCAO, str(exc)) from None
            except ErroAcessoBanco as exc:
                raise _Falha(ETAPA_EXECUCAO, str(exc)) from None
            except ErroExecucao as exc:
                ultimo_erro = str(exc)
                if correcoes >= cfg.max_correcoes:
                    raise _Falha(
                        ETAPA_EXECUCAO,
                        f"Erro de execução após {correcoes} correção(ões): {ultimo_erro}",
                    ) from None
                correcoes += 1
                resp.tentativas = 1 + correcoes
                try:
                    novo = corrigir(
                        pergunta, sql, self._m(ultimo_erro), self._esquema, self._llm, self._exemplos
                    )
                except GeracaoError as g:
                    raise _Falha(
                        ETAPA_CORRECAO,
                        f"Falha na correção da SQL: {g}. Último erro de execução: {ultimo_erro}",
                    ) from None
                except _ERROS_LLM as e:
                    raise _Falha(
                        ETAPA_CORRECAO,
                        f"{self._msg_llm(e, 'correção')}. Último erro de execução: {ultimo_erro}",
                    ) from None
                if novo == NAO_DISPONIVEL:
                    raise _Falha(
                        ETAPA_CORRECAO,
                        f"Falha na correção da SQL. Último erro de execução: {ultimo_erro}",
                    )
                sql = novo
                resp.sql = sql
                continue

            resp.resultado = resultado
            resp.status = STATUS_SUCESSO
            resp.etapa_falha = None
            resp.erro = None
            resp.explicacao = explicar(pergunta, sql, resultado, self._llm)
            return

    # ------------------------------------------------------------------
    def _auditar(self, pergunta: str, resp: Resposta, estado: dict) -> None:
        tentativas = min(
            max(resp.tentativas, TENTATIVAS_AUDITORIA_MIN), TENTATIVAS_AUDITORIA_MAX
        )
        motivo = self._m(estado["motivo"]) if estado["motivo"] else None
        reg = RegistroAuditoria(
            pergunta=self._m(pergunta),
            sql=resp.sql or "",
            validacao=estado["validacao"],
            tentativas=tentativas,
            status=resp.status,
            motivo_reprovacao=motivo,
        )
        try:
            resp.auditado = bool(_audit.gravar(reg, self._config.audit_path))
        except Exception:
            resp.auditado = False
        if not resp.auditado:
            resp.avisos.append("Aviso: a interação não foi auditada.")
