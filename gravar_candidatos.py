"""
Gravação de pessoas e candidaturas no PostgreSQL (esquema do histórico).

Tabelas:
  pessoas                 uma linha por pessoa, com `slug` público aleatório e nome de exibição
  pessoa_identificadores  CPFs, títulos e chaves de candidatura já vistos de cada pessoa
                          (a "ponte" que liga candidaturas de anos diferentes; nunca exportada)
  candidaturas            uma pessoa disputando um cargo numa eleição/turno

Garantias:
  * tudo numa única transação: se algo falhar, o banco volta ao que era antes;
  * ids estáveis: ao reimportar, a mesma pessoa mantém `id_pessoa` e `slug`;
  * o slug é aleatório e nunca derivado de CPF ou título.

Regras de privacidade do nome de exibição:
  1. nome social informado (o mais recente); senão
  2. se o TSE marcou o nome social como NÃO DIVULGÁVEL: o nome de urna mais recente; senão
  3. o nome de registro mais recente.
  O nome de registro antigo nunca é o nome de exibição.
"""

import base64
import os
from collections import Counter, defaultdict

import pandas as pd

import db

DDL = """
CREATE TABLE IF NOT EXISTS pessoas (
    id_pessoa            BIGINT PRIMARY KEY,              -- atribuído pelo importador (estável)
    slug                 TEXT UNIQUE NOT NULL,            -- endereço público: aleatório, nunca derivado de CPF
    nm_exibicao          TEXT NOT NULL,
    dt_nascimento        DATE,
    sg_uf_nascimento     CHAR(2),
    nivel_evidencia      CHAR(1),                         -- A (certeza) ... E; '-' = uma só candidatura
    revisar              BOOLEAN NOT NULL DEFAULT FALSE,
    ocultar_nome_registro BOOLEAN NOT NULL DEFAULT FALSE, -- nome social protegido pelo TSE
    atualizado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pessoa_identificadores (
    id_pessoa BIGINT NOT NULL REFERENCES pessoas(id_pessoa) ON DELETE CASCADE,
    tipo      TEXT NOT NULL CHECK (tipo IN ('cpf', 'titulo', 'candidatura')),
    valor     TEXT NOT NULL,
    anos      SMALLINT[] NOT NULL,
    PRIMARY KEY (id_pessoa, tipo, valor)
);
-- o mesmo CPF pode aparecer em duas pessoas (erro do TSE): por isso o índice não é único
CREATE INDEX IF NOT EXISTS idx_pessoa_ident_valor ON pessoa_identificadores (tipo, valor);

CREATE TABLE IF NOT EXISTS candidaturas (
    id_candidatura       BIGSERIAL PRIMARY KEY,
    id_pessoa            BIGINT NOT NULL REFERENCES pessoas(id_pessoa),
    ano_eleicao          SMALLINT NOT NULL,
    dt_eleicao           DATE NOT NULL,
    nr_turno             SMALLINT NOT NULL,
    tp_eleicao           TEXT NOT NULL,                   -- ordinaria | suplementar
    sg_uf                VARCHAR(2),
    sg_ue                VARCHAR(10) NOT NULL,
    nm_ue                TEXT,
    cd_cargo             SMALLINT NOT NULL,
    ds_cargo             TEXT,
    sq_candidato         BIGINT NOT NULL,
    nr_candidato         INTEGER,
    nm_candidato         TEXT,
    nm_urna_candidato    TEXT,
    nm_social_candidato  TEXT,
    tp_abrangencia       VARCHAR(20),
    nr_partido           SMALLINT,
    sg_partido           VARCHAR(20),
    nm_partido           TEXT,
    nm_federacao         TEXT,
    sg_federacao         TEXT,
    nm_coligacao         TEXT,
    dt_nascimento        DATE,
    sg_uf_nascimento     CHAR(2),
    cd_genero            SMALLINT,
    ds_genero            TEXT,
    cd_grau_instrucao    SMALLINT,
    ds_grau_instrucao    TEXT,
    cd_estado_civil      SMALLINT,
    ds_estado_civil      TEXT,
    cd_cor_raca          SMALLINT,
    ds_cor_raca          TEXT,
    cd_ocupacao          INTEGER,
    ds_ocupacao          TEXT,
    situacao             TEXT NOT NULL,   -- eleito | suplente | nao_eleito | segundo_turno | nao_concorreu | sem_resultado
    situacao_herdada     BOOLEAN NOT NULL DEFAULT FALSE,  -- vice: resultado herdado do titular da chapa
    cd_situacao_candidatura SMALLINT,
    ds_situacao_candidatura TEXT,
    cd_sit_tot_turno     SMALLINT,
    ds_sit_tot_turno     TEXT,
    UNIQUE (ano_eleicao, dt_eleicao, nr_turno, sg_ue, cd_cargo, sq_candidato)
);
CREATE INDEX IF NOT EXISTS idx_cand_pessoa ON candidaturas (id_pessoa);
CREATE INDEX IF NOT EXISTS idx_cand_eleicao ON candidaturas (ano_eleicao, nr_turno, cd_cargo);
CREATE INDEX IF NOT EXISTS idx_cand_numero ON candidaturas (ano_eleicao, cd_cargo, nr_candidato);
"""

