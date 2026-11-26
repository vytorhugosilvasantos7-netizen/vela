# Vela — painel de análise de mercado

Painel web de leitura técnica para criptomoedas, ações e forex. Usa candles da API pública da Binance para cripto e da Twelve Data para ações/forex. A aplicação não envia ordens.

## Executar

Requer Python 3.10 ou superior; não há dependências externas.

```powershell
cd .\trader-velas
Copy-Item .env.example .env
# Edite .env e informe sua chave Twelve Data.
python .\server.py
```

Abra `http://127.0.0.1:8000`. O servidor lê a chave do arquivo local `.env`, que não deve ser compartilhado nem enviado ao Git; uma variável de ambiente já configurada tem prioridade. A chave é necessária apenas para buscar e analisar ações e forex; cripto usa endpoints públicos da Binance. O plano, as permissões por mercado e os limites da Twelve Data podem afetar a disponibilidade e a atualidade dos dados.

O GitHub Pages serve apenas os arquivos estáticos e não executa o servidor Python nem o Ollama. Publicar a página lá, por si só, não disponibiliza as APIs nem a análise de imagens; o uso por clientes online exige uma hospedagem de backend e uma configuração apropriada de IA.

Para encerrar o servidor, pressione `Ctrl+C`.

## Análise de imagem e notícias

1. Instale o [Ollama para Windows](https://ollama.com/download) e deixe-o em execução.
2. No PowerShell, baixe o modelo de visão local: `ollama pull qwen2.5vl:3b`. O download tem aproximadamente 3,2 GB e precisa de memória e espaço livres; a análise pode levar vários minutos em computadores mais lentos.
3. Reinicie o servidor do Vela, acesse `http://127.0.0.1:8000` e escolha uma imagem PNG, JPEG ou WebP de até 5 MB. Informe o nome ou símbolo público do ativo para a busca de notícias.

A leitura aparece no painel à esquerda das notícias após a análise. O andamento e os erros são exibidos nesse painel; aguarde com a página aberta, pois o processamento pode levar vários minutos.

A imagem é enviada apenas ao Ollama em `127.0.0.1` e não é salva pelo Vela. O nome informado para a busca é enviado ao Google Notícias; são consultadas as edições Brasil e EUA, buscando até oito manchetes dos últimos sete dias. A lista tem fontes, datas e links, mas não cobre todas as notícias do mundo. A IA recebe apenas as manchetes, não o texto dos artigos; consulte as fontes originais antes de tirar conclusões. Se a busca falhar, o site informa o erro e tenta analisar a imagem sem notícias.

O Ollama e o modelo são necessários para a leitura da imagem. A análise usa a CPU para evitar erros de GPU e pode demorar vários minutos. Ela tenta explicar o que aparece, cenários condicionais e conceitos para estudar. Pode interpretar o gráfico incorretamente, inventar detalhes ou ignorar informações; confira a imagem e os valores e use os cenários apenas para fins educacionais. Prefira imagens nítidas, com o ativo, período e escalas visíveis.

## Como a leitura é calculada

O sinal combina tendência por EMA 20/50, RSI 14 e histograma MACD 12/26/9. A confluência mede apenas o alinhamento desses três indicadores; **não é uma probabilidade calibrada, previsão garantida ou recomendação de investimento**. A análise usa dados históricos e pode falhar.

## Testes

```powershell
python -m unittest discover -s tests
```
