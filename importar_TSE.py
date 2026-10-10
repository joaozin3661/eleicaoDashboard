"""
Importação INCREMENTAL dos dados do TSE para o PostgreSQL

Uso:
    python importar_TSE.py            # importa todos os anos de ELEICOES
    python importar_TSE.py 2026       # importa só 2026 (todos os turnos)
    python importar_TSE.py 2026:2     # só o boletim do 2º turno de 2026
    python importar_TSE.py 2022 2026  # importa 2022 e 2026

Cada execução só mexe no(s) ano(s) pedido(s): apaga as linhas daquele ano
e recarrega, numa única transação por tabela (se falhar, o ano antigo
continua intacto). Os outros anos, as pessoas e a geocodificação dos
locais de votação nunca são apagados.
 
Dependências: pip install pg8000 pandas
"""
 
import os
import sys
import time
import pandas as pd
import db

# Terminal do Windows (cp1252) não exibe caracteres como "→"
sys.stdout.reconfigure(encoding="utf-8")
 
# ─────────────────────────────────────────
# CONFIGURAÇÃO — ajuste aqui
# ─────────────────────────────────────────
# Conexão: lida de variáveis de ambiente / arquivo .env (veja .env.example).
DB = db.config()
 
# Um bloco por eleição. Para um novo ano, copie o bloco e ajuste os caminhos.
ELEICOES = {
    2026: {
        # Boletim por turno. Para o 2º turno, acrescente  2: "caminho/do/csv"
        "boletim_urna":   {
            1: "bweb_1t_PI_051020261403/BoletimUrnaPIbweb_1t_PI_051020261403.csv",
        },
        "perfil_eleitor": "perfil_eleitor_secao_2026_PI/perfil_eleitor_secao_2026_PI.csv",
        # Opcional: endereço, bairro, CEP e coordenadas dos locais (cadastro do TSE)
        "locais_votacao": "eleitorado_local_votacao_2026_PI.csv",
    },
}
 
ENCODING  = "latin-1"
SEP       = ";"
CHUNKSIZE = 100_000   # linhas por lote (ajuste conforme RAM disponível)
 
 
# ─────────────────────────────────────────
# DDL — criação das tabelas
# ─────────────────────────────────────────
DDL = """
-- Boletim de Urna (votos por seção)
CREATE TABLE IF NOT EXISTS boletim_urna (
    dt_geracao                    DATE,
    ano_eleicao                   SMALLINT,
    nr_turno                      SMALLINT,
    sg_uf                         CHAR(2),
    cd_municipio                  INTEGER,
    nm_municipio                  TEXT,
    nr_zona                       SMALLINT,
    nr_secao                      SMALLINT,
    nr_local_votacao              INTEGER,
    cd_cargo_pergunta             SMALLINT,
    ds_cargo_pergunta             TEXT,
    nr_partido                    SMALLINT,
    sg_partido                    VARCHAR(20),
    nm_partido                    TEXT,
    qt_aptos                      INTEGER,
    qt_comparecimento             INTEGER,
    qt_abstencoes                 INTEGER,
    cd_tipo_urna                  SMALLINT,
    ds_tipo_urna                  TEXT,
    cd_tipo_votavel               SMALLINT,
    ds_tipo_votavel               TEXT,
    nr_votavel                    INTEGER,
    nm_votavel                    TEXT,
    qt_votos                      INTEGER,
    nr_urna_efetivada             BIGINT,
    dt_abertura                   TIMESTAMP,
    dt_encerramento               TIMESTAMP,
    dt_emissao_bu                 TIMESTAMP,
    qt_elei_biom_sem_habilitacao  INTEGER
);
 
-- Perfil do eleitor por seção (usado para pegar NM_LOCAL_VOTACAO)
CREATE TABLE IF NOT EXISTS perfil_eleitor (
    ano_eleicao              SMALLINT,
    sg_uf                    CHAR(2),
    cd_municipio             INTEGER,
    nm_municipio             TEXT,
    nr_zona                  SMALLINT,
    nr_secao                 SMALLINT,
    nr_local_votacao         INTEGER,
    nm_local_votacao         TEXT,
    cd_genero                SMALLINT,
    ds_genero                TEXT,
    cd_faixa_etaria          SMALLINT,
    ds_faixa_etaria          TEXT,
    cd_grau_escolaridade     SMALLINT,
    ds_grau_escolaridade     TEXT,
    cd_raca_cor              SMALLINT,
    ds_raca_cor              TEXT,
    qt_eleitores             INTEGER,
    qt_eleitores_biometria   INTEGER,
    qt_eleitores_deficiencia INTEGER,
    qt_eleitores_nome_social INTEGER
);
 
-- Bancos criados antes da versão incremental não tinham o ano no perfil
ALTER TABLE perfil_eleitor ADD COLUMN IF NOT EXISTS ano_eleicao SMALLINT;

-- Locais de votação (gerada a partir do perfil, com geocodificação futura)
CREATE TABLE IF NOT EXISTS locais_votacao (
    sg_uf            CHAR(2),
    cd_municipio     INTEGER,
    nm_municipio     TEXT,
    nr_zona          SMALLINT,
    nr_local_votacao INTEGER,
    nm_local_votacao TEXT,
    endereco         TEXT,
    bairro           TEXT,
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    geocodificado    BOOLEAN DEFAULT FALSE,
    cep              CHAR(8),
    cd_tipo_local    SMALLINT,     -- 1 convencional, 2 voto em trânsito, 3 preso provisório, 4 temporário
    ds_tipo_local    TEXT,
    ds_situacao_local TEXT,        -- ATIVO / BLOQUEADO (cadastro do TSE)
    nm_local_original TEXT,        -- local original, quando a votação foi movida
    fonte_coordenada TEXT,         -- 'tse' | 'nominatim' | 'google' | 'manual'
    precisao_coordenada TEXT,      -- 'tse' | 'exata' | 'rua' | 'povoado' | 'manual'
    PRIMARY KEY (sg_uf, cd_municipio, nr_zona, nr_local_votacao)
);

-- Bancos criados antes da importação de locais do TSE
ALTER TABLE locais_votacao
    ADD COLUMN IF NOT EXISTS cep CHAR(8),
    ADD COLUMN IF NOT EXISTS cd_tipo_local SMALLINT,
    ADD COLUMN IF NOT EXISTS ds_tipo_local TEXT,
    ADD COLUMN IF NOT EXISTS ds_situacao_local TEXT,
    ADD COLUMN IF NOT EXISTS nm_local_original TEXT,
    ADD COLUMN IF NOT EXISTS fonte_coordenada TEXT,
    ADD COLUMN IF NOT EXISTS precisao_coordenada TEXT;
"""
 
