# Eleições 2026 no Piauí — painel de resultados

Painel público com os resultados das eleições de 2026 no Piauí por **município, zona eleitoral e
local de votação**, com mapa. Os dados vêm do Portal de Dados Abertos do TSE.

> **Status:** pipeline de dados e site estático prontos para o 1º turno de 2026
> (página do estado por cargo; página de cada município com mapa e tabela por local de votação).
> Faltam: 2º turno, Vereador (2024), página do candidato e linha do tempo de carreira.

## Como funciona

```
CSVs do TSE ──► importar_TSE.py ──► PostgreSQL ──► exportar_json.py ──► web/public/data/*.json ──► site estático
                                        ▲
              geocodificar_locais.py ───┘  (coordenadas dos locais sem latitude/longitude)
```

O site não precisa de banco em produção: ele só lê os JSON gerados.

## Dados (não estão no repositório)

Baixe em <https://dadosabertos.tse.jus.br> e coloque nas pastas abaixo, na raiz do projeto:

| Conjunto | Pasta / arquivo esperado |
|---|---|
| Boletim de urna (1º turno, PI) | `bweb_1t_PI_.../BoletimUrnaPIbweb_1t_PI_....csv` |
| Candidatos PI | `candidatoPI2026/consulta_cand_2026_PI.csv` |
| Candidatos BR (Presidente) | `candidatoBR2026/consulta_cand_2026_BR.csv` |
| Perfil do eleitorado por seção | `perfil_eleitor_secao_2026_PI/perfil_eleitor_secao_2026_PI.csv` |
| Eleitorado por local de votação | `eleitorado_local_votacao_2026_PI.csv` |

Os caminhos ficam no dicionário `ELEICOES` em `importar_TSE.py`. Os arquivos são Latin-1, separados
por `;`. O `.gitignore` impede que sejam versionados.

## Como rodar

Requisitos: Python 3.11+, PostgreSQL, `pip install pg8000 pandas`.

```bash
cp .env.example .env           # preencha PGPASSWORD (o .env nunca vai para o git)
# crie o banco:  CREATE DATABASE joaoeleicao;

python importar_TSE.py 2026    # importa 2026 (reexecutar recarrega só esse ano)
python geocodificar_locais.py --gravar            # coordenadas dos locais sem latitude/longitude
python aplicar_coordenadas_manuais.py             # opcional: coordenadas preenchidas à mão
python exportar_json.py        # gera web/public/data (confere os totais contra o banco)
```

`python importar_TSE.py 2026:2` carrega só o boletim do 2º turno (configure o arquivo em `ELEICOES`).

## Site (pasta `web/`)

Next.js (export estático) + TypeScript + Tailwind, Recharts (gráficos), TanStack Table (tabelas) e
Leaflet/OpenStreetMap (mapa). As páginas leem os JSON de `web/public/data` **no build**.

```bash
cd web
npm install
npm run dev      # desenvolvimento em http://localhost:3000
npm run build    # gera web/out (site estático, pronto para hospedar)
```

Para publicar em um subcaminho (ex.: GitHub Pages), defina `NEXT_PUBLIC_BASE_PATH=/nome-do-repo` antes do build.

## Modelo de dados

| Tabela / view | O que guarda |
|---|---|
| `pessoas` | Uma linha por pessoa (chave: CPF; sem CPF, nome + nascimento). Sobrevive entre eleições. **Nunca é exportada.** |
| `candidaturas` | Uma pessoa disputando um cargo em uma eleição. PK `(ano_eleicao, sq_candidato)`. |
| `boletim_urna` | Votos por seção (bruto do TSE). |
| `perfil_eleitor` | Perfil do eleitorado por seção. |
| `locais_votacao` | Local de votação: endereço, bairro, coordenadas, tipo e precisão da coordenada. |
| `v_candidaturas_votaveis` / `v_votos_candidato` | Ligam os votos à candidatura e à pessoa (vices e suplentes não aparecem na urna). |
| `resumo_*` | Tabelas de totais criadas pelo exportador. |

### Decisões que valem saber
- **Número de candidato não é único** (o 13 é Governador, Vice, Presidente...). O vínculo voto → candidato
  usa ano + cargo + número + nome de urna.
- **Precisão das coordenadas** (`precisao_coordenada`): `tse` (cadastro do TSE), `exata`, `rua` e `povoado`
  (busca no OpenStreetMap), `manual` e `municipio` (centro do município, aproximado). O mapa deve
  tratar as aproximadas de forma diferente das exatas.
- **A importação é incremental por ano e atômica**: cada tabela é recarregada numa transação.

## Privacidade

O site publica apenas dados públicos do TSE: nome, partido, cargo, número, votos e locais de votação.
CPF, título de eleitor e telefones **não** são exportados (o exportador falha se encontrar esses campos).

## Fonte

TSE — Portal de Dados Abertos. Resultados de 2026, 1º turno.
