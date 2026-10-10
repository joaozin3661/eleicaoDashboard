"""
Geocodifica os locais de votação que o TSE deixou sem coordenada.

Uso:
    python geocodificar_locais.py            # teste: busca e grava só o log (não altera o banco)
    python geocodificar_locais.py --gravar   # grava no banco as coordenadas aprovadas

Fonte: Nominatim (OpenStreetMap), ~1 requisição/segundo (política de uso).
Regras de segurança:
  - o resultado precisa citar o município e cair na área dos outros locais dele;
  - resultado que é um estabelecimento só vale se o nome bater (não aceita "outra
    escola da mesma rua"); riacho, estrada e igreja de outro nome são recusados;
  - cada ponto recebe uma PRECISÃO: 'exata' (prédio achado pelo nome), 'rua'
    (centro da rua) ou 'povoado' (centro do povoado/localidade);
  - nunca usa o centro do município como se fosse o local;
  - não sobrescreve coordenada que já existe.
Os resultados ficam em geocodificacao_log.csv (inclusive o que não foi achado)
e em geocodificacao_cache.json (reexecutar não repete buscas).
"""

import csv
import json
import unicodedata
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import db

from importar_TSE import DB

sys.stdout.reconfigure(encoding="utf-8")

PASTA = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(PASTA, "geocodificacao_cache.json")
LOG = os.path.join(PASTA, "geocodificacao_log.csv")
USER_AGENT = "eleicao-pi-painel/1.0 (projeto academico)"   # sem dados pessoais
PAUSA = 1.2          # segundos entre requisições
MARGEM_GRAUS = 0.20  # ~22 km em volta dos locais já conhecidos do município
PREFIXOS_ZONA = ("POVOADO", "POV.", "POV ", "LOCALIDADE", "LOC.", "ASSENTAMENTO", "SITIO", "SÍTIO", "FAZENDA")


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9 ]", " ", t.upper()).strip()


GENERICAS = set("""ESCOLA MUNICIPAL UNIDADE ESCOLAR UE UEM GRUPO CRECHE POSTO SAUDE UBS PSF CMEI
CENTRO COLEGIO DE DA DO DAS DOS E EM NA NO ESC MUL MUN UNID BASICA PRE POV POVOADO
LOCALIDADE ASSENTAMENTO""".split())
ABREVIACOES = {r"\bPCA\b": "PRAÇA", r"\bPC\b": "PRAÇA", r"\bAV\b": "AVENIDA",
               r"\bTRAV\b": "TRAVESSA", r"\bR\b": "RUA"}
TIPOS_POVOADO = {"hamlet", "village", "isolated_dwelling", "locality", "suburb",
                 "neighbourhood", "administrative", "town", "city"}


def nome_confere(nome_local, nome_osm):
    """O 1º trecho do resultado tem que ter ao menos metade das palavras distintivas do local."""
    alvo = [t for t in norm(nome_local).split() if t not in GENERICAS] or norm(nome_local).split()
    achado = set(norm(nome_osm).split())
    return bool(alvo) and sum(t in achado for t in alvo) / len(alvo) >= 0.5


def avaliar(local, como, res):
    """Devolve a precisão ('exata'|'rua'|'povoado') ou None se o resultado não serve."""
    nome_osm = res.get("display_name", "")
    if norm(local["municipio"]) not in norm(nome_osm):
        return None                                     # caiu em outro município
    categoria, tipo = res.get("category", ""), res.get("type", "")
    if como == "povoado":
        return "povoado" if tipo in TIPOS_POVOADO else None   # riacho/estrada não valem
    if categoria in ("amenity", "building", "office", "shop", "healthcare", "education"):
        primeiro = nome_osm.split(",")[0]
        return "exata" if nome_confere(local["nome"], primeiro) else None
    if como.startswith("endereço") and categoria in ("highway", "leisure", "place"):
        return "rua"
    return None


def limpar_endereco(txt):
    """Remove ruído do cadastro: 'S/N', 'CÓDIGO ÚNICO 123', 'KM 07', 'N 39'."""
    if not txt:
        return ""
    t = re.sub(r"C[ÓO]DIGO\s+[ÚU]NICO\s*\d+", " ", txt, flags=re.I)
    t = re.sub(r"\bS/?N\b|\bSN\b", " ", t, flags=re.I)
    for padrao, troca in ABREVIACOES.items():
        t = re.sub(padrao, troca, t, flags=re.I)
    t = re.sub(r"\s+-\s+(BAIRRO|POV\.?|POVOADO)\b", r", \1", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" ,-")


def nome_povoado(endereco):
    """'POVOADO ROCA VELHA' / 'POV. VIANA S/N' -> 'Roca Velha' (None se não for povoado)."""
    e = limpar_endereco(endereco).upper()
    for p in PREFIXOS_ZONA:
        if e.startswith(p):
            resto = e[len(p):].strip(" .-")
            resto = re.sub(r"\s*-\s*.*$", "", resto)          # corta 'POVOADO X - EXU'
            return resto.title() if resto else None
    return None


