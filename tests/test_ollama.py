import io
import json
import unittest
from unittest.mock import patch

from avrs.backend import OllamaBackend


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return self.payload


class OllamaBackendTests(unittest.TestCase):
    def test_chat_request_format_and_tokens(self):
        reply = {
            "message": {"role": "assistant", "content": '{"answer":"42"}'},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        with patch("urllib.request.urlopen", return_value=FakeHTTPResponse(reply)) as call:
            client = OllamaBackend(model="llama3.2:3b")
            output = client.ask("You are helpful", "What is 6*7?")
        self.assertEqual(output.data["answer"], "42")
        self.assertEqual(output.usage["total_tokens"], 15)
        req = call.call_args.args[0]
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["model"], "llama3.2:3b")
        self.assertEqual(body["format"], "json")
        self.assertFalse(body["stream"])
        self.assertEqual(req.full_url, "http://localhost:11434/api/chat")

    def test_missing_ollama_server_gives_hint(self):
        from urllib.error import URLError
        with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
            with self.assertRaisesRegex(RuntimeError, "ollama serve"):
                OllamaBackend().ask("system", "user")


if __name__ == "__main__":
    unittest.main()
