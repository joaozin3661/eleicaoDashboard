import csv
import os
import sys

import db

from importar_TSE import DB

sys.stdout.reconfigure(encoding="utf-8")

ARQUIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "locais_para_preencher_manual.csv")
MARGEM_GRAUS = 0.30   # ~33 km além dos locais já conhecidos do município


def numero(txt):
    txt = (txt or "").strip().replace(",", ".")
    return float(txt) if txt else None


def main():
    try:
        texto = open(ARQUIVO, encoding="utf-8-sig").read()
    except UnicodeDecodeError:
        texto = open(ARQUIVO, encoding="cp1252").read()
    linhas = list(csv.DictReader(texto.splitlines(), delimiter=";"))

    conn = db.connect(**DB)
    cur = conn.cursor()
    ok = recusadas = 0
    for r in linhas:
        try:
            lat, lon = numero(r["latitude"]), numero(r["longitude"])
        except ValueError:
            print(f"  [recusado] {r['municipio']} / {r['local']}: coordenada ilegível "
                  f"({r['latitude']!r}, {r['longitude']!r})")
            recusadas += 1
            continue
        if lat is None and lon is None:
            continue                                   
        if lat is None or lon is None:
            print(f"  [recusado] {r['municipio']} / {r['local']}: falta latitude ou longitude")
            recusadas += 1
            continue

        cur.execute("""SELECT cd_municipio, nm_municipio, latitude IS NULL
                       FROM locais_votacao
                       WHERE nm_municipio = %s AND nr_zona = %s AND nr_local_votacao = %s""",
                    (r["municipio"], int(r["zona"]), int(r["cod_local"])))
        achado = cur.fetchone()
        if not achado:
            # nome do município pode ter acento corrompido: tenta só por zona + local
            cur.execute("""SELECT cd_municipio, nm_municipio, latitude IS NULL
                           FROM locais_votacao WHERE nr_zona = %s AND nr_local_votacao = %s""",
                        (int(r["zona"]), int(r["cod_local"])))
            candidatos = cur.fetchall()
            if len(candidatos) != 1:
                print(f"  [recusado] {r['municipio']} / {r['local']}: local não identificado "
                      f"({len(candidatos)} possibilidades)")
                recusadas += 1
                continue
            achado = candidatos[0]
        cd_mun, nm_mun, sem_coord = achado

        if not (-11.0 <= lat <= -2.5 and -46.0 <= lon <= -40.0):
            print(f"  [recusado] {nm_mun} / {r['local']}: {lat}, {lon} está fora do Piauí "
                  f"(latitude/longitude trocadas?)")
            recusadas += 1
            continue
        cur.execute("""SELECT min(latitude), max(latitude), min(longitude), max(longitude)
                       FROM locais_votacao WHERE cd_municipio = %s AND latitude IS NOT NULL""",
                    (cd_mun,))
        a = cur.fetchone()
        if a[0] is not None and not (a[0] - MARGEM_GRAUS <= lat <= a[1] + MARGEM_GRAUS
                                      and a[2] - MARGEM_GRAUS <= lon <= a[3] + MARGEM_GRAUS):
            print(f"  [recusado] {nm_mun} / {r['local']}: {lat}, {lon} está longe dos outros "
                  f"locais de {nm_mun}")
            recusadas += 1
            continue

        cur.execute("""UPDATE locais_votacao
                       SET latitude = %s, longitude = %s, geocodificado = TRUE,
                           fonte_coordenada = 'manual', precisao_coordenada = 'manual'
                       WHERE cd_municipio = %s AND nr_zona = %s AND nr_local_votacao = %s""",
                    (lat, lon, cd_mun, int(r["zona"]), int(r["cod_local"])))
        aviso = "" if sem_coord else "  (substituiu uma coordenada que já existia)"
        print(f"  [ok] {nm_mun} / {r['local'][:45]}: {lat}, {lon}{aviso}")
        ok += 1
    conn.commit()
    conn.close()
    print(f"\nGravadas: {ok} | recusadas: {recusadas}")


if __name__ == "__main__":
    main()
