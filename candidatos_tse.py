"""
Leitura e limpeza dos arquivos de candidatos do TSE (consulta_cand_*), de qualquer ano.

Os layouts mudaram ao longo dos anos (50, 63, 71 e 75 colunas), mas as colunas usadas aqui
existem em todos. Este módulo só lê e normaliza: não acessa o banco.
"""

import datetime
import glob
import os
import re
import unicodedata

import pandas as pd

COLUNAS = [
    "ANO_ELEICAO", "DT_ELEICAO", "DS_ELEICAO", "NR_TURNO", "SG_UF", "SG_UE", "NM_UE",
    "CD_CARGO", "DS_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO", "NM_CANDIDATO", "NM_URNA_CANDIDATO",
    "SG_PARTIDO", "DS_SIT_TOT_TURNO", "DS_SITUACAO_CANDIDATURA",
    "NR_CPF_CANDIDATO", "NR_TITULO_ELEITORAL_CANDIDATO", "DT_NASCIMENTO",
]

# Colunas extras gravadas no banco (os anos antigos não têm federação; ficam vazias).
COLUNAS_EXTRAS = [
    "NM_SOCIAL_CANDIDATO", "SG_UF_NASCIMENTO", "TP_ABRANGENCIA", "NR_PARTIDO", "NM_PARTIDO",
    "NM_FEDERACAO", "SG_FEDERACAO", "NM_COLIGACAO", "CD_GENERO", "DS_GENERO",
    "CD_GRAU_INSTRUCAO", "DS_GRAU_INSTRUCAO", "CD_ESTADO_CIVIL", "DS_ESTADO_CIVIL",
    "CD_COR_RACA", "DS_COR_RACA", "CD_OCUPACAO", "DS_OCUPACAO",
    "CD_SIT_TOT_TURNO", "CD_SITUACAO_CANDIDATURA",
]

# O TSE usa estes valores para "sem informação" (-4 = dado protegido/oculto).
NULOS = {"", "#NULO", "#NULO#", "#NE", "#NE#", "-1", "-3", "-4"}

# O TSE esconde o nome social de alguns candidatos com este texto. Não é um nome: é um aviso de
# proteção. Quem o tem não deve ter o nome de registro exibido publicamente.
NAO_DIVULGAVEL = "NAO DIVULGAVEL"


def eh_nao_divulgavel(valor) -> bool:
    """O TSE escreve 'NÃO DIVULGÁVEL', 'Não divulgável'... conforme o ano: compara sem acento e sem caixa."""
    return isinstance(valor, str) and sem_acento(valor).upper() == NAO_DIVULGAVEL


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()


def nome_normalizado(texto: str | None) -> str | None:
    """MAIÚSCULAS, sem acento nem pontuação, espaços colapsados."""
    if not texto:
        return None
    t = re.sub(r"[^A-Z ]", "", sem_acento(texto).upper())
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def cpf_valido(c: str) -> bool:
    """11 dígitos, não todos iguais, dígitos verificadores corretos."""
    if not re.fullmatch(r"\d{11}", c) or len(set(c)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(c[i]) * (n + 1 - i) for i in range(n))
        if int(c[n]) != (soma * 10 % 11) % 10:
            return False
    return True


def cpf_normalizado(valor: str | None) -> tuple[str | None, str]:
    """Devolve (cpf, situação). Repõe zeros à esquerda perdidos (ocorre em 2012)."""
    if valor is None:
        return None, "ausente"
    if re.fullmatch(r"\d{1,10}", valor):
        valor, recuperado = valor.zfill(11), True
    else:
        recuperado = False
    if cpf_valido(valor):
        return valor, "recuperado" if recuperado else "ok"
    return None, "invalido"


def titulo_normalizado(valor: str | None) -> str | None:
    """Título de eleitor: 12 dígitos, não zerado."""
    if valor and re.fullmatch(r"\d{12}", valor) and valor.strip("0"):
        return valor
    return None