# ─────────────────────────────────────────
# Colunas que vamos importar de cada tabela
# (ignora o resto para economizar espaço)
# ─────────────────────────────────────────
COLUNAS_BOLETIM = [
    "DT_GERACAO", "ANO_ELEICAO", "NR_TURNO", "SG_UF",
    "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
    "NR_LOCAL_VOTACAO", "CD_CARGO_PERGUNTA", "DS_CARGO_PERGUNTA",
    "NR_PARTIDO", "SG_PARTIDO", "NM_PARTIDO",
    "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
    "CD_TIPO_URNA", "DS_TIPO_URNA",
    "CD_TIPO_VOTAVEL", "DS_TIPO_VOTAVEL",
    "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS",
    "NR_URNA_EFETIVADA", "DT_ABERTURA", "DT_ENCERRAMENTO",
    "DT_EMISSAO_BU", "QT_ELEI_BIOM_SEM_HABILITACAO",
]
 
# Nome da coluna de ano em cada CSV -> coluna ano_eleicao da tabela
RENOMEAR_PERFIL = {"AA_ELEICAO": "ANO_ELEICAO"}
 
COLUNAS_PERFIL = [
    "AA_ELEICAO",   # no CSV do perfil o ano se chama AA_ELEICAO
    "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO",
    "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO",
    "CD_GENERO", "DS_GENERO", "CD_FAIXA_ETARIA", "DS_FAIXA_ETARIA",
    "CD_GRAU_ESCOLARIDADE", "DS_GRAU_ESCOLARIDADE",
    "CD_RACA_COR", "DS_RACA_COR",
    "QT_ELEITORES", "QT_ELEITORES_BIOMETRIA",
    "QT_ELEITORES_DEFICIENCIA", "QT_ELEITORES_NOME_SOCIAL",
]
 
 
# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────
def limpar(val):
    """Converte valores nulos do TSE para None."""
    if pd.isna(val):
        return None
    if isinstance(val, str):
        val = val.strip()
        if val in ("#NULO", "#NE", "#NULO#", ""):
            return None
    return val
 
 
def df_para_lista(df):
    return [tuple(limpar(v) for v in row) for row in df.itertuples(index=False)]
 
 
