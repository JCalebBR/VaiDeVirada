# Vai de Virada

Painel estático da apuração presidencial brasileira de 2026. Exibe a evolução da porcentagem de votos válidos dos dois finalistas, linhas horizontais pontilhadas do resultado nacional do 1º turno, tendências locais, inspeção por hover/toque, zoom e escala horizontal log(1 + % de urnas apuradas).

## Dados e limites

A fonte atual é a [totalização nacional do 2º turno do TSE](https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json) e a referência pontilhada é a [totalização do 1º turno](https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json). O navegador consulta diretamente o feed oficial a cada 30 segundos (CORS permitido para o domínio do Pages) e agrega novos registros sem recarregar; se falhar, mantém os últimos dados publicados. O GitHub Actions continua coletando a cada 5 minutos em `data/results.json`, com o cron e o deploy sujeitos a atraso.

Para mostrar o início do dia, foram importadas capturas do feed do TSE mantidas pelo [arquivo público Placar](https://placar-feed.nicolasqueiroga.workers.dev/history?race=presidente2&minutes=1440). A cópia original usada está preservada em `data/archive-2026-10-25.json`, com conversão verificável em `scripts/import_archive.py`. Somente capturas anteriores ao primeiro registro próprio (20h19) foram incorporadas; a série começa às **17h06**, primeiro registro disponível nesse arquivo, a 0,21% de urnas. Registros idênticos e regressivos são descartados. Uma amostra de 39,84% foi conferida contra uma leitura independente do arquivo oficial do TSE (24.444.579 votos Lula / 24.660.636 votos Flávio Bolsonaro). Pontos importados têm identificação de origem no tooltip; seu horário é o de captura, enquanto os pontos próprios exibem o horário da geração no TSE. Não se inferem dados anteriores às 17h06. A tendência extrapola linearmente os últimos até oito registros por um trecho curto: **não é pesquisa, previsão ou probabilidade de vitória**.

## Publicação

Repositório público no GitHub, branch padrão `main`. Em **Settings → Pages → Build and deployment**, selecione **GitHub Actions**. O workflow `.github/workflows/pages.yml` também pode ser iniciado em **Actions → Collect and publish election data → Run workflow**. O workflow precisa de permissão para escrever no repositório (concedida via `permissions: contents: write`; configurações da organização podem restringir). Os arquivos publicados são HTML/CSS/JS estáticos, sem backend, credenciais ou dependências de build.

## Desenvolvimento

```bash
python3 scripts/update.py
python3 -m unittest discover -s tests -v
python3 -m http.server 8000
```

Abra `http://localhost:8000`. A coleta falha sem alterar o histórico se o TSE estiver indisponível ou retornar dados regressivos. A consulta direta depende da autorização CORS da origem que hospeda a página; em `localhost`, se ela falhar, a página continua usando `data/results.json`. Arquivos em `data/results.json` são observações reais; nunca simule pontos de apuração.
