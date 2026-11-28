const imageForm = document.querySelector("#image-form");
const imageInput = document.querySelector("#chart-image");
const newsTopic = document.querySelector("#news-topic");
const imageSubmit = document.querySelector("#image-submit");
const imageConsent = document.querySelector("#image-consent");
const imageConsentWrap = document.querySelector("#image-consent-wrap");
const imagePrivacy = document.querySelector("#image-privacy");
const imageProviderBadge = document.querySelector("#image-provider-badge");
const imagePreview = document.querySelector("#image-preview");
const imageError = document.querySelector("#image-error");
const imageStatus = document.querySelector("#image-status");
const imageResult = document.querySelector("#image-result");
const imageExplanation = document.querySelector("#image-explanation");
const newsStatus = document.querySelector("#news-status");
const newsList = document.querySelector("#news-list");
const maxImageBytes = 5 * 1024 * 1024;
let previewUrl = null;
let imageAnalysisConfig = null;
let imageConfigError = null;

async function loadImageConfig() {
  try {
    imageAnalysisConfig = await getJson("/api/config");
    const usesGemini = imageAnalysisConfig.imageAnalysisProvider === "gemini";
    imageProviderBadge.textContent = usesGemini ? "IA ONLINE" : "IA LOCAL";
    imageConsentWrap.hidden = !imageAnalysisConfig.imageConsentRequired;
    imagePrivacy.textContent = usesGemini
      ? "A imagem será enviada ao servidor e ao Google Gemini. No nível gratuito, o Google pode usar o conteúdo para melhorar produtos. Não envie imagens com dados pessoais; o Vela não guarda o arquivo. O nome do ativo é consultado no Google Notícias."
      : "A imagem é analisada localmente pelo Ollama e não é enviada à IA online. O nome do ativo é consultado no Google Notícias.";
  } catch (error) {
    imageConfigError = error.message;
    imageStatus.textContent = "Não foi possível verificar a configuração da análise.";
  }
}

const imageConfigReady = loadImageConfig();

function showImageError(message) {
  imageError.textContent = message;
  imageError.hidden = false;
}

function resetImageResult() {
  imageResult.hidden = true;
  imageExplanation.textContent = "";
  imageError.hidden = true;
  imageConsent.checked = false;
  imageStatus.textContent = "Escolha uma imagem e informe o ativo para iniciar a análise.";
  newsStatus.textContent = "Informe o ativo e escolha uma imagem para começar.";
  newsList.replaceChildren();
}

function readImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(new Error("Não foi possível ler a imagem selecionada."));
    reader.readAsDataURL(file);
  });
}

function showNews(data) {
  newsList.replaceChildren();
  for (const article of data.articles) {
    let url;
    try {
      url = new URL(article.url);
    } catch {
      continue;
    }
    if (url.protocol !== "https:" || url.hostname !== "news.google.com") continue;
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = article.title;
    const details = document.createElement("small");
    const date = new Date(article.date);
    const dateText = Number.isNaN(date.getTime())
      ? "Data não disponível"
      : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
    details.textContent = `${article.source} · ${dateText} · Edição ${article.edition}`;
    item.append(link, details);
    newsList.append(item);
  }
  const count = newsList.children.length;
  newsStatus.textContent = count
    ? `${count} manchete(s) encontrada(s). Abra as fontes para verificar o contexto.${data.warning ? ` ${data.warning}` : ""}`
    : `Nenhuma manchete encontrada para este termo nos feeds consultados.${data.warning ? ` ${data.warning}` : ""}`;
}

imageInput.addEventListener("change", () => {
  resetImageResult();
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  imagePreview.hidden = true;
  const file = imageInput.files[0];
  if (!file) return;
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > maxImageBytes) {
    showImageError("Escolha uma imagem PNG, JPEG ou WebP de até 5 MB.");
    return;
  }
  imageError.hidden = true;
  previewUrl = URL.createObjectURL(file);
  imagePreview.src = previewUrl;
  imagePreview.hidden = false;
});

newsTopic.addEventListener("input", resetImageResult);

imageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  imageError.hidden = true;
  imageResult.hidden = true;
  imageStatus.textContent = "Confira os dados informados e tente novamente.";
  newsList.replaceChildren();
  const file = imageInput.files[0];
  const topic = newsTopic.value.trim();
  if (window.location.protocol === "file:") {
    showImageError('Abra o site pelo servidor: execute "Abrir Vela.bat" na pasta do projeto.');
    return;
  }
  if (!file || !["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > maxImageBytes) {
    showImageError("Escolha uma imagem PNG, JPEG ou WebP de até 5 MB.");
    return;
  }
  if (!/^[\p{L}\p{N} .&/_-]{2,60}$/u.test(topic)) {
    showImageError("Informe o nome ou símbolo público do ativo, com 2 a 60 caracteres.");
    return;
  }

  imageSubmit.disabled = true;
  imageInput.disabled = true;
  newsTopic.disabled = true;
  imageSubmit.textContent = "Consultando...";
  newsStatus.textContent = "Buscando notícias públicas...";
  imageStatus.textContent = "Buscando notícias antes de analisar a imagem. Mantenha esta página aberta.";
  let headlines = [];
  try {
    await imageConfigReady;
    if (!imageAnalysisConfig) {
      throw new Error(imageConfigError || "O servidor não informou como a imagem será processada.");
    }
    if (imageAnalysisConfig.imageConsentRequired && !imageConsent.checked) {
      throw new Error("Leia o aviso e marque a autorização para enviar esta imagem ao Google Gemini.");
    }
    try {
      const params = new URLSearchParams({ topic });
      const news = await getJson(`/api/news?${params}`);
      showNews(news);
      headlines = news.articles.map((article) => article.title);
    } catch (error) {
      newsStatus.textContent = `Notícias indisponíveis: ${error.message}. A análise continuará sem manchetes.`;
    }
    const image = await readImage(file);
    imageStatus.textContent = imageAnalysisConfig.imageAnalysisProvider === "gemini"
      ? "Analisando a imagem com o Google Gemini..."
      : "Analisando a imagem no Ollama local. Isso pode levar vários minutos...";
    const result = await getJson("/api/image-analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image, topic, headlines, consent: imageConsent.checked }),
    });
    if (typeof result.explanation !== "string" || !result.explanation.trim()) {
      throw new Error("A análise não retornou uma explicação. Tente novamente.");
    }
    imageExplanation.textContent = result.explanation;
    imageResult.hidden = false;
    imageStatus.textContent = "Análise concluída. Confira a leitura abaixo.";
  } catch (error) {
    imageStatus.textContent = "Não foi possível concluir a análise.";
    showImageError(error.message);
  } finally {
    imageSubmit.disabled = false;
    imageInput.disabled = false;
    newsTopic.disabled = false;
    imageSubmit.textContent = "Analisar imagem";
  }
});
