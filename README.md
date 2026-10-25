# Vai de Virada

Painel estático da apuração presidencial brasileira de 2026. Exibe a evolução da porcentagem de votos válidos dos dois finalistas, linhas horizontais pontilhadas do resultado nacional do 1º turno, tendências locais, inspeção por hover/toque, zoom e escala horizontal log(1 + % de urnas apuradas).

## Dados e limites

A fonte é a [totalização nacional do 2º turno do TSE](https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json) e a [totalização do 1º turno](https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json). Os snapshots são coletados pelo GitHub Actions a cada 5 minutos, mantidos em `data/results.json` e publicados pelo GitHub Pages. O cron do GitHub e o deploy podem sofrer atraso; o site consulta o arquivo publicado a cada 90 segundos. O timestamp exibido é o da totalização do TSE, horário de Brasília. O histórico começa quando a coleta do projeto começa; não existe reconstrução retroativa. A tendência extrapola linearmente os últimos até oito registros por um trecho curto: **não é pesquisa, previsão ou probabilidade de vitória**.

## Publicação

Repositório público no GitHub, branch padrão `main`. Em **Settings → Pages → Build and deployment**, selecione **GitHub Actions**. O workflow `.github/workflows/pages.yml` também pode ser iniciado em **Actions → Collect and publish election data → Run workflow**. O workflow precisa de permissão para escrever no repositório (concedida via `permissions: contents: write`; configurações da organização podem restringir). Os arquivos publicados são HTML/CSS/JS estáticos, sem backend, credenciais ou dependências de build.

## Desenvolvimento

```bash
python3 scripts/update.py
python3 -m unittest discover -s tests -v
python3 -m http.server 8000
```

Abra `http://localhost:8000`. A coleta falha sem alterar o histórico se o TSE estiver indisponível ou retornar dados regressivos. Arquivos em `data/results.json` são observações reais; nunca simule pontos de apuração.
