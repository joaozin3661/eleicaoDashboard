"""
Conexão com o PostgreSQL via pg8000 (Python puro, sem DLL).

Por que não psycopg2: com o Smart App Control do Windows ligado, a DLL do
psycopg2/psycopg é bloqueada ("política de Controle de Aplicativo"). O pg8000
é só Python, então carrega normalmente.

Uso:
    import db
    conn = db.connect(**DB)            # DB = dict(host, port, dbname, user, password)
    db.execute_values(cur, "INSERT INTO t (a, b) VALUES %s", linhas)
"""

import os

import pg8000.dbapi


if not hasattr(pg8000.dbapi.Cursor, "__enter__"):
    pg8000.dbapi.Cursor.__enter__ = lambda self: self
    pg8000.dbapi.Cursor.__exit__ = lambda self, *exc: self.close()


_MAX_PARAMS = 60_000


def _ler_env(caminho):
    if not os.path.exists(caminho):
        return
    for linha in open(caminho, encoding="utf-8"):
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def config():
    #Variáveis: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD.

    _ler_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    if not os.environ.get("PGPASSWORD"):
        raise SystemExit("Defina PGPASSWORD (copie .env.example para .env e preencha).")
    return dict(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "joaoeleicao"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ["PGPASSWORD"],
    )


def connect(host, port, dbname, user, password):
    return pg8000.dbapi.connect(host=host, port=port, database=dbname,
                                user=user, password=password)


def execute_values(cur, sql, linhas, page_size=2000):
    """Insere várias linhas de uma vez: troca `VALUES %s` por (%s,..),(%s,..).

    Mesma assinatura que psycopg2.extras.execute_values, para as chamadas existentes.
    """
    linhas = list(linhas)
    if not linhas:
        return
    ncols = len(linhas[0])
    por_lote = max(1, min(page_size, _MAX_PARAMS // ncols))
    marcador = "(" + ",".join(["%s"] * ncols) + ")"
    for i in range(0, len(linhas), por_lote):
        lote = linhas[i:i + por_lote]
        consulta = sql.replace("%s", ",".join([marcador] * len(lote)), 1)
        cur.execute(consulta, [v for linha in lote for v in linha])
