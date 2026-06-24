"""A thin Ollama adapter (M1 spec §5/§7, handoff §4.5).

``OllamaClient`` is the single seam through which a model call is made: given a
prompt, model, seed, and temperature, it returns the completion text plus call
metadata (resolved model+version, prompt/completion token counts, latency). It is
the M5 routing seam at first genuine use and is kept **thin** — no routing, no
model-selection policy, no cost guard, no retry beyond the one bounded HTTP call
(D16.4). It must not grow into a framework.

Transport. The HTTP call uses the standard library (``urllib``) so M1 adds no new
dependency — ``pyproject.toml`` is not a permitted M1 modification. The transport is
an injectable seam: tests supply a stub so the unit tests never touch a real Ollama
(CI stays hermetic, M1 spec §14); the default transport POSTs to Ollama's
``/api/generate``.

Errors. Any infrastructure failure (connection refused, timeout, malformed response)
raises the typed :class:`ModelUnavailableError`; the client never returns a partial
or silent result (M1 spec §7).

Configuration note (raised, not silently resolved — handoff preamble): the Ollama
host and timeout are ``Settings`` fields added in C7 (§4.8). To keep C5 atomic and
green they are injected via the constructor with defaults (``host.docker.internal``
per D16.2); the orchestrator (C7) will read them from ``Settings`` and pass them in —
the same injection pattern used for the store path (C2) and verifier timeout (C4).
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from velith.core.logging import get_logger

logger = get_logger(__name__)

#: Default Ollama endpoint reached from inside the container (D16.2).
DEFAULT_HOST: Final[str] = "http://host.docker.internal:11434"

#: Default wall-clock budget for a single generate call (seconds).
DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0

#: A parsed JSON object, and the injectable transport that returns one.
JsonObject = Mapping[str, Any]
Transport = Callable[[str, JsonObject], JsonObject]


class ModelUnavailableError(Exception):
    """Raised on any infrastructure failure of the model call (M1 spec §7).

    Connection refused, timeout, or a malformed response all surface as this typed
    error — never a partial or silent result. The orchestrator maps it to the
    ``INFRA_ERROR`` verdict and a non-zero exit.
    """


class Completion(BaseModel):
    """The result of one model call: the text plus provenance metadata.

    ``model`` is the requested model; ``model_version`` is the model string Ollama
    resolved and echoed (often a more specific tag). ``protected_namespaces=()``
    disables pydantic's ``model_`` namespace guard so ``model_version`` is permitted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    text: str
    model: str
    model_version: str
    prompt_tokens: int
    completion_tokens: int
    latency_seconds: float


class OllamaClient:
    """A thin adapter over a local Ollama server's ``/api/generate`` endpoint."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: Transport | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._timeout = timeout_seconds
        self._transport: Transport = transport if transport is not None else self._http_post

    def generate(self, *, prompt: str, model: str, seed: int, temperature: float) -> Completion:
        """Call the model and return its completion plus metadata.

        Pure with respect to its inputs except for model nondeterminism. Raises
        :class:`ModelUnavailableError` on any infrastructure failure.
        """
        url = f"{self._host}/api/generate"
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"seed": seed, "temperature": temperature},
        }
        start = time.monotonic()
        try:
            response = self._transport(url, payload)
        except (OSError, ValueError) as exc:
            raise ModelUnavailableError(f"Ollama request to {url} failed: {exc}") from exc
        latency = time.monotonic() - start

        try:
            text = str(response["response"])
            resolved_model = str(response.get("model", model))
            prompt_tokens = int(response.get("prompt_eval_count", 0))
            completion_tokens = int(response.get("eval_count", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelUnavailableError(f"malformed Ollama response: {exc}") from exc

        logger.info(
            "ollama generate completed",
            extra={
                "event": "ollama_generate",
                "model": model,
                "model_version": resolved_model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_seconds": latency,
            },
        )
        return Completion(
            text=text,
            model=model,
            model_version=resolved_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_seconds=latency,
        )

    def _http_post(self, url: str, payload: JsonObject) -> JsonObject:
        """Default transport: POST the payload to Ollama and parse the JSON reply."""
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as resp:
            body = resp.read()
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object from Ollama")
        return parsed