# Cargos que aparecem na urna (vices e suplentes NÃO têm voto próprio):
# 1 presidente, 3 governador, 5 senador, 6 dep. federal, 7 dep. estadual.
VIEWS = """
CREATE OR REPLACE VIEW v_candidaturas_votaveis AS
SELECT DISTINCT ON (ano_eleicao, nr_turno, cd_cargo, nr_candidato, chave_nome) *
FROM (
    SELECT *, regexp_replace(nm_urna_candidato, '[^[:alnum:]]', '', 'g') AS chave_nome
    FROM candidaturas
    WHERE cd_cargo IN (1, 3, 5, 6, 7)
) t
ORDER BY ano_eleicao, nr_turno, cd_cargo, nr_candidato, chave_nome, sq_candidato DESC;

-- Votos nominais ligados à candidatura e à pessoa. O vínculo usa ano + turno + cargo + número +
-- nome de urna comparado sem pontuação (o TSE troca aspas por espaço no cadastro).
CREATE OR REPLACE VIEW v_votos_candidato AS
SELECT b.ano_eleicao, b.nr_turno, b.cd_municipio, b.nm_municipio, b.nr_zona,
       b.nr_secao, b.nr_local_votacao, b.cd_cargo_pergunta AS cd_cargo,
       c.sq_candidato, c.id_pessoa, c.nm_urna_candidato, c.sg_partido,
       b.qt_votos
FROM boletim_urna b
JOIN v_candidaturas_votaveis c
  ON c.ano_eleicao = b.ano_eleicao
 AND c.nr_turno    = b.nr_turno
 AND c.cd_cargo    = b.cd_cargo_pergunta
 AND c.nr_candidato = b.nr_votavel
 AND c.chave_nome = regexp_replace(b.nm_votavel, '[^[:alnum:]]', '', 'g')
WHERE b.ds_tipo_votavel = 'Nominal';
"""

COLUNAS_DB = [
    "id_pessoa", "ano_eleicao", "dt_eleicao", "nr_turno", "tp_eleicao", "sg_uf", "sg_ue", "nm_ue",
    "cd_cargo", "ds_cargo", "sq_candidato", "nr_candidato", "nm_candidato", "nm_urna_candidato",
    "nm_social_candidato", "tp_abrangencia", "nr_partido", "sg_partido", "nm_partido", "nm_federacao",
    "sg_federacao", "nm_coligacao", "dt_nascimento", "sg_uf_nascimento", "cd_genero", "ds_genero",
    "cd_grau_instrucao", "ds_grau_instrucao", "cd_estado_civil", "ds_estado_civil", "cd_cor_raca",
    "ds_cor_raca", "cd_ocupacao", "ds_ocupacao", "situacao", "situacao_herdada",
    "cd_situacao_candidatura", "ds_situacao_candidatura", "cd_sit_tot_turno", "ds_sit_tot_turno",
]


