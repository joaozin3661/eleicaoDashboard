"""
Resolução de identidade: descobre quais candidaturas, de qualquer ano, são da mesma pessoa.

Princípios (validados com os dados do Piauí, 2000–2026):
  * Nenhum identificador é confiável sozinho: CPF e título têm erros de digitação do TSE, o CPF
    vem oculto em alguns anos e a data de nascimento também erra.
  * Duas candidaturas só se ligam quando DOIS sinais concordam
    (CPF+nome, CPF+nascimento, título+nome, título+nascimento ou nome+nascimento).
  * Um CPF diferente NÃO impede a ligação (uma pessoa pode ter dois CPFs, um cancelado).
  * Candidaturas com dado protegido (sem título, CPF nem nascimento) nunca se ligam sozinhas.
  * Decisões manuais (decisoes_identidade.csv) têm prioridade sobre as regras.

Não acessa o banco: recebe e devolve DataFrames.
"""

import csv
import os
from collections import Counter

import pandas as pd

# (rótulo, colunas) em ordem de força; cada regra liga linhas que compartilham TODAS as colunas.
REGRAS = [
    ("cpf+nome", ["cpf", "nome_norm"]),
    ("cpf+nascimento", ["cpf", "nasc"]),
    ("titulo+nome", ["titulo", "nome_norm"]),
    ("titulo+nascimento", ["titulo", "nasc"]),
    ("nome+nascimento", ["nome_norm", "nasc"]),
]


def pad(valor: str | None, n: int) -> str | None:
    """O Excel apaga zeros à esquerda; repõe (CPF=11, título=12)."""
    v = (valor or "").strip()
    return v.zfill(n) if v.isdigit() else None


def ler_decisoes(caminho: str) -> list[dict]:
    """decisoes_identidade.csv: tipo;valor_a;valor_b;nota.
    tipos: separar_titulo (nunca juntar os dois títulos) | juntar_titulo (sempre juntar) |
           isolar_candidatura (o registro tem CPF/título/nascimento de OUTRA pessoa: não liga a ninguém).
    Uma decisão por linha; valor_a de isolar_candidatura = ano|SG_UE|cd_cargo|SQ_CANDIDATO."""
    if not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        saida = []
        for r in csv.DictReader(f, delimiter=";"):
            tipo = r["tipo"].strip()
            if tipo == "isolar_candidatura":          # valor_a = ano|SG_UE|cd_cargo|SQ_CANDIDATO
                saida.append({"tipo": tipo, "a": r["valor_a"].strip(), "b": None, "nota": r.get("nota", "")})
            else:
                saida.append({"tipo": tipo, "a": pad(r["valor_a"], 12), "b": pad(r["valor_b"], 12),
                              "nota": r.get("nota", "")})
        return saida


class _Grupos:
    """Union-find que lembra os CPFs e títulos de cada grupo e respeita proibições."""

    def __init__(self, df: pd.DataFrame, proibidos: set[frozenset]):
        n = len(df)
        self.pai = list(range(n))
        self.cpfs = [({c} if isinstance(c, str) else set()) for c in df["cpf"]]
        self.tits = [({t} if isinstance(t, str) else set()) for t in df["titulo"]]
        self.proibidos = proibidos
        self.bloqueios = Counter()
        self.recusadas: list[tuple[int, int]] = []     # pares recusados por conflito forte (vão à revisão)

    def raiz(self, x: int) -> int:
        while self.pai[x] != x:
            self.pai[x] = self.pai[self.pai[x]]
            x = self.pai[x]
        return x

    def _proibido(self, ra: int, rb: int) -> bool:
        return any(frozenset((a, b)) in self.proibidos for a in self.tits[ra] for b in self.tits[rb])

    def _conflito_forte(self, ra: int, rb: int) -> bool:
        """CPFs e títulos ambos presentes e totalmente diferentes: provavelmente pessoas distintas."""
        return (bool(self.cpfs[ra] and self.cpfs[rb] and not self.cpfs[ra] & self.cpfs[rb])
                and bool(self.tits[ra] and self.tits[rb] and not self.tits[ra] & self.tits[rb]))

    def unir(self, x: int, y: int, regra: str, forcar: bool = False) -> bool:
        ra, rb = self.raiz(x), self.raiz(y)
        if ra == rb:
            return False
        if not forcar and self._proibido(ra, rb):
            self.bloqueios["decisão manual"] += 1
            return False
        # nome+nascimento é a regra mais fraca: não passa por cima de CPF e título que divergem
        if regra == "nome+nascimento" and self._conflito_forte(ra, rb):
            self.bloqueios["nome+nascimento com CPF e título divergentes"] += 1
            self.recusadas.append((x, y))
            return False
        self.pai[rb] = ra
        self.cpfs[ra] |= self.cpfs[rb]
        self.tits[ra] |= self.tits[rb]
        return True