def importar_csv(conn, tabela, arquivo, colunas, ano, renomear=None,
                 apagar_ano=True, turno=None, chunksize=CHUNKSIZE):
    """Carrega um CSV numa tabela, de forma atômica.

    Apaga as linhas de `ano` (e só do `turno`, se informado — o boletim
    do 2º turno não pode apagar o do 1º) e insere o CSV na MESMA transação:
    se algo falhar, nada é commitado e os dados antigos permanecem.
    Recusa o arquivo se a coluna de ano (ou de turno) do CSV não bater.
    """
    print(f"\n→ Importando {tabela} ({ano}) de {arquivo} ...")

    if not os.path.exists(arquivo):
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")

    tamanho = os.path.getsize(arquivo) / (1024 * 1024)
    print(f"  Tamanho: {tamanho:.1f} MB")

    renomear = renomear or {}
    colunas_tabela = [renomear.get(c, c) for c in colunas]
    cols_lower = [c.lower() for c in colunas_tabela]
    sql = f"INSERT INTO {tabela} ({','.join(cols_lower)}) VALUES %s"

    total = 0
    inicio = time.time()

    try:
        with conn.cursor() as cur:
            if apagar_ano:
                if turno is None:
                    cur.execute(f"DELETE FROM {tabela} WHERE ano_eleicao = %s", (ano,))
                else:
                    cur.execute(f"DELETE FROM {tabela} WHERE ano_eleicao = %s "
                                f"AND nr_turno = %s", (ano, turno))
                print(f"  Removidas {cur.rowcount:,} linhas antigas de {ano}")

        for i, chunk in enumerate(
            pd.read_csv(
                arquivo,
                encoding=ENCODING,
                sep=SEP,
                usecols=colunas,
                chunksize=chunksize,
                dtype=str,          # lê tudo como string, converte depois
                on_bad_lines="skip",
            )
        ):
            chunk = chunk[colunas].rename(columns=renomear)

            anos = set(chunk["ANO_ELEICAO"].dropna().unique())
            if anos != {str(ano)}:
                raise ValueError(
                    f"{arquivo} contém ano(s) {sorted(anos)}, esperado {ano}"
                )

            if turno is not None:
                turnos = set(chunk["NR_TURNO"].dropna().unique())
                if turnos != {str(turno)}:
                    raise ValueError(
                        f"{arquivo} contém turno(s) {sorted(turnos)}, esperado {turno}"
                    )

            with conn.cursor() as cur:
                db.execute_values(cur, sql, df_para_lista(chunk))

            total += len(chunk)
            elapsed = time.time() - inicio
            print(f"  Lote {i+1}: {total:,} linhas em {elapsed:.1f}s")

        if apagar_ano:
            conn.commit()   # staging (apagar_ano=False) é commitado por quem chama
    except Exception:
        conn.rollback()
        raise

    print(f"  ✓ Total importado: {total:,} linhas")


def criar_views(conn):
    """Cria as views de votos por candidato. Dependem de `candidaturas`, que é gravada por
    importar_candidatos_historico.py --gravar (esquema novo de pessoas e candidaturas)."""
    from gravar_candidatos import VIEWS
    print("\n→ Criando views ...")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('candidaturas') IS NOT NULL")
        if not cur.fetchone()[0]:
            print("  [AVISO] tabela candidaturas não existe: rode antes "
                  "python importar_candidatos_historico.py --gravar")
            return
        cur.execute(VIEWS)
    conn.commit()
    print("  ✓ v_candidaturas_votaveis, v_votos_candidato")



# Limites do Piauí (com folga) para recusar coordenadas obviamente erradas
_LAT_PI = (-11.0, -2.5)
_LON_PI = (-46.0, -40.0)


def _coord(valor):
    """'-10,03371053' -> -10.03371053. O TSE usa '-1' (ou vazio) para 'sem coordenada'."""
    if valor is None or pd.isna(valor):
        return None
    try:
        x = float(str(valor).strip().replace(",", "."))
    except ValueError:
        return None
    return None if x == -1 else x


def _texto(valor):
    """Vazio/#NULO/-1 -> None."""
    if valor is None or pd.isna(valor):
        return None
    valor = str(valor).strip()
    return None if valor in ("", "#NULO", "#NE", "-1") else valor


