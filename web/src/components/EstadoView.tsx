"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import Cartoes from "./Cartoes";
import GraficoCandidatos from "./GraficoCandidatos";
import SeletorCargo from "./SeletorCargo";
import Tabela from "./Tabela";
import { corPartido, fmt, validos } from "@/lib/formato";
import type { Candidato, Cargo, Estado } from "@/lib/tipos";

type LinhaCandidato = { nome: string; completo: string; partido: string; numero: number; votos: number; pct: number };
type LinhaMunicipio = {
  cd: number;
  nome: string;
  aptos: number;
  comparecimento: number;
  vencedor: string;
  partido: string;
  pctVencedor: number;
};

const colunasCandidatos: ColumnDef<LinhaCandidato>[] = [
  {
    header: "Candidato",
    accessorKey: "nome",
    cell: ({ row }) => (
      <div>
        <div className="font-medium">{row.original.nome}</div>
        <div className="text-xs text-zinc-500">{row.original.completo}</div>
      </div>
    ),
  },
  {
    header: "Partido",
    accessorKey: "partido",
    cell: ({ row }) => (
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: corPartido(row.original.partido) }} />
        {row.original.partido}
      </span>
    ),
  },
  { header: "Nº", accessorKey: "numero" },
  { header: "Votos", accessorKey: "votos", cell: ({ getValue }) => fmt(getValue<number>()) },
  { header: "% válidos", accessorKey: "pct", cell: ({ getValue }) => getValue<number>().toFixed(1).replace(".", ",") + "%" },
];

const colunasMunicipios: ColumnDef<LinhaMunicipio>[] = [
  {
    header: "Município",
    accessorKey: "nome",
    cell: ({ row }) => (
      <Link href={`/municipio/${row.original.cd}/`} className="font-medium text-blue-700 hover:underline dark:text-blue-400">
        {row.original.nome}
      </Link>
    ),
  },
  { header: "Aptos", accessorKey: "aptos", cell: ({ getValue }) => fmt(getValue<number>()) },
  {
    header: "Comparec.",
    accessorFn: (l) => (l.aptos ? l.comparecimento / l.aptos : 0),
    cell: ({ getValue }) => (100 * getValue<number>()).toFixed(1).replace(".", ",") + "%",
  },
  {
    header: "Mais votado",
    accessorKey: "vencedor",
    cell: ({ row }) => (
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: corPartido(row.original.partido) }} />
        {row.original.vencedor} <span className="text-zinc-500">({row.original.partido})</span>
      </span>
    ),
  },
  { header: "% dele", accessorKey: "pctVencedor", cell: ({ getValue }) => getValue<number>().toFixed(1).replace(".", ",") + "%" },
];

export default function EstadoView({
  cargos,
  estados,
  candidatos,
}: {
  cargos: Cargo[];
  estados: Record<number, Estado>;
  candidatos: Record<string, Candidato>;
}) {
  const [cargo, setCargo] = useState(cargos[0].cd);
  const estado = estados[cargo];
  const v = validos(estado.totais);

  const linhasCandidatos = useMemo<LinhaCandidato[]>(
    () =>
      estado.candidatos.map(([sq, votos]) => {
        const c = candidatos[sq];
        return { nome: c?.n ?? sq, completo: c?.nc ?? "", partido: c?.p ?? "?", numero: c?.nr ?? 0, votos, pct: (100 * votos) / v };
      }),
    [estado, candidatos, v],
  );

  const linhasMunicipios = useMemo<LinhaMunicipio[]>(
    () =>
      estado.municipios.map((m) => {
        const [sq, votos] = m.top[0] ?? ["", 0];
        const c = candidatos[sq];
        return {
          cd: m.cd,
          nome: m.nome,
          aptos: m.totais.aptos,
          comparecimento: m.totais.comparecimento,
          vencedor: c?.n ?? "–",
          partido: c?.p ?? "–",
          pctVencedor: validos(m.totais) ? (100 * votos) / validos(m.totais) : 0,
        };
      }),
    [estado, candidatos],
  );

  return (
    <div className="space-y-8">
      <SeletorCargo cargos={cargos} atual={cargo} onChange={setCargo} />

      <section className="space-y-3" aria-label="Resumo do estado">
        <h2 className="text-lg font-semibold">Piauí · {estado.cargo.nome}</h2>
        <Cartoes totais={estado.totais} />
        {cargo === 5 && (
          <p className="text-xs text-zinc-500">
            Para Senador cada eleitor tem dois votos em 2026, por isso a soma de votos é cerca do dobro do comparecimento.
          </p>
        )}
      </section>

      <section className="space-y-3" aria-label="Candidatos mais votados">
        <h2 className="text-lg font-semibold">Mais votados</h2>
        <GraficoCandidatos
          dados={linhasCandidatos.slice(0, 10).map((l) => ({ nome: l.nome, partido: l.partido, votos: l.votos, pct: l.pct }))}
        />
      </section>

      <section className="space-y-3" aria-label="Todos os candidatos">
        <h2 className="text-lg font-semibold">
          Todos os candidatos <span className="text-sm font-normal text-zinc-500">({linhasCandidatos.length} com votos)</span>
        </h2>
        <Tabela dados={linhasCandidatos} colunas={colunasCandidatos} placeholderBusca="Buscar candidato ou partido…" />
      </section>

      <section className="space-y-3" aria-label="Municípios">
        <h2 className="text-lg font-semibold">Por município</h2>
        <p className="text-sm text-zinc-500">
          Clique no município para ver o mapa e os resultados por zona e local de votação.
        </p>
        <Tabela dados={linhasMunicipios} colunas={colunasMunicipios} placeholderBusca="Buscar município…" porPagina={20} />
      </section>
    </div>
  );
}
