# Handoff: Vai de Virada

Estado conferido no checkout em 25/10/2026 (America/Recife). Dados eleitorais e
estado do GitHub mudam: reconfirme antes de relatar numeros ou publicar.

## Objetivo e entrega atual

- Painel estatico no GitHub Pages: https://jcalebbr.github.io/VaiDeVirada/
- Repositorio publico `JCalebBR/VaiDeVirada`, branch `main`.
- Serie historica do segundo turno, comparacao com o primeiro, hover com votos
  e percentuais, zoom, escala logaritmica e projecao ate 100%. A consulta
  direta ao TSE ocorre a cada 30 segundos no navegador; o workflow coleta
  snapshots e publica em intervalos agendados de cinco minutos.
- A secao recolhivel sobre votacao apos 17h le `data/extension-analysis.json`:
  votos tardios, divisao estimada por candidato, cenario ate 17h e limites,
  sempre restritos as secoes ja reconciliadas e com a cobertura exibida.
  So declara a resposta como completa quando nao ha secoes pendentes.
- O ultimo deploy verificado na passagem anterior foi o run `40251341988`
  (sucesso; commit `f48a801`). Isso e evidencia historica, nao status atual.

## Mapa do projeto

| Arquivo | Funcao |
| --- | --- |
| `index.html`, `style.css`, `app.js` | Site estatico, graficos, tooltips e toggle da secao |
| `data/results.json` | Historico publicado do segundo turno, atualizado pelo bot |
| `data/first-round-history.json` | Historico importado e verificado do primeiro turno |
| `data/archive-2026-10-25.json` | Capturas arquivadas da fase inicial do segundo turno |
| `data/extension.json` | Disponibilidade no catalogo CKAN de downloads de BU por UF |
| `scripts/update.py` | Coleta e validacao da totalizacao nacional |
| `scripts/update_extension.py` | Consulta ao catalogo de BU por UF, **nao** aos arquivos individuais |
| `scripts/audit_urna.py` | Inspecao reproduzivel de **uma** urna por vez, sem salvar log bruto |
| `scripts/collect_urna_logs.py` | Coleta nacional retomavel de log + BU por secao; checkpoint em `.cache/urna-logs/` |
| `data/extension-analysis.json` | Agregados reconciliados por Brasil, UF e municipio, com cobertura |
| `scripts/import_archive.py`, `scripts/import_first_round.py` | Importacoes historicas verificaveis |
| `.github/workflows/pages.yml` | Coleta, testes, commit de dados e deploy do Pages |
| `docs/urna-logs.md` | Descoberta dos URLs oficiais, exemplo e plano de pesquisa |
| `tests/` | Testes de coleta, auditoria e graficos |

O `README.md` detalha proveniencia, diferencas entre percentuais dos turnos e
limites da tendencia. Leia-o antes de modificar calculos ou textos do painel.

## Retomar com seguranca

1. `git status -sb && git log -3 --oneline`: o workflow pode ter criado
   commits de dados desde esta passagem. Nao sobrescreva mudancas alheias.
2. `gh run list --workflow pages.yml --limit 5`: confira o ultimo run e
   eventual falha. Se for publicar, atualize a branch antes de fazer push.
3. `python3 -m unittest discover -s tests -v` e
   `node --test tests/test_chart.cjs` validam as rotas basicas.
4. `python3 scripts/audit_urna.py pb 20516 64 427` repete a amostra oficial
   sob demanda; depende do TSE, nao roda no workflow e nao deve ser tomado
   como estatistica nacional.
5. Depois de alterar o site, confira o deploy pelo `gh run view` e busque a
   mudanca no HTML servido no Pages. Um push sozinho nao prova publicacao.

## 17h-19h: coleta em andamento

A coleta nacional roda desde 25/10/2026 ~23h35 com
`python3 scripts/collect_urna_logs.py --workers 40 --interval 0.0111`
(90 req/s; limite do TSE: 100 req/s por IP), destacada do terminal, log em
`.cache/urna-logs/collector.log`. Ritmo medido: ~1.770 secoes/min. Se o log
terminar com `Stopped: HTTP 403/429` ou `consecutive HTTP 404`, espere pelo
menos 10 minutos antes de retomar, com `--interval` maior. Para ver o andamento:
`sqlite3 .cache/urna-logs/checkpoint.sqlite "select status,count(*) from sections group by 1"`.
Se o processo parou, rode o mesmo comando: ele retoma do checkpoint.

A publicacao e feita por `~/.config/systemd/user/vaidevirada-publish.{service,timer}`
(a cada 15 min, `scripts/publish_extension.sh`); estado com
`systemctl --user list-timers vaidevirada-publish.timer` e log com
`journalctl --user -u vaidevirada-publish`. O timer so roda com o usuario logado.

Ao terminar: `--retry-failed` uma vez, conferir `absences.jsonl`, rodar os
testes, revisar a pagina e so entao commitar `data/extension-analysis.json`.
Pendencias conhecidas: o exterior (`zz`, 2.715 secoes) fica fora ate validar
o fuso por pais; secoes com mais de um conjunto de arquivos no `aux.json`
(contingencia) sao excluidas, nao escolhidas. Detalhes em `docs/urna-logs.md`.

Os logs nao ligam horario ao candidato. A divisao por candidato usa a
proporcao do BU de cada secao (hipotese explicita na pagina); `marginBounds`
traz os extremos possiveis sem essa hipotese.

## Cautelas operacionais

- Nao publicar log bruto, RDV, hashes ou identificadores individuais. O script
  atual retorna somente contagens e URL do indice oficial da secao.
- O codigo `6258` identifica a eleicao na navegacao/totalizacao; `3221` e
  o codigo do pleito usado nas rotas dos arquivos de urna. Nao sao intercambiaveis.
- A falta de arquivo no catalogo CKAN por UF **nao** implica falta de
  boletins/logs individuais no portal de resultados.
- O historico da apuracao comeca no primeiro snapshot publico disponivel
  (17h06), nao no inicio da votacao; horario de transmissao de BU nao
  equivale a horario de voto.
