# Vai de Virada

Painel estático da apuração presidencial brasileira de 2026. Exibe a evolução da porcentagem de votos válidos dos dois finalistas, linhas horizontais pontilhadas do resultado nacional do 1º turno, tendências locais, inspeção por hover/toque, zoom e escala horizontal log(1 + % de urnas apuradas).

Para retomar o trabalho: [`HANDOFF.md`](HANDOFF.md). Evidências, URLs dos arquivos individuais e plano de auditoria: [`docs/urna-logs.md`](docs/urna-logs.md).

## Dados e limites

A fonte atual é a [totalização nacional do 2º turno do TSE](https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json) e a referência pontilhada é a [totalização do 1º turno](https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json). O navegador consulta diretamente o feed oficial a cada 30 segundos (CORS permitido para o domínio do Pages) e agrega novos registros sem recarregar; se falhar, mantém os últimos dados publicados. O GitHub Actions continua coletando a cada 5 minutos em `data/results.json`, com o cron e o deploy sujeitos a atraso.

Para mostrar o início do dia, foram importadas capturas do feed do TSE mantidas pelo [arquivo público Placar](https://placar-feed.nicolasqueiroga.workers.dev/history?race=presidente2&minutes=1440). A cópia original usada está preservada em `data/archive-2026-10-25.json`, com conversão verificável em `scripts/import_archive.py`. Somente capturas anteriores ao primeiro registro próprio (20h19) foram incorporadas; a série começa às **17h06**, primeiro registro disponível nesse arquivo, a 0,21% de urnas. Registros idênticos e regressivos são descartados. Uma amostra de 39,84% foi conferida contra uma leitura independente do arquivo oficial do TSE (24.444.579 votos Lula / 24.660.636 votos Flávio Bolsonaro). Pontos importados têm identificação de origem no tooltip; seu horário é o de captura, enquanto os pontos próprios exibem o horário da geração no TSE. Não se inferem dados anteriores às 17h06. A tendência extrapola linearmente os últimos até oito registros até 100% das urnas (limitada a percentuais de 0% a 100%): **não é pesquisa, previsão ou probabilidade de vitória**.

As curvas pontilhadas do primeiro turno vêm das [capturas nacionais arquivadas pelo Placar](https://placar-feed.nicolasqueiroga.workers.dev/history?race=presidente&from=1791142200000&to=1791216000000). `scripts/import_first_round.py` preserva em `data/first-round-history.json` 247 observações não duplicadas, de 1,42% a 100%, valida os votos finais contra o arquivo oficial do TSE e descarta registros inconsistentes. As porcentagens dos finalistas no 1º turno usam como denominador **todos os votos válidos** (12 candidatos), enquanto no 2º turno são somente os votos dos dois finalistas. O hover compara os dois turnos no mesmo percentual de urnas; valores intermediários do 1º turno são interpolados entre observações arquivadas. No trecho pontilhado de tendência do 2º turno, o tooltip indica explicitamente os valores **projetados** naquele percentual e que não são resultados oficiais.

Na interface, o 1º turno aparece por padrão em uma faixa separada com linhas contínuas nas mesmas cores dos candidatos. O seletor **1º turno → Sobreposto** restaura as curvas pontilhadas sobre o gráfico principal. Escala linear/logarítmica e zoom são compartilhados entre as duas visualizações; a faixa separada também tem detalhes ao passar o mouse ou tocar.

O hover mostra votos e porcentagens por candidato em ambos os turnos. Nos registros arquivados do 1º turno, valores entre capturas são interpolados. Na projeção do 2º turno, o número de votos é **estimado**, não observado: calcula-se o total de votos válidos no percentual apontado multiplicando o total válido do último registro por `(urnas apontadas / urnas do último registro)` e aplica-se a participação projetada de cada candidato. Isso supõe ritmo constante de votos válidos por urna, apenas para leitura exploratória.

## A questão das 17h às 19h

A seção recolhível não atribui votos a candidatos sem evidência. A pergunta sobre o encerramento às 17h em 25/10/2026 não permite tratar todas as seções como se tivessem continuado a votar até as 19h. [Logs de urna contêm horário de votação, mas não o candidato escolhido](https://speedurna.furious.pro/sobre); boletins de urna (BU) contêm totais por seção, mas não horário de cada voto. Transmissão/totalização após as 17h não identifica voto depositado após as 17h. O [catálogo oficial de BU](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna) é consultado pelo workflow; `data/extension.json` guarda quais arquivos do 2º turno já foram publicados por UF e exterior. A seção atualiza essa disponibilidade sem refresh.

### Coleta nacional de logs

`scripts/collect_urna_logs.py` percorre as 517.179 seções dos catálogos do pleito `3221` (27 UFs e exterior). Para cada seção, baixa o índice `aux.json`, o BU e o log, conta os votos antes de 17h, entre 17h e 19h e depois das 19h no horário de Brasília e só soma a seção quando o total do log é igual ao do BU. Os arquivos brutos não são gravados; o checkpoint fica em `.cache/urna-logs/` (fora do git) e o agregado em `data/extension-analysis.json`, lido pela página. O TSE não publicou pacotes em lote do 2º turno no portal de dados abertos, por isso a coleta é seção por seção.

```sh
python3 scripts/collect_urna_logs.py                   # retoma de onde parou; Ctrl+C salva e para
python3 scripts/collect_urna_logs.py --seconds 600     # janela limitada
python3 scripts/collect_urna_logs.py --export-only     # regenera o JSON a partir do checkpoint
python3 scripts/collect_urna_logs.py --retry-failed    # recoloca falhas de download na fila
```

O padrão é 8 workers e no máximo 10 requisições por segundo; a coleta de 2026 rodou com `--workers 40 --interval 0.0111` (90 req/s). O TSE limita o acesso a [100 requisições por segundo por IP](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados), bloqueia por 10 minutos quem passa disso e avisa que 404 em excesso também pode bloquear; o script recusa intervalos abaixo de 1/95 s. Cada thread reaproveita sua conexão HTTPS. Em 403 ou 429 todos os workers param por 11 minutos e voltam com metade do ritmo; no quarto bloqueio seguido, ou após 25 respostas 404 seguidas, a coleta para e salva o checkpoint. Em 5xx o intervalo cresce e volta aos poucos. O portal de dados abertos não é consultado pelo script, porque o `robots.txt` dele proíbe `/api/`.

A ordem das seções é sorteada dentro de cada UF e todas as UFs avançam no mesmo percentual, então as seções já processadas formam uma amostra estratificada. Com ela o script estima o total nacional de votos concluídos depois das 17h e um limite superior de 99,9%, tratando exterior, seções excluídas, com falha ou sem reconciliação como se todos os seus votos fossem tardios. Se esse limite fica abaixo da margem final, retirar os votos tardios não muda o vencedor em nenhuma divisão possível entre candidatos, e a página diz isso. As primeiras 10.450 seções foram processadas antes do sorteio, na ordem do catálogo; o JSON registra esse número em `sampling.catalogOrderSections`. Seções agregadas (`nsp` no catálogo) não têm arquivos e entram pelo BU da seção principal. O exterior fica fora até validarmos o fuso de cada país. A divisão dos votos tardios por candidato supõe a mesma proporção do BU da seção e aparece como estimativa. A coleta não roda no workflow do Pages. Enquanto ela roda, `scripts/publish_extension.sh` envia o JSON para a `main` a cada 15 minutos (timer `vaidevirada-publish` do systemd de usuário na máquina da coleta). O script monta o commit num índice temporário, sem mexer na cópia de trabalho, e tenta de novo se o bot do workflow tiver feito push antes. O push desse arquivo não dispara o workflow (`paths-ignore`); o próximo run agendado faz o deploy. Quando o JSON chega a `state: complete`, o script desliga o próprio timer.

O portal oficial fornece [log e BU individuais da seção 0427, zona 0064, João Pessoa/PB](https://resultados.tse.jus.br/oficial/app/index.html#/eleicao/6258/uf/pb/mu/20516/zn/0064/cargo/1/vis/nominal/se/0427/dados-de-urna/log-da-urna). Para reproduzir **apenas essa amostra**, execute `python3 scripts/audit_urna.py pb 20516 64 427`. O arquivo auxiliar oficial do pleito `3221` aponta para um `log.jez` contendo `logd.dat`; contam-se somente eventos `VOTA` com a mensagem “O voto do eleitor foi computado” no dia 25/10/2026. O teste encontrou 333 eventos, dos quais um às 17h01 no relógio da urna. O script não baixa RDV, não preserva logs ou registros individuais e não infere votos por candidato. Antes de somar seções, é necessário validar cobertura, agregações, contingência, relógio/fuso de cada urna e reconciliar totais com BU e totalização; um arquivo por UF ausente no catálogo não significa ausência dos boletins individuais.

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
