const form = document.querySelector("#analysis-form");
const marketSelect = document.querySelector("#market-select");
const symbolInput = document.querySelector("#symbol-input");
const intervalSelect = document.querySelector("#interval-select");
const searchResults = document.querySelector("#search-results");
const errorMessage = document.querySelector("#error-message");
const analyzeButton = document.querySelector(".analyze-button");
const canvas = document.querySelector("#price-chart");
const chartEmpty = document.querySelector("#chart-empty");

const marketNames = {
  crypto: "Criptomoeda",
  stocks: "Ação",
  forex: "Forex",
};
const defaults = {
  crypto: "BTCUSDT",
  stocks: "AAPL",
  forex: "EUR/USD",
};
const directions = {
  alta: { label: "Viés de alta", icon: "↑", className: "bullish" },
  baixa: { label: "Viés de baixa", icon: "↓", className: "bearish" },
  lateral: { label: "Movimento lateral", icon: "↔", className: "neutral" },
};
const indicatorLabels = {
  positivo: "positivo",
  negativo: "negativo",
  neutro: "neutro",
};

let latestAnalysis = null;
let searchTimer = null;
let activeSearchController = null;

document.querySelector("#current-date").textContent = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
}).format(new Date());

function formatNumber(value, maximumFractionDigits = 2) {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: Math.min(2, maximumFractionDigits),
    maximumFractionDigits,
  }).format(value);
}

function safeText(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    if (window.location.hostname.endsWith(".github.io")) {
      throw new Error("O GitHub Pages não executa o servidor do Vela. Para usar análises online, é necessário hospedar o servidor e configurar a IA.");
    }
    throw new Error(`O servidor retornou uma resposta inválida (HTTP ${response.status}). Verifique se o servidor do Vela está em execução.`);
  }
  if (!response.ok) {
    throw new Error(payload.error || "Não foi possível concluir a consulta.");
  }
  return payload;
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function clearError() {
  errorMessage.textContent = "";
  errorMessage.hidden = true;
}

function updateActiveWatchItem() {
  document.querySelectorAll(".watch-item").forEach((item) => {
    const selected = item.dataset.market === marketSelect.value
      && item.dataset.symbol === symbolInput.value.trim().toUpperCase();
    item.classList.toggle("selected", selected);
  });
}

function drawAnalysis(data) {
  const direction = directions[data.direction] || directions.lateral;
  const signalCard = document.querySelector("#signal-card");
  signalCard.className = `signal-card ${direction.className}`;
  document.querySelector("#signal-direction").textContent = direction.label;
  document.querySelector("#signal-icon").textContent = direction.icon;
  document.querySelector("#confluence-value").textContent = `${data.confluence}%`;
  const confluenceBar = document.querySelector("#confluence-bar");
  confluenceBar.style.width = `${data.confluence}%`;
  confluenceBar.classList.toggle("bearish", data.direction === "baixa");

  const symbol = data.symbol.toUpperCase();
  const market = data.market;
  document.querySelector("#asset-name").textContent = getAssetName(market, symbol);
  document.querySelector("#asset-symbol").textContent = formatSymbol(market, symbol);
  document.querySelector("#market-label").textContent = marketNames[market];
  document.querySelector("#market-badge").textContent = market === "crypto" ? "SPOT" : market === "stocks" ? "AÇÃO" : "FX";
  document.querySelector("#asset-icon").textContent = market === "crypto"
    ? (symbol.startsWith("ETH") ? "◆" : symbol.startsWith("BTC") ? "₿" : "◈")
    : market === "forex" ? "↔" : "A";

  document.querySelector("#latest-price").textContent = formatNumber(data.latest, 8);
  const change = document.querySelector("#price-change");
  const sign = data.change > 0 ? "+" : "";
  change.textContent = `${sign}${formatNumber(data.change, 2)}%`;
  change.className = `change-value ${data.change > 0 ? "positive" : data.change < 0 ? "negative" : ""}`;

  const rsiValue = data.rsi === null ? "—" : formatNumber(data.rsi, 1);
  document.querySelector("#rsi-value").textContent = rsiValue;
  const rsiState = data.rsi === null
    ? "Sem dados"
    : data.rsi >= 70 ? "Sobrecomprado" : data.rsi <= 30 ? "Sobrevendido" : "Faixa neutra";
  document.querySelector("#rsi-state").textContent = rsiState;
  document.querySelector("#rsi-marker").style.left = `${Math.max(1, Math.min(99, data.rsi || 50))}%`;

  for (const [key, elementId] of [
    ["trend", "trend-indicator"],
    ["rsi", "rsi-indicator"],
    ["macd", "macd-indicator"],
  ]) {
    const indicator = document.querySelector(`#${elementId}`);
    const value = data.indicators[key];
    indicator.textContent = indicatorLabels[value] || "neutro";
    indicator.className = value === "positivo" ? "positive" : value === "negativo" ? "negative" : "";
  }

  document.querySelector("#chart-interval").textContent = data.interval.toUpperCase();
  const first = data.candles[0];
  const last = data.candles[data.candles.length - 1];
  document.querySelector("#chart-range").textContent = `${formatDate(first.time)} — ${formatDate(last.time)}`;
  chartEmpty.hidden = true;
  latestAnalysis = data;
  drawChart(data);
  document.querySelector("#updated-at").textContent = `Atualizado às ${new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date())}`;
  updateActiveWatchItem();
}

