import os
import csv

# Pastas onde estão os CSVs - ajuste se necessário
PASTAS = [
    "bweb_1t_PI_051020261403",
    "candidatoBR2026",
    "candidatoPI2026",
    "perfil_eleitor_secao_2026_PI",
]

# Encoding do TSE
ENCODING = "latin-1"
SEPARADOR = ";"


def inspecionar_pasta(pasta):
    print(f"\n{'='*60}")
    print(f"PASTA: {pasta}")
    print(f"{'='*60}")

    if not os.path.exists(pasta):
        print(f"  [ERRO] Pasta não encontrada: {pasta}")
        return

    arquivos = [f for f in os.listdir(pasta) if f.lower().endswith(".csv")]

    if not arquivos:
        print("  [AVISO] Nenhum arquivo CSV encontrado nesta pasta.")
        return

    for arquivo in sorted(arquivos):
        caminho = os.path.join(pasta, arquivo)
        tamanho_mb = os.path.getsize(caminho) / (1024 * 1024)
        print(f"\n  Arquivo: {arquivo} ({tamanho_mb:.1f} MB)")
        print(f"  {'-'*50}")

        try:
            with open(caminho, encoding=ENCODING, errors="replace") as f:
                reader = csv.reader(f, delimiter=SEPARADOR)
                cabecalho = next(reader, None)

                if cabecalho:
                    print(f"  Colunas ({len(cabecalho)}):")
                    for i, col in enumerate(cabecalho):
                        print(f"    [{i:02d}] {col.strip()}")

                print(f"\n  Primeiras 5 linhas:")
                for i, linha in enumerate(reader):
                    if i >= 5:
                        break
                    # Mostra só os primeiros 8 campos para não poluir
                    campos = [c.strip()[:30] for c in linha[:8]]
                    print(f"    {i+1}: {' | '.join(campos)}")

        except Exception as e:
            print(f"  [ERRO] {e}")


if __name__ == "__main__":
    print("INSPEÇÃO DOS ARQUIVOS DO TSE")
    print(f"Diretório atual: {os.getcwd()}")

    for pasta in PASTAS:
        inspecionar_pasta(pasta)

    print(f"\n{'='*60}")
    print("FIM DA INSPEÇÃO")