def _tem(valor) -> bool:
    """Só texto não vazio conta como valor (o pandas deixa vazios como NaN, que é 'verdadeiro')."""
    return isinstance(valor, str) and valor != ""


def _iso(data: str | None) -> str | None:
    """dd/mm/aaaa -> aaaa-mm-dd (None se vazio)."""
    if not _tem(data):
        return None
    d, m, y = data.split("/")
    return f"{y}-{m}-{d}"


def _chave(r) -> str:
    """Chave natural da candidatura, como texto (identifica quem não tem CPF nem título)."""
    return f"{r.ano}|{_iso(r.DT_ELEICAO)}|{r.turno}|{r.SG_UE}|{r.cd_cargo}|{r.SQ_CANDIDATO}"


def _mais_comum(valores, desempate):
    """Valor mais frequente; em empate, o que aparece no ano mais recente."""
    conta = Counter(v for v in valores if _tem(v))
    if not conta:
        return None
    melhor = max(conta.values())
    return next(v for v in desempate if _tem(v) and conta[v] == melhor)


def montar_grupos(a: pd.DataFrame, resumo: pd.DataFrame) -> list[dict]:
    """Uma entrada por pessoa (grupo da resolução de identidade), com tudo o que vai para o banco."""
    info = resumo.set_index("pessoa")
    a = a.assign(_dt=a["DT_ELEICAO"].map(_iso))                           # data ISO ordena certo
    grupos = []
    for gid, g in a.groupby("pessoa", sort=False):
        g = g.sort_values(["ano", "_dt"], ascending=False)                  # mais recente primeiro
        cpfs, titulos = defaultdict(set), defaultdict(set)
        for cpf, tit, ano in zip(g["cpf"], g["titulo"], g["ano"]):
            if _tem(cpf):
                cpfs[cpf].add(int(ano))
            if _tem(tit):
                titulos[tit].add(int(ano))
        chaves = [_chave(r) for r in g.itertuples()]
        social = next((n for n in g["NM_SOCIAL_CANDIDATO"] if _tem(n)), None)
        protegido = bool(g["social_protegido"].any())
        if social:
            exibicao = social
        elif protegido:
            exibicao = next((n for n in g["NM_URNA_CANDIDATO"] if _tem(n)), g["NM_CANDIDATO"].iloc[0])
        else:
            exibicao = g["NM_CANDIDATO"].iloc[0]
        r = info.loc[gid]
        grupos.append({
            "gid": gid, "cpfs": cpfs, "titulos": titulos, "chaves": chaves,
            "chave_ordem": min(chaves), "nm_exibicao": exibicao, "ocultar": protegido,
            "nasc": _iso(_mais_comum(g["nasc"], list(g["nasc"]))),
            "uf_nasc": _mais_comum(g["SG_UF_NASCIMENTO"], list(g["SG_UF_NASCIMENTO"])),
            "nivel": r["nivel"], "revisar": bool(r["motivos"]),
            "tem_ident": bool(cpfs or titulos),
            "anos_por_chave": {k: int(a_) for k, a_ in zip(chaves, g["ano"])},
        })
    grupos.sort(key=lambda x: x["chave_ordem"])           # ordem determinística
    return grupos