function formatSymbol(market, symbol) {
  if (market === "crypto") {
    const quotes = ["USDT", "USDC", "FDUSD", "TUSD", "BUSD", "BTC", "ETH", "BNB", "TRY", "EUR", "BRL", "DAI"];
    const quote = quotes.find((candidate) => symbol.endsWith(candidate) && symbol.length > candidate.length);
    if (quote) return `${symbol.slice(0, -quote.length)} / ${quote}`;
  }
  if (market === "forex" && symbol.includes("/")) {
    return symbol.toUpperCase();
  }
  return symbol.toUpperCase();
}

function getAssetName(market, symbol) {
  const known = {
    BTCUSDT: "Bitcoin",
    ETHUSDT: "Ethereum",
    BNBUSDT: "BNB",
    SOLUSDT: "Solana",
    XRPUSDT: "XRP",
    AAPL: "Apple",
    MSFT: "Microsoft",
    NVDA: "NVIDIA",
    TSLA: "Tesla",
    "EUR/USD": "Euro / Dólar",
    "GBP/USD": "Libra / Dólar",
    "USD/JPY": "Dólar / Iene",
  };
  return known[symbol] || (market === "crypto" ? symbol.replace(/USDT$/, "") : symbol);
}

function formatDate(value) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(date);
}

function drawChart(data) {
  const bounds = canvas.getBoundingClientRect();
  if (bounds.width === 0 || bounds.height === 0) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(bounds.width * ratio);
  canvas.height = Math.round(bounds.height * ratio);
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);

  const width = bounds.width;
  const height = bounds.height;
  const padding = { top: 10, right: 8, bottom: 23, left: 53 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const candles = data.candles;
  const values = candles.flatMap((candle, index) => [
    candle.low,
    candle.high,
    data.ema20Series[index],
  ]).filter(Number.isFinite);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const gap = Math.max((maximum - minimum) * 0.1, Math.abs(maximum) * 0.0005, 0.000001);
  const chartMin = minimum - gap;
  const chartMax = maximum + gap;
  const priceHeight = plotHeight * 0.81;
  const y = (value) => padding.top + ((chartMax - value) / (chartMax - chartMin)) * priceHeight;
  const x = (index) => padding.left + index / Math.max(candles.length - 1, 1) * plotWidth;

  context.clearRect(0, 0, width, height);
  context.font = "9px DM Sans, sans-serif";
  context.textBaseline = "middle";
  for (let line = 0; line <= 4; line += 1) {
    const lineY = padding.top + (priceHeight / 4) * line;
    const value = chartMax - ((chartMax - chartMin) / 4) * line;
    context.beginPath();
    context.strokeStyle = "#25313a";
    context.lineWidth = 1;
    context.setLineDash([3, 5]);
    context.moveTo(padding.left, lineY);
    context.lineTo(width - padding.right, lineY);
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = "#76838c";
    context.textAlign = "right";
    context.fillText(formatNumber(value, 4), padding.left - 8, lineY);
  }

  const maxVolume = Math.max(...candles.map((candle) => candle.volume), 0);
  if (maxVolume > 0) {
    const barWidth = Math.max(1, plotWidth / candles.length * 0.55);
    candles.forEach((candle, index) => {
      const barHeight = (candle.volume / maxVolume) * plotHeight * 0.13;
      context.fillStyle = candle.close >= candle.open ? "#3fbd9138" : "#df747638";
      context.fillRect(x(index) - barWidth / 2, height - padding.bottom - barHeight, barWidth, barHeight);
    });
  }

  context.beginPath();
  context.strokeStyle = "#43d2a2";
  context.lineWidth = 1.8;
  context.lineJoin = "round";
  candles.forEach((candle, index) => {
    if (index === 0) context.moveTo(x(index), y(candle.close));
    else context.lineTo(x(index), y(candle.close));
  });
  context.stroke();

  context.beginPath();
  context.strokeStyle = "#d4ae6e";
  context.lineWidth = 1.35;
  let started = false;
  data.ema20Series.forEach((value, index) => {
    if (!Number.isFinite(value)) return;
    if (!started) {
      context.moveTo(x(index), y(value));
      started = true;
    } else {
      context.lineTo(x(index), y(value));
    }
  });
  context.stroke();

  context.fillStyle = "#74818b";
  context.textAlign = "left";
  context.fillText(formatDate(candles[0].time), padding.left, height - 8);
  context.textAlign = "right";
  context.fillText(formatDate(candles[candles.length - 1].time), width - padding.right, height - 8);
}

