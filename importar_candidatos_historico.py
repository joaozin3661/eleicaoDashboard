"""
Importação do histórico de candidatos (todos os anos) — MODO DE TESTE.

Uso:
    python importar_candidatos_historico.py              # lê candidato*/consulta_cand_*.csv
    python importar_candidatos_historico.py --saida pasta
    python importar_candidatos_historico.py --gravar     # grava pessoas e candidaturas no banco

Lê e limpa os arquivos, resolve a identidade das pessoas entre os anos e escreve um relatório em
relatorio_identidade/ (resumo.txt e CSVs de revisão). NÃO grava nada no banco: serve para
conferir os dados e as regras antes de importar.

Os CSVs do relatório contêm CPF e título de eleitor: ficam só no seu computador (o .gitignore
já ignora *.csv e a pasta relatorio_identidade/).
"""

import argparse
import io
import os
import sys

import pandas as pd

from candidatos_tse import carregar
from identidade import ler_decisoes, resolver, resumir_pessoas

sys.stdout.reconfigure(encoding="utf-8")

CHAVE = ["ano", "dt_eleicao", "turno", "SG_UE", "cd_cargo", "SQ_CANDIDATO"]


def main(raiz: str, saida: str, gravar: bool = False) -> None:
    saida_txt = io.StringIO()

    def p(*partes):
        texto = " ".join(str(x) for x in partes)
        print(texto)
        saida_txt.write(texto + "\n")

    a, st = carregar(raiz, completo=gravar)
    a["dt_eleicao"] = a["DT_ELEICAO"]
    p("=" * 78)
    p("IMPORTAÇÃO DO HISTÓRICO DE CANDIDATOS — " + ("GRAVANDO NO BANCO" if gravar else "MODO DE TESTE (nada é gravado no banco)"))
    p("=" * 78)

    p(f"\n1) ARQUIVOS LIDOS: {len(st['arquivos'])} | candidaturas: {len(a):,}")
    for nome, n in st["arquivos"]:
        p(f"   {nome:34} {n:>7,}")

    p("\n2) CHAVE DA CANDIDATURA (ano + data + turno + unidade + cargo + sq_candidato)")
    dup = int(a.duplicated(CHAVE).sum())
    p(f"   duplicadas: {dup}  ->  {'OK, a chave é única' if dup == 0 else 'ATENÇÃO: há chaves repetidas'}")

    p("\n3) CANDIDATURAS POR ANO (suplementares entre parênteses)")
    for ano, g in a.groupby("ano"):
        sup = int((g["tp_eleicao"] == "suplementar").sum())
        p(f"   {ano}: {len(g):>6,}" + (f"  ({sup} suplementares)" if sup else ""))

    p("\n4) CPF POR ANO/ARQUIVO (ok | recuperado = zero à esquerda reposto | oculto pelo TSE | inválido)")
    for (ano, uf), c in sorted(st["cpf"].items()):
        p(f"   {ano} {uf}: ok={c.get('ok', 0):>5} recuperado={c.get('recuperado', 0):>4} "
          f"oculto={c.get('oculto', 0):>5} inválido={c.get('invalido', 0):>3}")
    inval = {k: v for k, v in st["datas_invalidas"].items() if v}
    p(f"   datas de nascimento descartadas (impossíveis): {sum(inval.values())}  {inval or ''}")
    prot = {k: v for k, v in st["protegidas"].items() if v}
    p(f"   candidaturas com dado protegido: {sum(prot.values())}  {prot or ''}")

    p("\n5) SITUAÇÃO FINAL: mapeamento do valor do TSE para a categoria usada")
    mapa = (a.groupby(["DS_SIT_TOT_TURNO", "situacao"], dropna=False).size().reset_index(name="linhas")
            .sort_values(["situacao", "linhas"], ascending=[True, False]))
    for _, r in mapa.iterrows():
        p(f"   {str(r['DS_SIT_TOT_TURNO'])[:48]:50} -> {r['situacao']:14} {r['linhas']:>6,}")
    p("   categorias:", a["situacao"].value_counts().to_dict())
    p(f"   vices que herdaram o resultado do titular da chapa: {int(a['situacao_herdada'].sum()):,}")
    sr = a[a["situacao"] == "sem_resultado"]
    vices = sr["DS_CARGO"].str.contains("VICE", na=False)
    p(f"   sem resultado: {len(sr):,} (vices: {int(vices.sum()):,}; outros cargos: {int((~vices).sum()):,})")
    p("   sem resultado, fora vices, por cargo:", sr[~vices]["DS_CARGO"].value_counts().head(6).to_dict())

    decisoes = ler_decisoes(os.path.join(raiz, "decisoes_identidade.csv"))
    p(f"\n6) IDENTIDADE (decisões manuais carregadas: {len(decisoes)})")
    a, info = resolver(a, decisoes)
    decididos = {t for d in decisoes for t in (d["a"], d["b"]) if t}
    pessoas = resumir_pessoas(a, info["pares_recusados"], decididos)
    p(f"   pessoas distintas: {len(pessoas):,}  (de {len(a):,} candidaturas)")
    p("   ligações por regra:", info["fusoes_por_regra"])
    p("   ligações recusadas:", info["bloqueios"] or "nenhuma")
    p("   pessoas por nível de evidência (A=certeza ... E=mais de um título):")
    for nivel, n in pessoas["nivel"].value_counts().sort_index().items():
        rot = {"-": "uma só candidatura", "A": "título único + mesmo nome + mesmo nascimento",
               "B": "título único + mesmo nascimento", "C": "título único, nome/nascimento variam",
               "D": "sem título", "E": "mais de um título"}[nivel]
        p(f"      {nivel}: {n:>6,}  {rot}")
    p(f"   pessoas com mais de 1 CPF (informativo, não bloqueia): {(pessoas.n_cpfs > 1).sum()}")
    p(f"   pessoas com datas de nascimento diferentes entre anos (digitação; usa-se a mais frequente): "
      f"{(pessoas.n_nascimentos > 1).sum()}")

    p("\n7) PESSOAS QUE JÁ TINHAM HISTÓRICO, POR ANO (ligação com eleições anteriores)")
    primeira = a.groupby("pessoa")["ano"].min()
    for ano in sorted(a["ano"].unique()):
        ps = set(a.loc[a["ano"] == ano, "pessoa"])
        voltam = sum(1 for x in ps if primeira[x] < ano)
        p(f"   {ano}: {len(ps):>6,} pessoas | já apareciam antes: {voltam:>6,} ({100 * voltam / len(ps):4.1f}%)")

    fila = pessoas[pessoas["motivos"] != ""].copy()
    p(f"\n8) FILA DE REVISÃO: {len(fila)} pessoas")
    for motivo, n in fila["motivos"].str.split("; ").explode().value_counts().items():
        p(f"   {n:>4}  {motivo}")

    os.makedirs(saida, exist_ok=True)
    detalhe = a[a["pessoa"].isin(fila["pessoa"])][
        ["pessoa", "ano", "tp_eleicao", "SG_UE", "DS_CARGO", "NM_CANDIDATO", "cpf", "titulo", "nasc", "arquivo_uf"]
    ].sort_values(["pessoa", "ano"]).merge(fila[["pessoa", "nivel", "motivos"]], on="pessoa")
    detalhe.to_csv(os.path.join(saida, "fila_revisao.csv"), sep=";", index=False, encoding="utf-8-sig")
    multi = pessoas[pessoas["n_cpfs"] > 1]["pessoa"]
    a[a["pessoa"].isin(multi)][["pessoa", "ano", "NM_CANDIDATO", "cpf", "titulo", "nasc"]].sort_values(
        ["pessoa", "ano"]).to_csv(os.path.join(saida, "conflitos_cpf.csv"), sep=";", index=False, encoding="utf-8-sig")
    mapa.to_csv(os.path.join(saida, "mapa_situacao.csv"), sep=";", index=False, encoding="utf-8-sig")
    p(f"\nArquivos em {saida}/: fila_revisao.csv, conflitos_cpf.csv, mapa_situacao.csv, resumo.txt")
    if gravar:
        import db
        from gravar_candidatos import gravar as gravar_no_banco
        p("\n9) GRAVAÇÃO NO BANCO (numa transação: se algo falhar, nada muda)")
        conn = db.connect(**db.config())
        res = gravar_no_banco(conn, a, pessoas)
        conn.close()
        for k, v in res.items():
            p(f"   {k}: {v}")
    else:
        p("Nada foi gravado no banco. Revise o relatório antes de importar (use --gravar).")
    with open(os.path.join(saida, "resumo.txt"), "w", encoding="utf-8") as f:
        f.write(saida_txt.getvalue())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--saida", default=None)
    ap.add_argument("--gravar", action="store_true", help="grava no banco (por padrão só gera o relatório)")
    args = ap.parse_args()
    main(args.raiz, args.saida or os.path.join(args.raiz, "relatorio_identidade"), args.gravar)