def atribuir_ids(cur, grupos: list[dict]) -> dict:
    """Dá a cada grupo um id_pessoa e um slug, reaproveitando os da pessoa já gravada quando
    ela compartilha identificadores (título e chave de candidatura pesam mais que CPF)."""
    existentes = defaultdict(set)
    cur.execute("SELECT id_pessoa, tipo, valor FROM pessoa_identificadores")
    for idp, tipo, valor in cur.fetchall():
        existentes[(tipo, valor)].add(idp)
    cur.execute("SELECT id_pessoa, slug FROM pessoas")
    slugs = dict(cur.fetchall())
    cur.execute("SELECT coalesce(max(id_pessoa), 0) FROM pessoas")
    proximo = cur.fetchone()[0] + 1
    usados, em_uso = set(), set(slugs.values())
    for g in grupos:
        pontos = Counter()
        for t in g["titulos"]:
            for i in existentes.get(("titulo", t), ()):
                pontos[i] += 3
        for k in g["chaves"] if not g["tem_ident"] else ():
            for i in existentes.get(("candidatura", k), ()):
                pontos[i] += 3
        for c in g["cpfs"]:
            for i in existentes.get(("cpf", c), ()):
                pontos[i] += 1
        livres = [(-p, i) for i, p in pontos.items() if i not in usados]
        if livres:
            g["id"] = min(livres)[1]
        else:
            g["id"], proximo = proximo, proximo + 1
        usados.add(g["id"])
        if g["id"] in slugs:
            g["slug"] = slugs[g["id"]]
        else:
            while True:                                   # aleatório, 10 caracteres, sem relação com CPF
                s = base64.b32encode(os.urandom(7)).decode().lower().rstrip("=")[:10]
                if s not in em_uso:
                    break
            em_uso.add(s)
            g["slug"] = s
    return {g["gid"]: g["id"] for g in grupos}