async function analyze() {
  clearError();
  searchResults.hidden = true;
  const market = marketSelect.value;
  const symbol = symbolInput.value.trim();
  const interval = intervalSelect.value;
  if (!symbol) {
    showError("Informe o símbolo do ativo que deseja analisar.");
    symbolInput.focus();
    return;
  }

  analyzeButton.disabled = true;
  analyzeButton.querySelector("span").textContent = "Consultando...";
  try {
    const params = new URLSearchParams({ market, symbol, interval });
    const data = await getJson(`/api/analysis?${params}`);
    drawAnalysis(data);
  } catch (error) {
    showError(error.message);
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.querySelector("span").textContent = "Analisar ativo";
  }
}

async function searchSymbols(term) {
  if (term.trim().length < 2) {
    searchResults.hidden = true;
    return;
  }
  if (activeSearchController) activeSearchController.abort();
  activeSearchController = new AbortController();
  searchResults.hidden = false;
  searchResults.innerHTML = '<div class="search-message">Buscando ativos...</div>';
  try {
    const params = new URLSearchParams({ market: marketSelect.value, q: term.trim() });
    const data = await getJson(`/api/search?${params}`, { signal: activeSearchController.signal });
    if (data.results.length === 0) {
      searchResults.innerHTML = '<div class="search-message">Nenhum ativo encontrado. Você também pode informar o símbolo manualmente.</div>';
      return;
    }
    searchResults.innerHTML = data.results.map((result) => `
      <button class="search-option" type="button" role="option" data-symbol="${safeText(result.symbol)}">
        <span>${safeText(result.name || result.symbol)}</span>
        <span>${safeText(result.symbol)}${result.exchange ? ` · ${safeText(result.exchange)}` : ""}</span>
      </button>
    `).join("");
  } catch (error) {
    if (error.name === "AbortError") return;
    searchResults.innerHTML = `<div class="search-message">${safeText(error.message)}</div>`;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (window.location.protocol === "file:") {
    showError("A página abriu sem o servidor. Feche-a e execute \"Abrir Vela.bat\" na pasta trader-velas para carregar os gráficos.");
  } else {
    analyze();
  }
});

symbolInput.addEventListener("input", () => {
  clearError();
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => searchSymbols(symbolInput.value), 300);
  updateActiveWatchItem();
});

marketSelect.addEventListener("change", () => {
  clearError();
  symbolInput.value = defaults[marketSelect.value];
  searchResults.hidden = true;
  updateActiveWatchItem();
});

searchResults.addEventListener("click", (event) => {
  const option = event.target.closest(".search-option");
  if (!option) return;
  symbolInput.value = option.dataset.symbol;
  searchResults.hidden = true;
  updateActiveWatchItem();
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".symbol-input-wrap")) searchResults.hidden = true;
});

document.querySelectorAll(".watch-item").forEach((item) => {
  item.addEventListener("click", () => {
    marketSelect.value = item.dataset.market;
    symbolInput.value = item.dataset.symbol;
    updateActiveWatchItem();
    analyze();
  });
});

window.addEventListener("resize", () => {
  if (latestAnalysis) drawChart(latestAnalysis);
});

analyze();
