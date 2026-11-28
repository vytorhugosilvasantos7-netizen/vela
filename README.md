# Vela — painel de análise de mercado

Painel web de leitura técnica para criptomoedas, ações e forex. Usa candles da API pública da Binance para cripto e da Twelve Data para ações/forex. A aplicação não envia ordens.

## Executar

Requer Python 3.10 ou superior; não há dependências externas.

```powershell
Copy-Item .env.example .env
# Edite .env e informe sua chave Twelve Data.
python .\server.py
```

Execute os comandos na pasta raiz do projeto e abra `http://127.0.0.1:8000`. O servidor lê a chave do arquivo local `.env`, que não deve ser compartilhado nem enviado ao Git; uma variável de ambiente já configurada tem prioridade. A chave é necessária apenas para buscar e analisar ações e forex; cripto usa endpoints públicos da Binance. O plano, as permissões por mercado e os limites da Twelve Data podem afetar a disponibilidade e a atualidade dos dados.

O GitHub Pages serve apenas os arquivos estáticos e não executa o servidor Python nem o Ollama. Publicar a página lá, por si só, não disponibiliza as APIs nem a análise de imagens; o uso por clientes online exige uma hospedagem de backend e uma configuração apropriada de IA.

Para encerrar o servidor, pressione `Ctrl+C`.

## Publicar uma demonstração gratuita

O GitHub Pages serve arquivos estáticos e não executa o servidor Python. Para experimentar o Vela online, use o Blueprint `render.yaml` com o serviço gratuito do Render; ele publica a página e a API no mesmo endereço.

1. Crie uma chave Gemini no [Google AI Studio](https://aistudio.google.com/apikey). Não a coloque no repositório, no código do navegador ou em mensagens públicas.
2. No Render, escolha **New → Blueprint**, conecte o repositório `vela` e confirme o serviço gratuito definido em `render.yaml`.
3. Quando solicitado, informe `GEMINI_API_KEY` diretamente no Render. O Blueprint seleciona `gemini-3.5-flash-lite`.
4. Abra o endereço `onrender.com` mostrado pelo Render. Use esse endereço em vez do GitHub Pages.

O modelo Gemini recebe a imagem e o contexto de manchetes apenas após o usuário marcar a autorização explícita. No nível gratuito, o Google pode usar o conteúdo para melhorar seus produtos. Não envie gráficos com nomes, números de conta ou outros dados pessoais. O Vela não grava as imagens em disco.

Esta é uma demonstração, não uma hospedagem de produção: serviços gratuitos do Render podem dormir após 15 minutos sem tráfego e levar cerca de um minuto para reativar; cotas gratuitas do Gemini podem mudar ou acabar. O servidor limita análises de imagem a 30 por dia por instância, mas esse limite em memória reinicia quando o serviço reinicia. Não há login ou proteção contra abuso distribuído; não ofereça publicamente como serviço comercial sem adicionar autenticação, cotas persistentes, monitoramento e controles de privacidade.

## Análise de imagem e notícias

1. Instale o [Ollama para Windows](https://ollama.com/download) e deixe-o em execução.
2. No PowerShell, baixe o modelo de visão local: `ollama pull qwen2.5vl:3b`. O download tem aproximadamente 3,2 GB e precisa de memória e espaço livres; a análise pode levar vários minutos em computadores mais lentos.
3. Reinicie o servidor do Vela, acesse `http://127.0.0.1:8000` e escolha uma imagem PNG, JPEG ou WebP de até 5 MB. Informe o nome ou símbolo público do ativo para a busca de notícias.

A leitura aparece no painel à esquerda das notícias após a análise. O andamento e os erros são exibidos nesse painel; aguarde com a página aberta, pois o processamento pode levar vários minutos.

A imagem é processada pelo Ollama em `127.0.0.1` quando `IMAGE_ANALYSIS_PROVIDER=ollama`. O nome informado para a busca é enviado ao Google Notícias; são consultadas as edições Brasil e EUA, buscando até oito manchetes dos últimos sete dias. A lista tem fontes, datas e links, mas não cobre todas as notícias do mundo. A IA recebe apenas as manchetes, não o texto dos artigos; consulte as fontes originais antes de tirar conclusões. Se a busca falhar, o site informa o erro e tenta analisar a imagem sem notícias.

O Ollama e o modelo são necessários para a leitura da imagem. A análise usa a CPU para evitar erros de GPU e pode demorar vários minutos. Ela tenta explicar o que aparece, cenários condicionais e conceitos para estudar. Pode interpretar o gráfico incorretamente, inventar detalhes ou ignorar informações; confira a imagem e os valores e use os cenários apenas para fins educacionais. Prefira imagens nítidas, com o ativo, período e escalas visíveis.

## Como a leitura é calculada

O sinal combina tendência por EMA 20/50, RSI 14 e histograma MACD 12/26/9. A confluência mede apenas o alinhamento desses três indicadores; **não é uma probabilidade calibrada, previsão garantida ou recomendação de investimento**. A análise usa dados históricos e pode falhar.

## Testes

```powershell
python -m unittest discover -s tests
```
