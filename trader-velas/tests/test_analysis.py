import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from server import MarketDataError, analyze_candles, crypto_symbols, load_local_env, relative_strength_index


def candles_from_closes(closes):
    return [
        {
            "time": f"2025-01-{index + 1:02d}T00:00:00",
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 100,
        }
        for index, close in enumerate(closes)
    ]


class AnalysisTests(unittest.TestCase):
    def test_strong_uptrend_returns_bullish_confluence(self):
        closes = [100 + index for index in range(80)]

        result = analyze_candles(candles_from_closes(closes))

        self.assertEqual(result["direction"], "alta")
        self.assertGreaterEqual(result["confluence"], 70)
        self.assertLessEqual(result["confluence"], 100)
        self.assertEqual(result["indicators"]["trend"], "positivo")
        self.assertEqual(result["indicators"]["rsi"], "positivo")
        self.assertEqual(len(result["ema20Series"]), len(closes))

    def test_strong_downtrend_returns_bearish_confluence(self):
        closes = [200 - index for index in range(80)]

        result = analyze_candles(candles_from_closes(closes))

        self.assertEqual(result["direction"], "baixa")
        self.assertGreaterEqual(result["confluence"], 70)
        self.assertLessEqual(result["confluence"], 100)
        self.assertEqual(result["indicators"]["trend"], "negativo")

    def test_analysis_rejects_insufficient_history(self):
        with self.assertRaises(MarketDataError):
            analyze_candles(candles_from_closes([100 + index for index in range(49)]))

    def test_rsi_handles_flat_and_one_directional_series(self):
        self.assertEqual(relative_strength_index([10] * 16), 50)
        self.assertEqual(relative_strength_index(list(range(16))), 100)

    def test_local_env_loads_key_without_overriding_existing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text('TWELVE_DATA_API_KEY="local-key"\n', encoding="utf-8")
            with patch("server.ROOT", Path(directory)), patch.dict(os.environ, {}, clear=True):
                load_local_env()
                self.assertEqual(os.environ["TWELVE_DATA_API_KEY"], "local-key")

            with patch("server.ROOT", Path(directory)), patch.dict(
                os.environ, {"TWELVE_DATA_API_KEY": "environment-key"}, clear=True
            ):
                load_local_env()
                self.assertEqual(os.environ["TWELVE_DATA_API_KEY"], "environment-key")

    def test_crypto_search_prioritizes_assets_matching_the_query(self):
        exchange_info = {
            "symbols": [
                {"symbol": "BTCARS", "baseAsset": "BTC", "quoteAsset": "ARS", "status": "TRADING"},
                {"symbol": "BTCFDUSD", "baseAsset": "BTC", "quoteAsset": "FDUSD", "status": "TRADING"},
                {"symbol": "ETHBTC", "baseAsset": "ETH", "quoteAsset": "BTC", "status": "TRADING"},
                {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING"},
            ]
        }
        with patch("server.request_json", return_value=exchange_info), patch(
            "server.SYMBOL_CACHE", {"expires_at": 0.0, "symbols": []}
        ):
            results = crypto_symbols("BTC")

        self.assertEqual(results[0], {"symbol": "BTCUSDT", "name": "BTC / USDT"})
        self.assertIn({"symbol": "ETHBTC", "name": "ETH / BTC"}, results)


if __name__ == "__main__":
    unittest.main()
