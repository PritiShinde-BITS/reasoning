"""JSON-only LLM adapters. Only OpenAI backend talks to a model; mock is for plumbing tests."""
from dataclasses import dataclass
import json
import os
import time
from typing import Any


@dataclass
class Response:
    data: dict[str, Any]
    usage: dict[str, int]
    raw: str


class OpenAIBackend:
    def __init__(self, model: str = "gpt-4o-mini", max_retries: int = 3):
        from openai import OpenAI  # lazy import for offline unit tests
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("Set OPENAI_API_KEY before running paid experiments")
        self.client = OpenAI(timeout=90.0, max_retries=0)
        self.model = model
        self.max_retries = max_retries
        self.is_mock = False

    def ask(self, system: str, user: str) -> Response:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_completion_tokens=1600,
                )
                raw = result.choices[0].message.content or ""
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError("Model did not return a JSON object")
                usage = result.usage
                return Response(
                    data=obj,
                    usage={"input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                           "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                           "total_tokens": int(getattr(usage, "total_tokens", 0) or 0)},
                    raw=raw,
                )
            except Exception as exc:
                last_error = exc
                if attempt + 1 == self.max_retries:
                    break
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"LLM request failed after {self.max_retries} attempts: {last_error}")


class OllamaBackend:
    """Local Ollama JSON-chat backend. No API key and no extra pip dependency."""
    is_mock = False

    def __init__(
        self,
        model: str = "llama3.2:3b",
        base_url: str = "http://localhost:11434",
        max_retries: int = 2,
        timeout: int = 300,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout

    def ask(self, system: str, user: str) -> Response:
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError, URLError

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0, "num_predict": 1600},
            "keep_alive": "5m",
        }
        last_error = None
        for attempt in range(self.max_retries):
            request = Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                raw = result.get("message", {}).get("content", "")
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError("Ollama did not return a JSON object")
                inp = int(result.get("prompt_eval_count") or 0)
                out = int(result.get("eval_count") or 0)
                return Response(
                    data=obj,
                    usage={"input_tokens": inp, "output_tokens": out,
                           "total_tokens": inp + out},
                    raw=raw,
                )
            except HTTPError as exc:
                try:
                    detail = exc.read().decode("utf-8")[:500]
                except Exception:
                    detail = ""
                if exc.code == 404:
                    raise RuntimeError(
                        f"Ollama model {self.model!r} was not found. "
                        f"Check 'ollama list' or run 'ollama pull {self.model}'. {detail}"
                    ) from exc
                if exc.code < 500:
                    raise RuntimeError(
                        f"Ollama HTTP {exc.code}: {detail}"
                    ) from exc
                last_error = f"Ollama HTTP {exc.code}: {detail}"
            except URLError as exc:
                raise RuntimeError(
                    f"Cannot connect to Ollama at {self.base_url}. "
                    "Open Ollama.app or run 'ollama serve'."
                ) from exc
            except (ValueError, KeyError) as exc:
                last_error = (
                    f"Ollama returned invalid or truncated JSON: {exc}. "
                    "Try another model or increase num_predict."
                )
            if attempt + 1 < self.max_retries:
                time.sleep(1)
        raise RuntimeError(
            f"Local Ollama request failed after {self.max_retries} attempts: {last_error}"
        )


class MockBackend:
    """Deterministic contract test, NOT a real LLM and NOT research data."""
    model = "MOCK_NOT_FOR_TRAINING"
    is_mock = True

    def ask(self, system: str, user: str) -> Response:
        if "JOINT_PLAN" in system:
            obj = {"plans": [
                {"id": "A", "tactic": "direct", "instructions": "Find answer directly."},
                {"id": "B", "tactic": "program", "instructions": "Calculate with expressions."},
                {"id": "C", "tactic": "direct", "instructions": "Check independently."},
            ]}
        elif "AGGREGATOR" in system:
            obj = {"selected_id": "A", "reason": "Mock selection for integration test"}
        elif "PROGRAM_SOLVER" in system:
            obj = {"steps": [{"name": "x", "expr": "2 + 3"}],
                   "answer_expr": "x", "explanation": "Mock arithmetic"}
        else:
            obj = {"answer": "5", "explanation": "Mock integration test answer"}
        return Response(obj, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, json.dumps(obj))
