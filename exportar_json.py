

import json
import os
import shutil
import sys

import db

sys.stdout.reconfigure(encoding="utf-8")

PASTA = os.path.dirname(os.path.abspath(__file__))
TOP_MUNICIPIO = 10          # candidatos por município no resultado do estado (mapa de cores)

SQL_RESUMOS = """
DROP TABLE IF EXISTS resumo_votos_candidato_local;
CREATE TABLE resumo_votos_candidato_local AS
SELECT ano_eleicao, nr_turno, cd_cargo, cd_municipio, nr_zona, nr_local_votacao,
       sq_candidato, sum(qt_votos)::int AS votos
FROM v_votos_candidato
GROUP BY 1, 2, 3, 4, 5, 6, 7;
CREATE INDEX ON resumo_votos_candidato_local (ano_eleicao, nr_turno, cd_cargo, cd_municipio);

DROP TABLE IF EXISTS resumo_local_cargo;
CREATE TABLE resumo_local_cargo AS
WITH secao AS (
    SELECT ano_eleicao, nr_turno, cd_cargo_pergunta AS cd_cargo, cd_municipio, nr_zona,
           nr_local_votacao, nr_secao,
           max(qt_aptos) AS aptos, max(qt_comparecimento) AS comparecimento
    FROM boletim_urna GROUP BY 1, 2, 3, 4, 5, 6, 7
), local_ AS (
    SELECT ano_eleicao, nr_turno, cd_cargo, cd_municipio, nr_zona, nr_local_votacao,
           sum(aptos)::int AS aptos, sum(comparecimento)::int AS comparecimento
    FROM secao GROUP BY 1, 2, 3, 4, 5, 6
), v AS (
    SELECT ano_eleicao, nr_turno, cd_cargo_pergunta AS cd_cargo, cd_municipio, nr_zona,
           nr_local_votacao,
           coalesce(sum(qt_votos) FILTER (WHERE ds_tipo_votavel = 'Branco'), 0)::int  AS brancos,
           coalesce(sum(qt_votos) FILTER (WHERE ds_tipo_votavel = 'Nulo'), 0)::int    AS nulos,
           coalesce(sum(qt_votos) FILTER (WHERE ds_tipo_votavel = 'Legenda'), 0)::int AS legenda,
           coalesce(sum(qt_votos) FILTER (WHERE ds_tipo_votavel = 'Nominal'), 0)::int AS nominais
    FROM boletim_urna GROUP BY 1, 2, 3, 4, 5, 6
)
SELECT * FROM local_ JOIN v USING (ano_eleicao, nr_turno, cd_cargo, cd_municipio, nr_zona,
                                   nr_local_votacao);
CREATE INDEX ON resumo_local_cargo (ano_eleicao, nr_turno, cd_cargo, cd_municipio);
"""

CAMPOS_TOTAIS = ("aptos", "comparecimento", "brancos", "nulos", "legenda", "nominais")


