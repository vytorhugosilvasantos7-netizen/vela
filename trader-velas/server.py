import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from image_analysis import (
    AnalysisError,
    MAX_IMAGE_BYTES,
    analyze_image,
    fetch_news,
    image_analysis_provider,
    validate_topic,
)


ROOT = Path(__file__).resolve().parent
INTERVALS = {
    "1m": ("1m", "1min"),
    "5m": ("5m", "5min"),
    "15m": ("15m", "15min"),
    "1h": ("1h", "1h"),
    "4h": ("4h", "4h"),
    "1d": ("1d", "1day"),
}
MARKETS = {"crypto", "stocks", "forex"}
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9./_-]{1,32}$")
SYMBOL_CACHE = {"expires_at": 0.0, "symbols": []}
GEMINI_DAILY_LIMIT = 30
GEMINI_USAGE = {"day": "", "count": 0}
GEMINI_USAGE_LOCK = threading.Lock()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class MarketDataError(Exception):
    pass


def load_local_env():
    env_file = ROOT / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return

    for line_number, line in enumerate(lines, start=1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        name, separator, value = entry.partition("=")
        if not separator:
            logging.warning("Ignoring malformed .env entry at line %s", line_number)
            continue
        key = name.strip()
        if key not in {"TWELVE_DATA_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL", "IMAGE_ANALYSIS_PROVIDER"}:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value and not os.environ.get(key, "").strip():
            os.environ[key] = value


def reserve_gemini_request():
    today = datetime.now().date().isoformat()
    with GEMINI_USAGE_LOCK:
        if GEMINI_USAGE["day"] != today:
            GEMINI_USAGE["day"] = today
            GEMINI_USAGE["count"] = 0
        if GEMINI_USAGE["count"] >= GEMINI_DAILY_LIMIT:
            return False
        GEMINI_USAGE["count"] += 1
        return True


def request_json(url):
    request = Request(url, headers={"User-Agent": "TraderVelas/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 429:
            raise MarketDataError("Limite de consultas do provedor atingido. Aguarde e tente novamente.") from error
        raise MarketDataError(f"O provedor de dados respondeu com erro HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        raise MarketDataError("Não foi possível conectar ao provedor de dados agora.") from error
    except json.JSONDecodeError as error:
        raise MarketDataError("O provedor retornou uma resposta inválida.") from error


def get_twelve_data_key():
    key = os.environ.get("TWELVE_DATA_API_KEY", "").strip()
    if not key:
        raise MarketDataError(
            "Configure a variável TWELVE_DATA_API_KEY no servidor para consultar ações e forex."
        )
    return key


def fetch_crypto_candles(symbol, interval):
    params = urlencode({"symbol": symbol.upper(), "interval": INTERVALS[interval][0], "limit": 200})
    payload = request_json(f"https://api.binance.com/api/v3/klines?{params}")
    if not isinstance(payload, list):
        message = payload.get("msg") if isinstance(payload, dict) else None
        raise MarketDataError(message or "Não foi possível obter candles da Binance.")
    candles = []
    now_ms = int(time.time() * 1000)
    for row in payload:
        if not isinstance(row, list) or len(row) < 6:
            continue
        if int(row[6]) > now_ms:
            continue
        candles.append({
            "time": datetime.fromtimestamp(int(row[0]) / 1000).astimezone().isoformat(),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    return candles


def fetch_twelve_data_candles(symbol, interval):
    params = urlencode({
        "symbol": symbol,
        "interval": INTERVALS[interval][1],
        "outputsize": 200,
        "apikey": get_twelve_data_key(),
    })
    payload = request_json(f"https://api.twelvedata.com/time_series?{params}")
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        message = payload.get("message") if isinstance(payload, dict) else None
        raise MarketDataError(message or "Não foi possível obter candles do Twelve Data.")

    candles = []
    for row in reversed(values):
        try:
            candles.append({
                "time": row["datetime"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return candles


def get_candles(market, symbol, interval):
    if market == "crypto":
        return fetch_crypto_candles(symbol, interval)
    return fetch_twelve_data_candles(symbol, interval)


def exponential_moving_average(values, period):
    if len(values) < period:
        return []
    multiplier = 2 / (period + 1)
    average = sum(values[:period]) / period
    result = [None] * (period - 1) + [average]
    for value in values[period:]:
        average = (value - average) * multiplier + average
        result.append(average)
    return result


def relative_strength_index(values, period=14):
    if len(values) <= period:
        return None
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0) for change in changes]
    losses = [max(-change, 0) for change in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        average_gain = (average_gain * (period - 1) + gains[index]) / period
        average_loss = (average_loss * (period - 1) + losses[index]) / period
    if average_loss == 0:
        return 100.0 if average_gain else 50.0
    return 100 - 100 / (1 + average_gain / average_loss)


def analyze_candles(candles):
    if len(candles) < 50:
        raise MarketDataError("São necessários pelo menos 50 candles para calcular a análise.")
    closes = [candle["close"] for candle in candles]
    ema20 = exponential_moving_average(closes, 20)
    ema50 = exponential_moving_average(closes, 50)
    ema12 = exponential_moving_average(closes, 12)
    ema26 = exponential_moving_average(closes, 26)
    macd_line = [fast - slow for fast, slow in zip(ema12, ema26) if fast is not None and slow is not None]
    signal_line = exponential_moving_average(macd_line, 9)
    macd_histogram = macd_line[-1] - signal_line[-1] if signal_line and signal_line[-1] is not None else 0
    rsi = relative_strength_index(closes)

    latest = closes[-1]
    trend_vote = (
        1 if latest > ema20[-1] and ema20[-1] > ema50[-1]
        else -1 if latest < ema20[-1] and ema20[-1] < ema50[-1]
        else 0
    )

    rsi_vote = 1 if rsi is not None and rsi > 55 else -1 if rsi is not None and rsi < 45 else 0
    macd_vote = 1 if macd_histogram > 0 else -1 if macd_histogram < 0 else 0
    score = trend_vote * 0.4 + rsi_vote * 0.3 + macd_vote * 0.3
    direction = "alta" if score >= 0.4 else "baixa" if score <= -0.4 else "lateral"
    change = ((latest / closes[-2]) - 1) * 100 if closes[-2] else 0

    return {
        "direction": direction,
        "confluence": round(abs(score) * 100),
        "latest": latest,
        "change": change,
        "rsi": rsi,
        "ema20": ema20[-1],
        "ema50": ema50[-1],
        "macdHistogram": macd_histogram,
        "indicators": {
            "trend": "positivo" if trend_vote > 0 else "negativo" if trend_vote < 0 else "neutro",
            "rsi": "positivo" if rsi_vote > 0 else "negativo" if rsi_vote < 0 else "neutro",
            "macd": "positivo" if macd_vote > 0 else "negativo" if macd_vote < 0 else "neutro",
        },
        "candles": candles,
        "ema20Series": [round(value, 8) if value is not None else None for value in ema20],
    }


def crypto_symbols(query):
    now = time.time()
    if now >= SYMBOL_CACHE["expires_at"]:
        payload = request_json("https://api.binance.com/api/v3/exchangeInfo")
        symbols = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(symbols, list):
            message = payload.get("msg") if isinstance(payload, dict) else None
            raise MarketDataError(message or "Não foi possível carregar os símbolos da Binance.")
        SYMBOL_CACHE["symbols"] = [
            item for item in symbols
            if item.get("status") == "TRADING" and item.get("isSpotTradingAllowed", True)
        ]
        SYMBOL_CACHE["expires_at"] = now + 3600

    search = query.upper()
    matches = [
        item
        for item in SYMBOL_CACHE["symbols"]
        if search in item.get("symbol", "") or search in item.get("baseAsset", "")
    ]
    matches = sorted(
        matches,
        key=lambda item: (
            item["symbol"] != search,
            item["baseAsset"] != search,
            not item["baseAsset"].startswith(search),
            {"USDT": 0, "USDC": 1, "FDUSD": 2, "BUSD": 3}.get(item["quoteAsset"], 4),
            item["symbol"],
        ),
    )[:12]
    return [
        {
            "symbol": item["symbol"],
            "name": f'{item["baseAsset"]} / {item["quoteAsset"]}',
        }
        for item in matches
    ]


def search_twelve_data(market, query):
    params = urlencode({"symbol": query, "apikey": get_twelve_data_key()})
    payload = request_json(f"https://api.twelvedata.com/symbol_search?{params}")
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise MarketDataError(payload.get("message", "Falha na busca de ativos do Twelve Data."))
    values = payload.get("data", []) if isinstance(payload, dict) else []
    expected_type = "forex" if market == "forex" else "stock"
    matches = []
    for item in values:
        instrument_type = str(item.get("instrument_type", "")).lower()
        if expected_type not in instrument_type:
            continue
        matches.append({
            "symbol": item.get("symbol", ""),
            "name": item.get("instrument_name") or item.get("name") or item.get("symbol", ""),
            "exchange": item.get("exchange", ""),
        })
    return matches[:12]


class TraderVelasHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "src"), **kwargs)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/analysis":
            self.handle_analysis(parse_qs(parsed_url.query))
            return
        if parsed_url.path == "/api/search":
            self.handle_search(parse_qs(parsed_url.query))
            return
        if parsed_url.path == "/api/news":
            self.handle_news(parse_qs(parsed_url.query))
            return
        if parsed_url.path == "/api/config":
            self.handle_config()
            return
        if parsed_url.path.startswith("/api/"):
            self.send_json(404, {"error": "Rota não encontrada."})
            return
        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/image-analysis":
            self.send_json(404, {"error": "Rota não encontrada."})
            return
        origin = self.headers.get("Origin", "")
        permitted_origins = {
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        }
        permitted_origins.update(
            item.strip()
            for item in os.environ.get("TRADER_VELAS_ALLOWED_ORIGINS", "").split(",")
            if item.strip()
        )
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "http").split(",", 1)[0].strip()
        host = self.headers.get("Host", "").strip()
        if forwarded_proto in {"http", "https"} and host and "\r" not in host and "\n" not in host:
            permitted_origins.add(f"{forwarded_proto}://{host}")
        if origin not in permitted_origins:
            self.send_json(403, {"error": "A análise de imagem só pode ser usada pelo site local."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Tamanho da requisição inválido."})
            return
        if length <= 0 or length > ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 16384:
            self.send_json(413, {"error": "A imagem deve ter no máximo 5 MB."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise AnalysisError("Dados da análise inválidos.")
            provider = image_analysis_provider()
            if provider == "gemini" and not reserve_gemini_request():
                self.send_json(429, {"error": "O limite diário de análises gratuitas deste site foi atingido. Tente novamente amanhã."})
                return
            explanation = analyze_image(
                payload.get("image"),
                payload.get("topic"),
                payload.get("headlines"),
                consent=payload.get("consent", False),
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Dados da análise inválidos."})
            return
        except AnalysisError as error:
            self.send_json(400, {"error": str(error)})
            return
        self.send_json(200, {"explanation": explanation})

    def handle_config(self):
        try:
            provider = image_analysis_provider()
        except AnalysisError as error:
            self.send_json(503, {"error": str(error)})
            return
        self.send_json(200, {
            "imageAnalysisProvider": provider,
            "imageConsentRequired": provider == "gemini",
        })

    def handle_news(self, query):
        try:
            topic = validate_topic(query.get("topic", [""])[0])
        except AnalysisError as error:
            self.send_json(400, {"error": str(error)})
            return
        try:
            result = fetch_news(topic)
        except AnalysisError as error:
            self.send_json(502, {"error": str(error)})
            return
        self.send_json(200, result)

    def handle_analysis(self, query):
        market = query.get("market", [""])[0]
        symbol = query.get("symbol", [""])[0].strip()
        interval = query.get("interval", [""])[0]
        if market not in MARKETS:
            self.send_json(400, {"error": "Selecione um mercado válido."})
            return
        if not SYMBOL_PATTERN.fullmatch(symbol):
            self.send_json(400, {"error": "Informe um símbolo válido, como BTCUSDT, AAPL ou EUR/USD."})
            return
        if interval not in INTERVALS:
            self.send_json(400, {"error": "Selecione um intervalo válido."})
            return
        try:
            candles = get_candles(market, symbol, interval)
            result = analyze_candles(candles)
        except MarketDataError as error:
            self.send_json(502, {"error": str(error)})
            return
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            logging.exception("Invalid provider data for %s %s", market, symbol)
            self.send_json(502, {"error": "O provedor retornou dados incompletos para este ativo."})
            return
        self.send_json(200, {
            "market": market,
            "symbol": symbol.upper(),
            "interval": interval,
            **result,
        })

    def handle_search(self, query):
        market = query.get("market", [""])[0]
        term = query.get("q", [""])[0].strip()
        if market not in MARKETS:
            self.send_json(400, {"error": "Selecione um mercado válido."})
            return
        if len(term) < 2 or len(term) > 32 or not SYMBOL_PATTERN.fullmatch(term):
            self.send_json(400, {"error": "Digite pelo menos 2 caracteres para buscar."})
            return
        try:
            results = crypto_symbols(term) if market == "crypto" else search_twelve_data(market, term)
        except MarketDataError as error:
            self.send_json(502, {"error": str(error)})
            return
        self.send_json(200, {"results": results})

    def log_message(self, format_string, *args):
        logging.info("%s - %s", self.address_string(), format_string % args)


def main():
    load_local_env()
    default_host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    host = os.environ.get("TRADER_VELAS_HOST", default_host)
    port = int(os.environ.get("PORT", os.environ.get("TRADER_VELAS_PORT", "8000")))
    server = ThreadingHTTPServer((host, port), TraderVelasHandler)
    logging.info("Trader Velas disponível em http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Encerrando servidor.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