def consultas(local):
    """Lista de (descrição, texto de busca), da mais específica para a mais ampla."""
    mun, nome = local["municipio"].title(), local["nome"].title()
    sufixo = f"{mun}, Piauí, Brasil"
    out = [("nome+município", f"{nome}, {sufixo}")]
    end = limpar_endereco(local["endereco"])
    bairro = (local["bairro"] or "").title()
    if end and not end.upper().startswith(PREFIXOS_ZONA):
        partes = [end.title()]
        if bairro and bairro.upper() not in ("ZONA RURAL",):
            partes.append(bairro)
        out.append(("endereço+bairro", ", ".join(partes + [sufixo])))
        if bairro:                                      # "Centro" às vezes atrapalha a busca
            out.append(("endereço", f"{end.title()}, {sufixo}"))
    pov = nome_povoado(local["endereco"])
    if pov:
        out.append(("povoado", f"{pov}, {sufixo}"))
    return out


def buscar(texto):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": texto, "format": "jsonv2", "limit": 3, "countrycodes": "br",
         "accept-language": "pt-BR"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:                                  # rede/limite: espera e tenta de novo
            print(f"    (erro: {e}; tentativa {tentativa + 1}/3)")
            time.sleep(5 * (tentativa + 1))
    return None


def dentro_da_area(lat, lon, area):
    return (area[0] - MARGEM_GRAUS <= lat <= area[1] + MARGEM_GRAUS
            and area[2] - MARGEM_GRAUS <= lon <= area[3] + MARGEM_GRAUS)


def main(gravar):
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    conn = db.connect(**DB)
    cur = conn.cursor()
    cur.execute("ALTER TABLE locais_votacao ADD COLUMN IF NOT EXISTS precisao_coordenada TEXT")
    cur.execute("""UPDATE locais_votacao SET precisao_coordenada = 'tse'
                   WHERE fonte_coordenada = 'tse' AND precisao_coordenada IS NULL""")
    conn.commit()

    # área (caixa) dos locais já conhecidos de cada município
    cur.execute("""SELECT cd_municipio, min(latitude), max(latitude), min(longitude), max(longitude)
                   FROM locais_votacao WHERE latitude IS NOT NULL GROUP BY 1""")
    areas = {r[0]: r[1:] for r in cur.fetchall()}

    cur.execute("""
        SELECT l.cd_municipio, l.nr_zona, l.nr_local_votacao, l.nm_municipio, l.nm_local_votacao,
               l.endereco, l.bairro,
               COALESCE((SELECT sum(qt_votos) FROM boletim_urna b
                         WHERE b.cd_municipio = l.cd_municipio AND b.nr_zona = l.nr_zona
                           AND b.nr_local_votacao = l.nr_local_votacao AND b.cd_cargo_pergunta = 3), 0) v
        FROM locais_votacao l WHERE l.latitude IS NULL ORDER BY v DESC, 4, 5""")
    pend = [dict(zip(("cd_mun", "zona", "nr", "municipio", "nome", "endereco", "bairro", "votos"), r))
            for r in cur.fetchall()]
    print(f"{len(pend)} locais sem coordenada ({sum(1 for p in pend if p['votos'] > 0)} com votos)")

    log, aprovados = [], []
    for i, loc in enumerate(pend, 1):
        achou = None
        area = areas.get(loc["cd_mun"])
        for como, texto in consultas(loc):
            if texto not in cache:
                cache[texto] = buscar(texto)
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                time.sleep(PAUSA)
            for res in cache[texto] or []:
                lat, lon = float(res["lat"]), float(res["lon"])
                if area is not None and not dentro_da_area(lat, lon, area):
                    continue
                precisao = avaliar(loc, como, res)
                if precisao:
                    achou = (como, texto, lat, lon, res.get("display_name", ""), precisao)
                    break
            if achou:
                break
        print(f"[{i:>2}/{len(pend)}] {loc['municipio'][:18]:<18} {loc['nome'][:40]:<40} "
              f"{'OK ' + achou[0] if achou else 'não encontrado'}")
        log.append({
            "municipio": loc["municipio"], "zona": loc["zona"], "cod_local": loc["nr"],
            "local": loc["nome"], "endereco": loc["endereco"], "bairro": loc["bairro"],
            "votos_governador": int(loc["votos"]),
            "resultado": "ENCONTRADO" if achou else "NAO_ENCONTRADO",
            "metodo": achou[0] if achou else "", "latitude": achou[2] if achou else "",
            "longitude": achou[3] if achou else "", "precisao": achou[5] if achou else "",
            "endereco_osm": achou[4] if achou else "",
        })
        if achou:
            aprovados.append((loc, achou))

    with open(LOG, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(log[0]), delimiter=";")
        w.writeheader()
        w.writerows(log)

    com_voto = [l for l in log if l["votos_governador"] > 0]
    print(f"\nEncontrados: {len(aprovados)}/{len(pend)} "
          f"(com votos: {sum(1 for l in com_voto if l['resultado'] == 'ENCONTRADO')}/{len(com_voto)})")
    print(f"Log: {LOG}")

    if gravar:
        for loc, (como, _t, lat, lon, _d, precisao) in aprovados:
            cur.execute(
                """UPDATE locais_votacao SET latitude = %s, longitude = %s, geocodificado = TRUE,
                          fonte_coordenada = 'nominatim', precisao_coordenada = %s
                   WHERE cd_municipio = %s AND nr_zona = %s AND nr_local_votacao = %s
                     AND latitude IS NULL""",
                (lat, lon, precisao, loc["cd_mun"], loc["zona"], loc["nr"]))
        conn.commit()
        print(f"Gravados no banco: {len(aprovados)}")
    else:
        print("Modo teste: nada foi gravado. Confira o log e rode com --gravar.")
    conn.close()


if __name__ == "__main__":
    main("--gravar" in sys.argv)