def preparar_esquema(cur) -> str:
    """Cria o esquema novo. Se existir o esquema antigo (pessoas por CPF), troca por ele."""
    cur.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'pessoas' AND column_name = 'nr_cpf'""")
    antigo = cur.fetchone() is not None
    if antigo:
        cur.execute("DROP VIEW IF EXISTS v_votos_candidato")
        cur.execute("DROP VIEW IF EXISTS v_candidaturas_votaveis")
        cur.execute("DROP TABLE IF EXISTS candidaturas CASCADE")
        cur.execute("DROP TABLE IF EXISTS pessoas CASCADE")
    cur.execute(DDL)
    return "substituiu o esquema antigo (pessoas por CPF)" if antigo else "esquema já era o novo"


def gravar(conn, a: pd.DataFrame, resumo: pd.DataFrame) -> dict:
    """Grava pessoas, identificadores e candidaturas numa transação. Devolve estatísticas."""
    cur = conn.cursor()
    try:
        msg = preparar_esquema(cur)
        grupos = montar_grupos(a, resumo)
        id_de = atribuir_ids(cur, grupos)

        # candidaturas e identificadores são refeitos por inteiro; as pessoas são atualizadas no lugar
        cur.execute("DELETE FROM candidaturas")
        cur.execute("DELETE FROM pessoa_identificadores")

        db.execute_values(cur, """
            INSERT INTO pessoas (id_pessoa, slug, nm_exibicao, dt_nascimento, sg_uf_nascimento,
                                 nivel_evidencia, revisar, ocultar_nome_registro)
            VALUES %s
            ON CONFLICT (id_pessoa) DO UPDATE SET
                nm_exibicao = EXCLUDED.nm_exibicao, dt_nascimento = EXCLUDED.dt_nascimento,
                sg_uf_nascimento = EXCLUDED.sg_uf_nascimento, nivel_evidencia = EXCLUDED.nivel_evidencia,
                revisar = EXCLUDED.revisar, ocultar_nome_registro = EXCLUDED.ocultar_nome_registro,
                atualizado_em = now()""",
            [(g["id"], g["slug"], g["nm_exibicao"], g["nasc"], g["uf_nasc"], g["nivel"], g["revisar"],
              g["ocultar"]) for g in grupos])

        ident = []
        for g in grupos:
            ident += [(g["id"], "cpf", c, sorted(an)) for c, an in g["cpfs"].items()]
            ident += [(g["id"], "titulo", t, sorted(an)) for t, an in g["titulos"].items()]
            if not g["tem_ident"]:                         # sem CPF nem título: a chave da candidatura
                ident += [(g["id"], "candidatura", k, [an]) for k, an in g["anos_por_chave"].items()]
        db.execute_values(cur, "INSERT INTO pessoa_identificadores (id_pessoa, tipo, valor, anos) VALUES %s", ident)

        out = pd.DataFrame({
            "id_pessoa": a["pessoa"].map(id_de), "ano_eleicao": a["ano"], "dt_eleicao": a["DT_ELEICAO"].map(_iso),
            "nr_turno": a["turno"], "tp_eleicao": a["tp_eleicao"], "sg_uf": a["SG_UF"], "sg_ue": a["SG_UE"],
            "nm_ue": a["NM_UE"], "cd_cargo": a["cd_cargo"], "ds_cargo": a["DS_CARGO"],
            "sq_candidato": a["SQ_CANDIDATO"], "nr_candidato": a["NR_CANDIDATO"], "nm_candidato": a["NM_CANDIDATO"],
            "nm_urna_candidato": a["NM_URNA_CANDIDATO"], "nm_social_candidato": a["NM_SOCIAL_CANDIDATO"],
            "tp_abrangencia": a["TP_ABRANGENCIA"], "nr_partido": a["NR_PARTIDO"], "sg_partido": a["SG_PARTIDO"],
            "nm_partido": a["NM_PARTIDO"], "nm_federacao": a["NM_FEDERACAO"], "sg_federacao": a["SG_FEDERACAO"],
            "nm_coligacao": a["NM_COLIGACAO"], "dt_nascimento": a["nasc"].map(_iso),
            "sg_uf_nascimento": a["SG_UF_NASCIMENTO"], "cd_genero": a["CD_GENERO"], "ds_genero": a["DS_GENERO"],
            "cd_grau_instrucao": a["CD_GRAU_INSTRUCAO"], "ds_grau_instrucao": a["DS_GRAU_INSTRUCAO"],
            "cd_estado_civil": a["CD_ESTADO_CIVIL"], "ds_estado_civil": a["DS_ESTADO_CIVIL"],
            "cd_cor_raca": a["CD_COR_RACA"], "ds_cor_raca": a["DS_COR_RACA"], "cd_ocupacao": a["CD_OCUPACAO"],
            "ds_ocupacao": a["DS_OCUPACAO"], "situacao": a["situacao"], "situacao_herdada": a["situacao_herdada"],
            "cd_situacao_candidatura": a["CD_SITUACAO_CANDIDATURA"],
            "ds_situacao_candidatura": a["DS_SITUACAO_CANDIDATURA"], "cd_sit_tot_turno": a["CD_SIT_TOT_TURNO"],
            "ds_sit_tot_turno": a["DS_SIT_TOT_TURNO"],
        })[COLUNAS_DB].astype(object)
        out = out.where(out.notna(), None)
        linhas = [tuple(r) for r in out.itertuples(index=False, name=None)]
        db.execute_values(cur, f"INSERT INTO candidaturas ({', '.join(COLUNAS_DB)}) VALUES %s", linhas)

        cur.execute("""DELETE FROM pessoas p WHERE NOT EXISTS
                       (SELECT 1 FROM candidaturas c WHERE c.id_pessoa = p.id_pessoa)""")
        removidas = cur.rowcount
        cur.execute(VIEWS)

        # conferências: se algo não bater, a transação inteira é desfeita
        cur.execute("SELECT count(*) FROM candidaturas"); n_cand = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM pessoas"); n_pes = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM candidaturas c LEFT JOIN pessoas p USING (id_pessoa) WHERE p.id_pessoa IS NULL")
        orfas = cur.fetchone()[0]
        assert n_cand == len(a), f"candidaturas gravadas ({n_cand}) != lidas ({len(a)})"
        assert n_pes == len(grupos), f"pessoas gravadas ({n_pes}) != grupos ({len(grupos)})"
        assert orfas == 0, "há candidaturas sem pessoa"
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"esquema": msg, "candidaturas": n_cand, "pessoas": n_pes, "identificadores": len(ident),
            "pessoas_removidas": removidas}
