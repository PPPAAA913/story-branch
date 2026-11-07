import io
import json
import os
import unittest
from unittest.mock import patch

from studio.generation import GenerationError, OpenRouterGenerator


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class OpenRouterAdapterTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "test/model"})
    @patch("studio.generation.urlopen")
    def test_sends_bearer_token_and_parses_model_json(self, mocked_open):
        body = {"choices": [{"message": {"content": '{"result":"ok"}'}}]}
        mocked_open.return_value = FakeResponse(json.dumps(body).encode("utf-8"))
        generator = OpenRouterGenerator()
        self.assertEqual({"result": "ok"}, generator._complete_json("test prompt"))
        request = mocked_open.call_args.args[0]
        sent = json.loads(request.data)
        self.assertEqual("https://openrouter.ai/api/v1/chat/completions", request.full_url)
        self.assertEqual("Bearer test-key", request.get_header("Authorization"))
        self.assertEqual("test/model", sent["model"])

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "test/model"})
    @patch("studio.generation.urlopen")
    def test_rejects_unexpected_provider_payload(self, mocked_open):
        mocked_open.return_value = FakeResponse(b'{"choices":[]}')
        with self.assertRaisesRegex(GenerationError, "unexpected response"):
            OpenRouterGenerator()._complete_json("test prompt")


if __name__ == "__main__":
    unittest.main()