def gravar(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def somar(linhas):
    """Soma os 6 totais de uma lista de linhas do resumo_local_cargo."""
    return {c: sum(l[c] for l in linhas) for c in CAMPOS_TOTAIS}


def main(saida):
    conn = db.connect(**db.config())
    cur = conn.cursor()

    def consulta(sql, params=()):
        cur.execute(sql, params)
        nomes = [d[0] for d in cur.description]
        return [dict(zip(nomes, r)) for r in cur.fetchall()]

    print("→ Criando tabelas resumo ...")
    cur.execute(SQL_RESUMOS)
    conn.commit()

    if os.path.isdir(saida):
        # Só apaga uma exportação anterior nossa (tem index.json). Nunca uma pasta qualquer.
        if os.listdir(saida) and not os.path.exists(os.path.join(saida, "index.json")):
            sys.exit(f"A pasta {saida} não está vazia e não é uma exportação anterior. "
                     f"Escolha outra com --saida.")
        shutil.rmtree(saida)           # evita arquivos velhos de uma exportação anterior

    eleicoes = consulta("""SELECT DISTINCT ano_eleicao AS ano, nr_turno AS turno
                           FROM resumo_local_cargo ORDER BY 1, 2""")
    cargos = {r["cd"]: r["nome"] for r in consulta(
        "SELECT DISTINCT cd_cargo_pergunta AS cd, ds_cargo_pergunta AS nome FROM boletim_urna")}
    municipios = consulta("""SELECT DISTINCT cd_municipio AS cd, nm_municipio AS nome
                             FROM boletim_urna ORDER BY 2""")
    nome_mun = {m["cd"]: m["nome"] for m in municipios}
    gerado = consulta("SELECT max(dt_geracao) AS d FROM boletim_urna")[0]["d"]

    gravar(os.path.join(saida, "index.json"), {
        "fonte": "TSE - Dados Abertos (boletim de urna, candidatos, locais de votação)",
        "dados_gerados_em": str(gerado),
        "eleicoes": [{"ano": e["ano"], "turno": e["turno"],
                      "cargos": [{"cd": c, "nome": n} for c, n in sorted(cargos.items())]}
                     for e in eleicoes],
        "municipios": [{"cd": m["cd"], "nome": m["nome"]} for m in municipios],
    })

    problemas = []
    for e in eleicoes:
        ano, turno = e["ano"], e["turno"]
        tag = f"{ano}-{turno}"
        print(f"\n→ Eleição {ano}, turno {turno}")

        # -- candidatos (somente os que aparecem na urna; sem CPF/título) 
        cands = consulta("""SELECT sq_candidato, nm_urna_candidato AS n, sg_partido AS p,
                                   nr_candidato AS nr, cd_cargo AS c, nm_candidato AS nc, id_pessoa AS pessoa
                            FROM v_candidaturas_votaveis WHERE ano_eleicao = %s""", (ano,))
        gravar(os.path.join(saida, f"candidatos-{ano}.json"),
               {str(c["sq_candidato"]): {k: c[k] for k in ("n", "p", "nr", "c", "nc", "pessoa")}
                for c in cands})

        # -- locais de votação (só campos públicos e úteis ao mapa) 
        locais = consulta("""SELECT cd_municipio, nr_zona, nr_local_votacao, nm_local_votacao AS nome,
                                    bairro, endereco, latitude AS lat, longitude AS lon,
                                    precisao_coordenada AS prec, ds_tipo_local AS tipo,
                                    ds_situacao_local AS situacao
                             FROM locais_votacao""")
        info_local = {(l["cd_municipio"], l["nr_zona"], l["nr_local_votacao"]): l for l in locais}

        for cd_cargo, nome_cargo in sorted(cargos.items()):
            todos = consulta("""SELECT * FROM resumo_local_cargo
                                WHERE ano_eleicao=%s AND nr_turno=%s AND cd_cargo=%s""",
                             (ano, turno, cd_cargo))
            votos = consulta("""SELECT cd_municipio, nr_zona, nr_local_votacao, sq_candidato, votos
                                FROM resumo_votos_candidato_local
                                WHERE ano_eleicao=%s AND nr_turno=%s AND cd_cargo=%s""",
                             (ano, turno, cd_cargo))
            por_mun, votos_mun = {}, {}
            for l in todos:
                por_mun.setdefault(l["cd_municipio"], []).append(l)
            for v in votos:
                votos_mun.setdefault(v["cd_municipio"], []).append(v)

            # ---- resultado do estado ----
            total_cand, mun_resumo = {}, []
            for cd_mun in sorted(por_mun, key=lambda c: nome_mun[c]):
                cand_mun = {}
                for v in votos_mun.get(cd_mun, []):
                    cand_mun[v["sq_candidato"]] = cand_mun.get(v["sq_candidato"], 0) + v["votos"]
                    total_cand[v["sq_candidato"]] = total_cand.get(v["sq_candidato"], 0) + v["votos"]
                top = sorted(cand_mun.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_MUNICIPIO]
                mun_resumo.append({"cd": cd_mun, "nome": nome_mun[cd_mun],
                                   "totais": somar(por_mun[cd_mun]),
                                   "top": [[str(sq), n] for sq, n in top]})
            todos_ord = sorted(total_cand.items(), key=lambda kv: (-kv[1], kv[0]))
            tot_estado = somar(todos)
            gravar(os.path.join(saida, "estado", f"{tag}-{cd_cargo}.json"), {
                "ano": ano, "turno": turno, "cargo": {"cd": cd_cargo, "nome": nome_cargo},
                "totais": tot_estado,
                "candidatos": [[str(sq), n] for sq, n in todos_ord],
                "municipios": mun_resumo,
            })
            if sum(total_cand.values()) != tot_estado["nominais"]:
                problemas.append(f"{tag} {nome_cargo}: candidatos {sum(total_cand.values())} "
                                 f"!= nominais {tot_estado['nominais']}")
            print(f"   {nome_cargo:<18} {len(todos_ord):>4} candidatos, "
                  f"{tot_estado['nominais']:>9,} votos nominais")

            # ---- um arquivo por município (acumulado entre cargos) ----
            for cd_mun, linhas in por_mun.items():
                arq = os.path.join(saida, "municipios", tag, f"{cd_mun}.json")
                doc = json.load(open(arq, encoding="utf-8")) if os.path.exists(arq) else {
                    "cd": cd_mun, "nome": nome_mun[cd_mun], "locais": [], "cargos": {}}
                idx = {(l["z"], l["l"]): i for i, l in enumerate(doc["locais"])}
                votos_local = {}
                for v in votos_mun.get(cd_mun, []):
                    votos_local.setdefault((v["nr_zona"], v["nr_local_votacao"]), {})[
                        str(v["sq_candidato"])] = v["votos"]
                tot_cand_mun, linhas_local = {}, []
                for l in sorted(linhas, key=lambda x: (x["nr_zona"], x["nr_local_votacao"])):
                    chave = (l["nr_zona"], l["nr_local_votacao"])
                    if chave not in idx:
                        i = info_local.get((cd_mun,) + chave)
                        idx[chave] = len(doc["locais"])
                        doc["locais"].append({
                            "z": chave[0], "l": chave[1],
                            "nome": i["nome"] if i else None, "bairro": i["bairro"] if i else None,
                            "end": i["endereco"] if i else None,
                            "lat": i["lat"] if i else None, "lon": i["lon"] if i else None,
                            "prec": i["prec"] if i else None, "tipo": i["tipo"] if i else None,
                            "sit": i["situacao"] if i else None})
                    vl = votos_local.get(chave, {})
                    for sq, n in vl.items():
                        tot_cand_mun[sq] = tot_cand_mun.get(sq, 0) + n
                    linhas_local.append([idx[chave], l["aptos"], l["comparecimento"], l["brancos"],
                                         l["nulos"], l["legenda"], vl])
                doc["cargos"][str(cd_cargo)] = {
                    "nome": nome_cargo, "totais": somar(linhas),
                    "candidatos": [[sq, n] for sq, n in
                                   sorted(tot_cand_mun.items(), key=lambda kv: (-kv[1], kv[0]))],
                    "por_local": linhas_local,
                    "colunas_por_local": ["idx_local", "aptos", "comparecimento", "brancos",
                                          "nulos", "legenda", "votos_por_candidato"],
                }
                gravar(arq, doc)

    # ---- conferência final: o que está nos arquivos bate com o banco? ----
    print("\n→ Conferindo os arquivos gerados contra o banco ...")
    for e in eleicoes:
        tag = f"{e['ano']}-{e['turno']}"
        for cd_cargo in cargos:
            esperado = consulta("""SELECT coalesce(sum(votos),0)::bigint AS n FROM resumo_votos_candidato_local
                                   WHERE ano_eleicao=%s AND nr_turno=%s AND cd_cargo=%s""",
                                (e["ano"], e["turno"], cd_cargo))[0]["n"]
            soma = 0
            pasta = os.path.join(saida, "municipios", tag)
            for nome_arq in os.listdir(pasta):
                d = json.load(open(os.path.join(pasta, nome_arq), encoding="utf-8"))
                c = d["cargos"].get(str(cd_cargo))
                if c:
                    soma += sum(n for _, n in c["candidatos"])
                    soma_locais = sum(sum(l[6].values()) for l in c["por_local"])
                    if soma_locais != sum(n for _, n in c["candidatos"]):
                        problemas.append(f"{tag} {cargos[cd_cargo]} município {d['cd']}: locais != total")
            if soma != esperado:
                problemas.append(f"{tag} {cargos[cd_cargo]}: arquivos de município somam {soma}, "
                                 f"banco tem {esperado}")
            print(f"   {cargos[cd_cargo]:<18} municípios somam {soma:>10,} | banco {esperado:>10,} "
                  f"{'OK' if soma == esperado else 'DIFERENTE'}")

    # segurança: nenhum campo sensível nos arquivos
    for raiz, _, arqs in os.walk(saida):
        for a in arqs:
            txt = open(os.path.join(raiz, a), encoding="utf-8").read()
            for proibido in ("nr_cpf", "titulo_eleitor", "nr_titulo"):
                if proibido in txt:
                    problemas.append(f"{a}: contém '{proibido}'")

    n_arq = sum(len(a) for _, _, a in os.walk(saida))
    tamanho = sum(os.path.getsize(os.path.join(r, a)) for r, _, aa in os.walk(saida) for a in aa)
    print(f"\n{n_arq} arquivos, {tamanho / 1024 / 1024:.1f} MB em {saida}")
    conn.close()
    if problemas:
        print("\nPROBLEMAS ENCONTRADOS:")
        for p in problemas:
            print("  -", p)
        sys.exit(1)
    print("✓ Exportação conferida: sem divergências.")


if __name__ == "__main__":
    destino = os.path.join(PASTA, "web", "public", "data")
    if "--saida" in sys.argv:
        destino = os.path.abspath(sys.argv[sys.argv.index("--saida") + 1])
    main(destino)