def importar_locais_tse(conn, ano, arquivo):
    """Preenche locais_votacao com o cadastro de locais do TSE (endereço, bairro,
    CEP, coordenadas, tipo e situação) e cria os locais que ainda não existem.

    - O arquivo repete cada seção nos dois turnos: fica 1 linha por local
      (a do 1º turno, quando existe).
    - O arquivo do TSE é mais recente que o perfil do eleitor, então o NOME do
      local vindo dele prevalece (locais trocados/realocados).
    - Coordenada do TSE só sobrescreve se vier preenchida; uma coordenada já
      obtida por geocodificação nunca é apagada.
    """
    print(f"\n→ Importando locais de votação ({ano}) de {arquivo} ...")
    if not os.path.exists(arquivo):
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")

    colunas = ["AA_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO",
               "NR_ZONA", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "CD_TIPO_LOCAL",
               "DS_TIPO_LOCAL", "DS_ENDERECO", "NM_BAIRRO", "NR_CEP",
               "NR_LATITUDE", "NR_LONGITUDE", "DS_SITU_LOCAL_VOTACAO",
               "NM_LOCAL_VOTACAO_ORIGINAL"]
    df = pd.read_csv(arquivo, encoding=ENCODING, sep=SEP, usecols=colunas, dtype=str)

    anos = set(df["AA_ELEICAO"].dropna().unique())
    if anos != {str(ano)}:
        raise ValueError(f"{arquivo} contém ano(s) {sorted(anos)}, esperado {ano}")

    df["NR_TURNO"] = df["NR_TURNO"].astype(int)
    chave = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO"]
    df = df.sort_values("NR_TURNO", kind="stable").drop_duplicates(chave)

    linhas, sem_coord, coord_invalida = [], 0, 0
    for r in df.itertuples(index=False):
        lat, lon = _coord(r.NR_LATITUDE), _coord(r.NR_LONGITUDE)
        if lat is not None and lon is not None and not (
                _LAT_PI[0] <= lat <= _LAT_PI[1] and _LON_PI[0] <= lon <= _LON_PI[1]):
            lat = lon = None
            coord_invalida += 1
        if lat is None or lon is None:
            lat = lon = None
            sem_coord += 1
        cep = _texto(r.NR_CEP)
        linhas.append((
            r.SG_UF, int(r.CD_MUNICIPIO), r.NM_MUNICIPIO, int(r.NR_ZONA),
            int(r.NR_LOCAL_VOTACAO), r.NM_LOCAL_VOTACAO.strip(),
            _texto(r.DS_ENDERECO), _texto(r.NM_BAIRRO),
            cep if cep and len(cep) == 8 and cep.isdigit() and cep != "00000000" else None,
            int(r.CD_TIPO_LOCAL), _texto(r.DS_TIPO_LOCAL),
            _texto(r.DS_SITU_LOCAL_VOTACAO), _texto(r.NM_LOCAL_VOTACAO_ORIGINAL),
            lat, lon,
        ))

    sql = """
        INSERT INTO locais_votacao
            (sg_uf, cd_municipio, nm_municipio, nr_zona, nr_local_votacao,
             nm_local_votacao, endereco, bairro, cep, cd_tipo_local, ds_tipo_local,
             ds_situacao_local, nm_local_original, latitude, longitude)
        VALUES %s
        ON CONFLICT (sg_uf, cd_municipio, nr_zona, nr_local_votacao) DO UPDATE SET
            nm_municipio      = EXCLUDED.nm_municipio,
            nm_local_votacao  = EXCLUDED.nm_local_votacao,
            endereco          = EXCLUDED.endereco,
            bairro            = EXCLUDED.bairro,
            cep               = EXCLUDED.cep,
            cd_tipo_local     = EXCLUDED.cd_tipo_local,
            ds_tipo_local     = EXCLUDED.ds_tipo_local,
            ds_situacao_local = EXCLUDED.ds_situacao_local,
            nm_local_original = EXCLUDED.nm_local_original,
            fonte_coordenada  = CASE WHEN EXCLUDED.latitude IS NOT NULL THEN 'tse'
                                     ELSE locais_votacao.fonte_coordenada END,
            precisao_coordenada = CASE WHEN EXCLUDED.latitude IS NOT NULL THEN 'tse'
                                       ELSE locais_votacao.precisao_coordenada END,
            latitude          = COALESCE(EXCLUDED.latitude, locais_votacao.latitude),
            longitude         = COALESCE(EXCLUDED.longitude, locais_votacao.longitude),
            geocodificado     = COALESCE(EXCLUDED.latitude, locais_votacao.latitude) IS NOT NULL
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM locais_votacao")
            antes = cur.fetchone()[0]
            db.execute_values(cur, sql, linhas)
            cur.execute("SELECT count(*) FROM locais_votacao")
            depois = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    print(f"  ✓ {len(linhas):,} locais processados ({depois - antes} novos)")
    print(f"    sem coordenada (precisam de geocodificação) ... {sem_coord}")
    print(f"    coordenada recusada por cair fora do Piauí .... {coord_invalida}")


def criar_locais_votacao(conn):
    """Extrai locais únicos da tabela perfil_eleitor."""
    print("\n→ Criando tabela locais_votacao a partir do perfil_eleitor ...")
    sql = """
    INSERT INTO locais_votacao
        (sg_uf, cd_municipio, nm_municipio, nr_zona, nr_local_votacao, nm_local_votacao)
    SELECT DISTINCT
        sg_uf, cd_municipio, nm_municipio, nr_zona, nr_local_votacao, nm_local_votacao
    FROM perfil_eleitor
    ON CONFLICT DO NOTHING;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("  ✓ locais_votacao populada!")
 
 
