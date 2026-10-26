# Vai de Virada

Painel estático da apuração presidencial brasileira de 2026. Exibe a evolução da porcentagem de votos válidos dos dois finalistas, linhas horizontais pontilhadas do resultado nacional do 1º turno, tendências locais, inspeção por hover/toque, zoom e escala horizontal log(1 + % de urnas apuradas).

## Dados e limites

A fonte atual é a [totalização nacional do 2º turno do TSE](https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json) e a referência pontilhada é a [totalização do 1º turno](https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json). O navegador consulta diretamente o feed oficial a cada 30 segundos (CORS permitido para o domínio do Pages) e agrega novos registros sem recarregar; se falhar, mantém os últimos dados publicados. O GitHub Actions continua coletando a cada 5 minutos em `data/results.json`, com o cron e o deploy sujeitos a atraso.

Para mostrar o início do dia, foram importadas capturas do feed do TSE mantidas pelo [arquivo público Placar](https://placar-feed.nicolasqueiroga.workers.dev/history?race=presidente2&minutes=1440). A cópia original usada está preservada em `data/archive-2026-10-25.json`, com conversão verificável em `scripts/import_archive.py`. Somente capturas anteriores ao primeiro registro próprio (20h19) foram incorporadas; a série começa às **17h06**, primeiro registro disponível nesse arquivo, a 0,21% de urnas. Registros idênticos e regressivos são descartados. Uma amostra de 39,84% foi conferida contra uma leitura independente do arquivo oficial do TSE (24.444.579 votos Lula / 24.660.636 votos Flávio Bolsonaro). Pontos importados têm identificação de origem no tooltip; seu horário é o de captura, enquanto os pontos próprios exibem o horário da geração no TSE. Não se inferem dados anteriores às 17h06. A tendência extrapola linearmente os últimos até oito registros até 100% das urnas (limitada a percentuais de 0% a 100%): **não é pesquisa, previsão ou probabilidade de vitória**.

As curvas pontilhadas do primeiro turno vêm das [capturas nacionais arquivadas pelo Placar](https://placar-feed.nicolasqueiroga.workers.dev/history?race=presidente&from=1791142200000&to=1791216000000). `scripts/import_first_round.py` preserva em `data/first-round-history.json` 247 observações não duplicadas, de 1,42% a 100%, valida os votos finais contra o arquivo oficial do TSE e descarta registros inconsistentes. As porcentagens dos finalistas no 1º turno usam como denominador **todos os votos válidos** (12 candidatos), enquanto no 2º turno são somente os votos dos dois finalistas. O hover compara os dois turnos no mesmo percentual de urnas; valores intermediários do 1º turno são interpolados entre observações arquivadas. No trecho pontilhado de tendência do 2º turno, o tooltip indica explicitamente os valores **projetados** naquele percentual e que não são resultados oficiais.

Na interface, o 1º turno aparece por padrão em uma faixa separada com linhas contínuas nas mesmas cores dos candidatos. O seletor **1º turno → Sobreposto** restaura as curvas pontilhadas sobre o gráfico principal. Escala linear/logarítmica e zoom são compartilhados entre as duas visualizações; a faixa separada também tem detalhes ao passar o mouse ou tocar.

O hover mostra votos e porcentagens por candidato em ambos os turnos. Nos registros arquivados do 1º turno, valores entre capturas são interpolados. Na projeção do 2º turno, o número de votos é **estimado**, não observado: calcula-se o total de votos válidos no percentual apontado multiplicando o total válido do último registro por `(urnas apontadas / urnas do último registro)` e aplica-se a participação projetada de cada candidato. Isso supõe ritmo constante de votos válidos por urna, apenas para leitura exploratória.

## A questão das 17h às 19h

A seção recolhível não atribui votos a candidatos sem evidência. A pergunta sobre o encerramento às 17h em 25/10/2026 não permite tratar todas as seções como se tivessem continuado a votar até as 19h. [Logs de urna contêm horário de votação, mas não o candidato escolhido](https://speedurna.furious.pro/sobre); boletins de urna (BU) contêm totais por seção, mas não horário de cada voto. Transmissão/totalização após as 17h não identifica voto depositado após as 17h. O [catálogo oficial de BU](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna) é consultado pelo workflow; `data/extension.json` guarda quais arquivos do 2º turno já foram publicados por UF e exterior. A seção atualiza essa disponibilidade sem refresh, mas **não** apresenta contagens de votos após 17h enquanto não houver cobertura de logs verificada.

Mesmo sem associação de horário a candidato, logs completos poderiam eventualmente estabelecer um limite: se o total de votações concluídas após 17h for menor que a margem **final** entre os candidatos, retirá-las não poderia mudar o vencedor. Se não for, os dados agregados ainda não permitem distribuir escolhas por horário. A margem exibida pela página é explicitamente provisória até que 100% das urnas sejam totalizadas.

## Publicação

Repositório público no GitHub, branch padrão `main`. Em **Settings → Pages → Build and deployment**, selecione **GitHub Actions**. O workflow `.github/workflows/pages.yml` também pode ser iniciado em **Actions → Collect and publish election data → Run workflow**. O workflow precisa de permissão para escrever no repositório (concedida via `permissions: contents: write`; configurações da organização podem restringir). Os arquivos publicados são HTML/CSS/JS estáticos, sem backend, credenciais ou dependências de build.

## Desenvolvimento

```bash
python3 scripts/update.py
python3 -m unittest discover -s tests -v
python3 -m http.server 8000
```

Abra `http://localhost:8000`. A coleta falha sem alterar o histórico se o TSE estiver indisponível ou retornar dados regressivos. A consulta direta depende da autorização CORS da origem que hospeda a página; em `localhost`, se ela falhar, a página continua usando `data/results.json`. Arquivos em `data/results.json` são observações reais; nunca simule pontos de apuração.
