# Arquivos de urna do segundo turno: evidencia e limites

Pesquisa reproduzida em 25/10/2026. Os caminhos abaixo sao da propria
aplicacao de resultados do TSE e de uma secao especifica; disponibilidade,
formato e valores precisam ser revalidados antes de ampliar a coleta.

## Enderecos e identificadores

- Portal de logs: https://resultados.tse.jus.br/oficial/app/index.html#/eleicao/6258/uf/br/cargo/1/vis/nominal/dados-de-urna/log-da-urna
- BU da secao de exemplo: https://resultados.tse.jus.br/oficial/app/index.html#/eleicao/6258/uf/pb/mu/20516/zn/0064/cargo/1/vis/nominal/se/0427/dados-de-urna/boletim-de-urna
- Configuracao de secoes da PB no pleito: https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/config/pb/pb-p003221-cs.json
- Indice de arquivos da secao: https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/dados/pb/20516/0064/0427/p003221-pb-m20516-z0064-s0427-aux.json

O fragmento `#` e rota do aplicativo, nao URL do arquivo. A totalizacao
presidencial do segundo turno usa eleicao `6258`; a API de arquivos de urna
usa pleito `3221`. Esses codigos foram observados separadamente. A rota do
indice tem `uf`, municipio com cinco digitos, zona e secao com quatro digitos.
O indice `aux.json` contem `hashes[]`; cada entrada referencia um conjunto de
arquivos (`arq`) com nome (`nm`) e tipo (`tp`). Para esse exemplo apareceu um
conjunto com `bu.dat` (`bu`), `log.jez` (`log`), imagem do BU, RDV e outros.
O arquivo individual fica em:

```text
.../arquivo-urna/3221/dados/{uf}/{municipio}/{zona}/{secao}/{hash}/{nm}
```

Nao substitua `{hash}` por um valor inventado: consulte o indice oficial.
`scripts/audit_urna.py` faz isso e recusa multiplos conjuntos em vez de
escolher arbitrariamente entre urna original, contingencia ou agregacao.

## Evidencia na secao 0427

Comando: `python3 scripts/audit_urna.py pb 20516 64 427`.
O `log.jez` baixado nessa verificacao era um ZIP contendo `logd.dat` em
Latin-1. As linhas possuem data/hora, nivel, identificador do equipamento,
modulo, mensagem e campo final. Para 25/10/2026, o script conta somente
modulo `VOTA` e mensagem exata `O voto do eleitor foi computado`:

| Secao PB / 20516 / 0064 / 0427 | Eventos |
| --- | ---: |
| Votacoes computadas no dia | 333 |
| Apos 17:00:00, no relogio da urna | 1 |
| Apos 19:00:00, no relogio da urna | 0 |

O evento tardio foi as 17h01. Trata-se de **uma unica secao**, nao de
estimativa para Joao Pessoa, PB ou Brasil. Nem o log nem o BU associam
candidato a esse horario. O BU do exemplo e ASN.1/DER; o coletor nacional o
decodifica e confirma os mesmos 333 votos (ver secao seguinte). Nenhum RDV foi analisado ou deve ser usado para
reconstituir escolhas individuais.

O script carrega o log em memoria, limita tamanho e nao escreve eventos em
`data/`; testes sinteticos em `tests/test_audit_urna.py` verificam corte
estrito apos 17:00:00 e rejeicao de arquivo/formato inesperado. O horario e
o do relogio da urna: validar fuso, relogio e eventuais correcoes antes de
somar secoes, especialmente fora do exemplo na PB.

## Coleta nacional: o que os arquivos mostraram

`scripts/collect_urna_logs.py` implementa o plano abaixo. Observado na coleta
de 25-26/10/2026:

- Os catalogos `config/{uf}/{uf}-p003221-cs.json` listam 517.179 secoes.
  Secoes com `nsp` foram agregadas a secao principal (`nsa` na principal) e
  respondem 404 no `aux.json`: sao 17.931, contadas como `aggregated`.
- O BU decodificado (DER) da secao 0427 bate com o log: 175 / 145 / 3 / 10,
  total 333.
- Alguns `log.jez` trazem, alem de `logd.dat`, um segundo ZIP `*.jez` com
  outro `logd.dat`. O coletor soma os votos de todos e exige que o total
  bata com o BU; na primeira amostra o log aninhado tinha 0 votos.
- O CKAN do TSE (`resultados-2026-boletim-de-urna` e
  `resultados-2026-arquivos-transmitidos-para-totalizacao`) so tinha
  arquivos do 1o turno; os pacotes de log do Gedai sao da preparacao das
  urnas, nao da votacao.
- O relogio do log esta no fuso local. AC e 13 municipios do oeste do AM
  usam UTC-5; AM restante, RO, RR, MT e MS usam UTC-4; Fernando de Noronha
  UTC-2.
- Exterior (`zz`): o relogio do log e o local, com horario de verao aplicado
  quando a urna liga, antes do primeiro voto; por isso so um ajuste de relogio
  depois do primeiro voto exclui a secao. O BU do exterior nao tem o campo
  opcional `[1]` entre comparecimento e eleicoes (9 campos em vez de 10).
  Secoes apuradas em cedula trazem `busa`/`logsa` e nao tem log de voto.
- O catalogo `config/{uf}/{uf}-p003221-cs.json` traz `da`/`ha` por secao: a
  chegada dos arquivos, em horario de Brasilia (Toquio 06h31, Wellington
  01h51, Lisboa 14h31, Los Angeles 21h12). Antes das 17h, nenhum voto da secao
  pode ser posterior as 17h BRT.

Status no checkpoint: `ok`, `pending`, `aggregated`, `failed` (rede/HTTP),
`excluded` (motivo em `.cache/urna-logs/absences.jsonl`) e `unreconciled`
(log diferente do BU).

## Plano para uma analise nacional defensavel

1. Localizar arquivos de configuracao de secoes de todas as UFs e exterior,
   conferir quais correspondem ao segundo turno e obter denominadores
   oficiais de secoes e votantes. Anotar a cobertura por UF.
2. Identificar secoes agregadas, transferidas, anuladas, contingencia e
   multiplos hashes. Definir a unidade de contagem para evitar duplicacoes.
3. Coletar indices e logs em lotes controlados, com cache/checkpoint local
   restrito, timeouts, retries e registro explicito de 404/erros. Respeitar
   a infraestrutura oficial; nao sobrecarregar o portal.
4. Analisar eventos de voto computado no **segundo turno** e reconciliar por
   secao com BU e/ou comparecimento oficial. Investigar divergencias,
   falhas de horario e urnas sem log antes de publicar totais.
5. Normalizar horario com fuso e data da localidade, distinguir `>17h`,
   `=17h` e `>19h`, e explicitar que o evento e conclusao do voto, nao
   necessariamente inicio da habilitacao nem transmissao do BU.
6. Publicar apenas agregados e denominadores auditaveis, inclusive secoes
   ausentes. Nao inferir preferencia eleitoral a partir de horario,
   comparecimento ou sequencia de registro.

Se a cobertura for incompleta, exiba intervalo/limite ou "nao determinado",
nunca um total nacional derivado so das secoes coletadas. Mesmo com cobertura
completa, total tardio maior que a margem final nao determina quem ganharia
sem esses votos. O teste simples de margem usa a margem **final**, nao
snapshots parciais da apuracao.