def resolver(df: pd.DataFrame, decisoes: list[dict] | None = None) -> tuple[pd.DataFrame, dict]:
    """Acrescenta a coluna `pessoa` (número do grupo) e devolve também estatísticas por regra."""
    df = df.reset_index(drop=True)
    decisoes = decisoes or []
    df["decidida"] = False
    chave = df["ano"].astype(str) + "|" + df["SG_UE"].astype(str) + "|" + df["cd_cargo"].astype(str) + "|" + df["SQ_CANDIDATO"].astype(str)
    for d in decisoes:
        if d["tipo"] == "isolar_candidatura":
            m = chave == d["a"]
            if not m.any():
                print(f"AVISO: decisão isolar_candidatura sem correspondência: {d['a']}")
            df.loc[m, ["cpf", "titulo", "nasc"]] = None     # identificadores desse registro não são confiáveis
            df.loc[m, "protegida"] = True                   # protegida = nunca se liga por regra
            df.loc[m, "decidida"] = True
    proibidos = {frozenset((d["a"], d["b"])) for d in decisoes if d["tipo"] == "separar_titulo" and d["a"] and d["b"]}
    g = _Grupos(df, proibidos)
    por_regra = Counter()

    # decisões "juntar": liga as linhas que têm cada um dos títulos
    for d in decisoes:
        if d["tipo"] == "juntar_titulo" and d["a"] and d["b"]:
            ia = df.index[df["titulo"] == d["a"]].tolist()
            ib = df.index[df["titulo"] == d["b"]].tolist()
            if ia and ib:
                for i in ia[1:] + ib:
                    por_regra["decisão manual (juntar)"] += g.unir(ia[0], i, "manual", forcar=True)

    aptas = ~df["protegida"]                         # dado protegido nunca liga por regra
    for rotulo, colunas in REGRAS:
        sub = df[aptas].dropna(subset=colunas)
        for idx in sub.groupby(colunas).groups.values():
            idx = list(idx)
            for j in idx[1:]:
                por_regra[rotulo] += g.unir(idx[0], j, rotulo)
    df["pessoa"] = [g.raiz(i) for i in range(len(df))]
    pares = {tuple(sorted((int(df.at[x, "pessoa"]), int(df.at[y, "pessoa"])))) for x, y in g.recusadas}
    pares = {p for p in pares if p[0] != p[1]}
    return df, {"fusoes_por_regra": dict(por_regra), "bloqueios": dict(g.bloqueios), "pares_recusados": pares}


def _variacao_total_de_nome(nomes: list[str]) -> bool:
    """O nome muda por completo: o 1º e o último nome divergem entre alguma variante e a primeira."""
    def pontas(n): w = n.split(); return (w[0], w[-1]) if w else ("", "")
    base = pontas(nomes[0])
    return any(pontas(n)[0] != base[0] and pontas(n)[1] != base[1] for n in nomes[1:])


def resumir_pessoas(df: pd.DataFrame, pares_recusados: set | None = None,
                    decididos: set | None = None) -> pd.DataFrame:
    """Uma linha por pessoa: nível de evidência (A–E), sinais de conflito e motivos de revisão."""
    em_par = {p for par in (pares_recusados or ()) for p in par}
    decididos = decididos or set()                    # títulos já resolvidos por decisão manual
    linhas = []
    for pessoa, g in df.groupby("pessoa"):
        tits, cpfs = g["titulo"].dropna().unique(), g["cpf"].dropna().unique()
        nascs, nomes = g["nasc"].dropna().unique(), list(g["nome_norm"].dropna().unique())
        n = len(g)
        if n == 1:
            nivel = "-"
        elif len(tits) == 1 and len(nomes) == 1 and len(nascs) <= 1:
            nivel = "A"
        elif len(tits) == 1 and len(nascs) <= 1:
            nivel = "B"
        elif len(tits) == 1:
            nivel = "C"
        elif len(tits) == 0:
            nivel = "D"
        else:
            nivel = "E"
        motivos = []
        if len(cpfs) > 1 and len(tits) > 1:
            motivos.append("conflito forte: mais de um CPF e mais de um título")
        if len(nomes) > 1 and _variacao_total_de_nome(nomes):
            motivos.append("nome muda por completo")
        if pessoa in em_par:
            motivos.append("possível mesma pessoa de outro grupo: nome e nascimento iguais, CPF e título divergem")
        if n == 1 and bool(g["protegida"].iloc[0]):
            motivos.append("dado protegido (sem título, CPF nem nascimento)")
        if decididos & set(tits) or bool(g["decidida"].any()):
            motivos = []                              # já decidido manualmente: não volta à fila
        linhas.append({
            "pessoa": pessoa, "candidaturas": n, "nivel": nivel,
            "n_cpfs": len(cpfs), "n_titulos": len(tits), "n_nascimentos": len(nascs), "n_nomes": len(nomes),
            "anos": ",".join(str(a) for a in sorted(set(g["ano"]))),
            "nome": g.sort_values("ano")["NM_CANDIDATO"].iloc[-1],
            "motivos": "; ".join(motivos),
        })
    return pd.DataFrame(linhas)
