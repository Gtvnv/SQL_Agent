"""Log_Auditoria: registro das interações em JSON Lines."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from sql_agent.config import PADRAO_AUDIT_PATH

LIMITE_PERGUNTA = 4000
LIMITE_SQL = 10000
TIMEOUT_GRAVACAO_S = 2


@dataclass
class RegistroAuditoria:
    pergunta: str
    sql: str
    validacao: str  # "aprovada" | "reprovada"
    tentativas: int  # 1..3
    status: str  # "sucesso" | "falha"
    motivo_reprovacao: str | None = None
    timestamp_utc: str = ""
    pergunta_truncada: bool = False
    sql_truncada: bool = False

    def __post_init__(self) -> None:
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def truncar(texto: str, limite: int) -> tuple[str, bool]:
    """Devolve o texto limitado a `limite` caracteres e se houve truncamento."""
    if len(texto) > limite:
        return texto[:limite], True
    return texto, False


def _serializar(reg: RegistroAuditoria) -> str:
    pergunta, p_trunc = truncar(reg.pergunta or "", LIMITE_PERGUNTA)
    sql, s_trunc = truncar(reg.sql or "", LIMITE_SQL)
    dados = {
        "timestamp_utc": reg.timestamp_utc,
        "pergunta": pergunta,
        "pergunta_truncada": p_trunc or reg.pergunta_truncada,
        "sql": sql,
        "sql_truncada": s_trunc or reg.sql_truncada,
        "validacao": reg.validacao,
        "motivo_reprovacao": reg.motivo_reprovacao,
        "tentativas": reg.tentativas,
        "status": reg.status,
    }
    return json.dumps(dados, ensure_ascii=False)


def gravar(reg: RegistroAuditoria, caminho: str = PADRAO_AUDIT_PATH) -> bool:
    """Acrescenta o registro ao arquivo JSON Lines.

    Roda em thread com `join(2)`. Devolve False em falha ou excesso de tempo,
    sem nova tentativa.
    """
    resultado = {"ok": False}
    cancelado = threading.Event()

    def _escrever() -> None:
        try:
            linha = _serializar(reg) + "\n"
            if cancelado.is_set():
                return
            with open(caminho, "a", encoding="utf-8") as f:
                f.write(linha)
            resultado["ok"] = True
        except Exception:
            resultado["ok"] = False

    t = threading.Thread(target=_escrever, daemon=True)
    t.start()
    t.join(TIMEOUT_GRAVACAO_S)
    if t.is_alive():
        cancelado.set()
        return False
    return resultado["ok"]