def criar_indices(conn):
    """Cria índices para queries rápidas."""
    print("\n→ Criando índices ...")
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_bu_ano        ON boletim_urna (ano_eleicao);",
        "CREATE INDEX IF NOT EXISTS idx_perf_ano      ON perfil_eleitor (ano_eleicao);",
        "CREATE INDEX IF NOT EXISTS idx_bu_municipio  ON boletim_urna (cd_municipio);",
        "CREATE INDEX IF NOT EXISTS idx_bu_zona       ON boletim_urna (nr_zona);",
        "CREATE INDEX IF NOT EXISTS idx_bu_local      ON boletim_urna (nr_local_votacao);",
        "CREATE INDEX IF NOT EXISTS idx_bu_cargo      ON boletim_urna (cd_cargo_pergunta);",
        "CREATE INDEX IF NOT EXISTS idx_bu_votavel    ON boletim_urna (nr_votavel);",
        "CREATE INDEX IF NOT EXISTS idx_perf_local    ON perfil_eleitor (nr_local_votacao);",
        "CREATE INDEX IF NOT EXISTS idx_perf_mun      ON perfil_eleitor (cd_municipio);",
    ]
    with conn.cursor() as cur:
        for idx in indices:
            cur.execute(idx)
            print(f"  ✓ {idx.split('ON')[1].split(';')[0].strip()}")
    conn.commit()
    print("  ✓ Índices criados!")
 
 
# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
def importar_ano(conn, ano, so_turno=None):
    """Importa uma eleição. Com so_turno, carrega apenas o boletim daquele turno."""
    arq = ELEICOES[ano]
    print("\n" + "-" * 60)
    print(f"ELEIÇÃO {ano}" +(f" — só boletim do turno {so_turno}" if so_turno else ""))
    print("-" * 60)

    if so_turno is None:
        importar_csv(conn, "perfil_eleitor", arq["perfil_eleitor"], COLUNAS_PERFIL,
                     ano, renomear=RENOMEAR_PERFIL)
        criar_locais_votacao(conn)   # só acrescenta locais novos (preserva geocodificação)
        if arq.get("locais_votacao"):
            importar_locais_tse(conn, ano, arq["locais_votacao"])

    for turno, arquivo in sorted(arq["boletim_urna"].items()):
        if so_turno in (None, turno):
            importar_csv(conn, "boletim_urna", arquivo, COLUNAS_BOLETIM, ano,
                         turno=turno)


if __name__ == "__main__":
    # Argumentos: "2026" (tudo) ou "2026:2" (só o boletim do 2º turno de 2026)
    pedidos = []
    for arg in sys.argv[1:] or [str(a) for a in sorted(ELEICOES)]:
        ano_s, _, turno_s = arg.partition(":")
        pedidos.append((int(ano_s), int(turno_s) if turno_s else None))
    anos = [a for a, _ in pedidos]
    invalidos = [a for a in anos if a not in ELEICOES]
    if invalidos:
        sys.exit(f"Ano(s) sem configuração em ELEICOES: {invalidos}. "
                 f"Disponíveis: {sorted(ELEICOES)}")

    print("=" * 60)
    print(f"IMPORTAÇÃO TSE {', '.join(map(str, anos))} → PostgreSQL")
    print("=" * 60)

    conn = db.connect(**DB)
    print(f"✓ Conectado ao banco: {DB['dbname']}")

    # Idempotente: só cria o que ainda não existe, nunca apaga dados.
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()

    for ano, so_turno in pedidos:
        if so_turno is not None and so_turno not in ELEICOES[ano]["boletim_urna"]:
            sys.exit(f"{ano} não tem boletim configurado para o turno {so_turno}")
        importar_ano(conn, ano, so_turno)

    criar_indices(conn)
    criar_views(conn)

    conn.close()
    print("\n" + "=" * 60)
    print("✓ IMPORTAÇÃO CONCLUÍDA!")
    print("=" * 60)
