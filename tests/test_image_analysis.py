import base64
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from image_analysis import AnalysisError, analyze_image, fetch_news, validate_image
from server import TraderVelasHandler


PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode("ascii")
FEED = b"""<rss><channel><item><title>Bitcoin market</title>
<link>https://news.google.com/articles/example</link>
<source>Example News</source><pubDate>Wed, 18 Nov 2026 10:00:00 GMT</pubDate>
</item></channel></rss>"""


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ImageAnalysisTests(unittest.TestCase):
    def test_rejects_non_image_and_oversized_input(self):
        with self.assertRaises(AnalysisError):
            validate_image(base64.b64encode(b"not an image").decode("ascii"))
        with self.assertRaises(AnalysisError):
            validate_image("A" * (7 * 1024 * 1024))

    def test_news_deduplicates_editions_and_preserves_sources(self):
        with patch("image_analysis.urlopen", side_effect=lambda *args, **kwargs: Response(FEED)):
            result = fetch_news("Bitcoin")
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["articles"][0]["source"], "Example News")
        self.assertEqual(result["articles"][0]["url"], "https://news.google.com/articles/example")

    def test_reports_news_provider_failure(self):
        with patch("image_analysis.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(AnalysisError, "notícias"):
                fetch_news("Bitcoin")

    def test_image_is_sent_only_to_local_ollama_with_headlines(self):
        response = json.dumps({"message": {"content": "Cenários condicionais."}}).encode()
        with patch("image_analysis.build_opener") as build:
            build.return_value.open.return_value = Response(response)
            result = analyze_image(PNG, "Bitcoin", ["Bitcoin market"])
        request = build.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(payload["model"], "qwen2.5vl:3b")
        self.assertEqual(payload["messages"][0]["images"], [PNG])
        self.assertIn("Bitcoin market", payload["messages"][0]["content"])
        self.assertIn("O que estudar", payload["messages"][0]["content"])
        self.assertEqual(result, "Cenários condicionais.")

    def test_gemini_receives_image_only_after_consent(self):
        response = json.dumps({
            "candidates": [{
                "content": {"parts": [{"text": "Leitura do gráfico."}]},
                "finishReason": "STOP",
            }]
        }).encode()
        with patch.dict("os.environ", {
            "IMAGE_ANALYSIS_PROVIDER": "gemini",
            "GEMINI_API_KEY": "test-key",
        }), patch("image_analysis.urlopen", return_value=Response(response)) as open_url:
            result = analyze_image(PNG, "Bitcoin", ["Bitcoin market"], consent=True)

        request = open_url.call_args.args[0]
        payload = json.loads(request.data)
        self.assertIn("gemini-3.5-flash-lite:generateContent", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertNotIn("test-key", request.full_url)
        self.assertEqual(payload["contents"][0]["parts"][1]["inline_data"]["mime_type"], "image/png")
        self.assertEqual(payload["contents"][0]["parts"][1]["inline_data"]["data"], PNG)
        self.assertEqual(result, "Leitura do gráfico.")

    def test_gemini_rejects_missing_consent_without_sending_image(self):
        with patch.dict("os.environ", {
            "IMAGE_ANALYSIS_PROVIDER": "gemini",
            "GEMINI_API_KEY": "test-key",
        }), patch("image_analysis.urlopen") as open_url:
            with self.assertRaisesRegex(AnalysisError, "autorização"):
                analyze_image(PNG, "Bitcoin", [], consent=False)
        open_url.assert_not_called()

    def test_gemini_rejects_missing_server_key(self):
        with patch.dict("os.environ", {"IMAGE_ANALYSIS_PROVIDER": "gemini"}, clear=True):
            with self.assertRaisesRegex(AnalysisError, "GEMINI_API_KEY"):
                analyze_image(PNG, "Bitcoin", [], consent=True)

    def test_gemini_quota_error_is_actionable(self):
        error = HTTPError(
            "https://generativelanguage.googleapis.com/",
            429,
            "quota",
            {},
            io.BytesIO(b"{}"),
        )
        with patch.dict("os.environ", {
            "IMAGE_ANALYSIS_PROVIDER": "gemini",
            "GEMINI_API_KEY": "test-key",
        }), patch("image_analysis.urlopen", side_effect=error):
            with self.assertRaisesRegex(AnalysisError, "cota gratuita"):
                analyze_image(PNG, "Bitcoin", [], consent=True)

    def test_warns_when_model_response_is_truncated(self):
        response = json.dumps({
            "message": {"content": "Leitura parcial."},
            "done_reason": "length",
        }).encode()
        with patch("image_analysis.build_opener") as build:
            build.return_value.open.return_value = Response(response)
            result = analyze_image(PNG, "Bitcoin", [])
        self.assertIn("pode estar incompleta", result)

    def test_timeout_has_actionable_error(self):
        with patch("image_analysis.build_opener") as build:
            build.return_value.open.side_effect = TimeoutError()
            with self.assertRaisesRegex(AnalysisError, "demorou demais"):
                analyze_image(PNG, "Bitcoin", [])

    def test_ollama_server_error_includes_details(self):
        error = HTTPError("http://127.0.0.1:11434/api/chat", 500, "error", {}, io.BytesIO(b'{"error":"model failure"}'))
        with patch("image_analysis.build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaisesRegex(AnalysisError, "model failure"):
                analyze_image(PNG, "Bitcoin", [])

    def test_missing_ollama_shows_actionable_error(self):
        with patch("image_analysis.build_opener") as build:
            build.return_value.open.side_effect = URLError("offline")
            with self.assertRaisesRegex(AnalysisError, "Ollama local"):
                analyze_image(PNG, "Bitcoin", [])

    def test_post_rejects_remote_origin(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), TraderVelasHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/image-analysis",
                data=b"{}",
                headers={"Content-Type": "application/json", "Origin": "https://example.com"},
            )
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_news_route_rejects_invalid_topic_as_client_error(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), TraderVelasHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as error:
                urlopen(f"http://127.0.0.1:{server.server_port}/api/news?topic=x")
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_config_reports_when_gemini_consent_is_required(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), TraderVelasHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict("os.environ", {"IMAGE_ANALYSIS_PROVIDER": "gemini"}):
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/config") as response:
                    payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["imageAnalysisProvider"], "gemini")
            self.assertTrue(payload["imageConsentRequired"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
