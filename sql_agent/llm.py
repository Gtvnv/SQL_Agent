"""Cliente LLM: Protocol, exceções de domínio e adaptador HTTP (stdlib)."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

URL_PADRAO = "https://api.openai.com/v1/chat/completions"


class LlmTimeout(Exception):
    """O provedor não respondeu dentro do tempo limite."""


class LlmRedeError(Exception):
    """Falha de rede, de autenticação ou erro do provedor."""


class LlmLimiteError(Exception):
    """O provedor recusou por limite de requisições (HTTP 429)."""


@runtime_checkable
class LlmClient(Protocol):
    def completar(self, system: str, user: str, timeout_s: float) -> str: ...


class HttpLlmClient:
    """Adaptador para APIs compatíveis com chat completions da OpenAI.

    Lê chave e modelo da Config (``api_key`` e ``model``). A chave nunca é
    incluída em mensagens de erro nem em ``repr``.
    """

    def __init__(self, config, url: str = URL_PADRAO) -> None:
        self._api_key = config.api_key
        self._model = config.model
        self._url = url

    def __repr__(self) -> str:
        return f"HttpLlmClient(model={self._model!r}, url={self._url!r})"

    def completar(self, system: str, user: str, timeout_s: float) -> str:
        corpo = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=corpo,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise LlmLimiteError("limite de requisições do LLM excedido") from None
            if e.code in (408, 504):
                raise LlmTimeout("tempo limite do LLM excedido") from None
            raise LlmRedeError(f"erro do provedor LLM (HTTP {e.code})") from None
        except (socket.timeout, TimeoutError):
            raise LlmTimeout("tempo limite do LLM excedido") from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise LlmTimeout("tempo limite do LLM excedido") from None
            raise LlmRedeError("falha de rede ao acessar o LLM") from None
        except (OSError, ValueError):
            raise LlmRedeError("falha de rede ou resposta inválida do LLM") from None

        try:
            return dados["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LlmRedeError("resposta inesperada do provedor LLM") from None