def nascimento_normalizado(valor: str | None, ano_eleicao: int) -> str | None:
    """dd/mm/aaaa plausível (candidato com 16 a 100 anos na eleição); senão, None."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", valor or "")
    if not m:
        return None
    d, mes, ano = map(int, m.groups())
    try:
        datetime.date(ano, mes, d)                      # recusa dias que não existem (ex.: 29/02/1957)
    except ValueError:
        return None
    return valor if 16 <= ano_eleicao - ano <= 100 else None


# situação final (DS_SIT_TOT_TURNO), em texto sem acento e maiúsculo -> categoria canônica
_SITUACAO = {
    "ELEITO": "eleito", "ELEITO POR QP": "eleito", "ELEITO POR MEDIA": "eleito", "MEDIA": "eleito",
    "SUPLENTE": "suplente",
    "NAO ELEITO": "nao_eleito",
    "2 TURNO": "segundo_turno",
}
_BLOQUEADA = ("NEGADO", "INDEFERID", "RENUNCIA", "FALECIMENTO", "CASSACAO", "CANCELAD", "SUBSTITUID", "NAO CONHECIMENTO", "INAPTO")


def situacao_canonica(sit_total: str | None, sit_candidatura: str | None) -> str:
    """eleito | suplente | nao_eleito | segundo_turno | nao_concorreu | sem_resultado."""
    s = sem_acento(sit_total or "").upper().strip()
    s = re.sub(r"\b(\d)[O°]\b", r"\1", s)    # "2º TURNO" (vira "2O" sem acento) -> "2 TURNO"
    s = re.sub(r"\s+", " ", s)
    if s in _SITUACAO:
        return _SITUACAO[s]
    texto = f"{s} {sem_acento(sit_candidatura or '').upper()}"
    if any(p in texto for p in _BLOQUEADA):
        return "nao_concorreu"
    return "sem_resultado"


# vice -> cargo do titular da chapa (vice-presidente, vice-governador, vice-prefeito)
_TITULAR_DO_VICE = {2: 1, 4: 3, 12: 11}


def _herdar_resultado_dos_vices(a: pd.DataFrame) -> None:
    """O arquivo não traz resultado para vices: eles herdam o do titular da chapa
    (mesma eleição, turno, unidade e número). Marca em `situacao_herdada`."""
    chave = ["ano", "DT_ELEICAO", "turno", "SG_UE", "NR_CANDIDATO"]
    titulares = a[a["cd_cargo"].isin(_TITULAR_DO_VICE.values()) & (a["situacao"] != "sem_resultado")]
    resultado = {(*k, c): s for k, c, s in zip(map(tuple, titulares[chave].values), titulares["cd_cargo"],
                                                titulares["situacao"])}
    a["situacao_herdada"] = False
    for i in a.index[a["cd_cargo"].isin(_TITULAR_DO_VICE) & (a["situacao"] == "sem_resultado")]:
        k = (*tuple(a.loc[i, chave]), _TITULAR_DO_VICE[a.at[i, "cd_cargo"]])
        if k in resultado:
            a.at[i, "situacao"], a.at[i, "situacao_herdada"] = resultado[k], True


def carregar(raiz: str = ".", completo: bool = False) -> tuple[pd.DataFrame, dict]:
    """Lê todos os consulta_cand_*.csv das pastas candidato*/ e devolve (candidaturas, estatísticas).
    Com completo=True traz também as colunas extras que vão para o banco."""
    colunas = COLUNAS + (COLUNAS_EXTRAS if completo else [])
    arquivos = sorted(glob.glob(os.path.join(raiz, "candidato*", "consulta_cand_*.csv")))
    if not arquivos:
        raise SystemExit(f"Nenhum consulta_cand_*.csv encontrado em {raiz}/candidato*/")
    stats = {"arquivos": [], "cpf": {}, "datas_invalidas": {}, "protegidas": {}}
    quadros = []
    for f in arquivos:
        base = os.path.basename(f)[:-4].split("_")
        ano_arq, uf_arq = int(base[-2]), base[-1]
        d = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str, keep_default_na=False,
                        usecols=lambda c: c in colunas)
        for faltando in colunas:                       # coluna que o layout daquele ano não tem
            if faltando not in d.columns:
                d[faltando] = ""
        d = d.apply(lambda s: s.str.strip())
        stats["arquivos"].append((os.path.basename(f), len(d)))
        d["arquivo_ano"], d["arquivo_uf"] = ano_arq, uf_arq

        protegida = d["NR_TITULO_ELEITORAL_CANDIDATO"].eq("-4")      # dado protegido (sem título/CPF/nascimento)
        bruto = d.copy()
        social_protegido = bruto["NM_SOCIAL_CANDIDATO"].map(eh_nao_divulgavel)
        for c in colunas:
            # object + None (e não NaN): o resto do código espera texto ou None
            vazio = d[c].isin(NULOS) | d[c].map(eh_nao_divulgavel)
            d[c] = d[c].astype(object).where(~vazio, None)

        cpfs = [cpf_normalizado(v) for v in d["NR_CPF_CANDIDATO"]]
        d["cpf"] = [c for c, _ in cpfs]
        situ = pd.Series([s for _, s in cpfs])
        stats["cpf"][ano_arq, uf_arq] = situ.value_counts().to_dict()
        # CPF oculto pelo TSE ('-4'/'-1') conta como "oculto", não como "ausente"
        oculto = bruto["NR_CPF_CANDIDATO"].isin({"-4", "-1"}).to_numpy()
        stats["cpf"][ano_arq, uf_arq]["oculto"] = int(oculto.sum())

        d["titulo"] = d["NR_TITULO_ELEITORAL_CANDIDATO"].map(titulo_normalizado)
        d["ano"] = d["ANO_ELEICAO"].astype(int)
        d["nasc"] = [nascimento_normalizado(n, a) for n, a in zip(d["DT_NASCIMENTO"], d["ano"])]
        stats["datas_invalidas"][ano_arq, uf_arq] = int(
            (d["nasc"].isna() & d["DT_NASCIMENTO"].notna()).sum())
        d["protegida"] = protegida.to_numpy()
        d["social_protegido"] = social_protegido.to_numpy()
        stats["protegidas"][ano_arq, uf_arq] = int(protegida.sum())
        quadros.append(d)

    a = pd.concat(quadros, ignore_index=True)
    a["nome_norm"] = a["NM_CANDIDATO"].map(nome_normalizado)
    a["tp_eleicao"] = a["DS_ELEICAO"].fillna("").map(
        lambda t: "suplementar" if re.search(r"suplementar|\bsup\.", t, re.I) else "ordinaria")
    a["turno"] = a["NR_TURNO"].astype(int)
    a["cd_cargo"] = a["CD_CARGO"].astype(int)
    a["situacao"] = [situacao_canonica(s, c) for s, c in zip(a["DS_SIT_TOT_TURNO"], a["DS_SITUACAO_CANDIDATURA"])]
    _herdar_resultado_dos_vices(a)
    return a, stats
