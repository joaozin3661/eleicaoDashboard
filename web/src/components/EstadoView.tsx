"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import Cartoes from "./Cartoes";
import GraficoCandidatos from "./GraficoCandidatos";
import type { Bolha } from "./MapaEstado";
import SeletorCargo from "./SeletorCargo";
import Tabela from "./Tabela";
import { corPartido, fmt, fmtPP, margemPP, validos } from "@/lib/formato";
import type { Candidato, Cargo, Estado } from "@/lib/tipos";

// Leaflet precisa do navegador (window), então o mapa só é carregado no cliente.
const MapaEstado = dynamic(() => import("./MapaEstado"), {
  ssr: false,
  loading: () => <div className="h-[520px] w-full animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-900" />,
});

type LinhaCandidato = { nome: string; completo: string; partido: string; numero: number; votos: number; pct: number };
type LinhaMunicipio = {
  cd: number;
  nome: string;
  aptos: number;
  comparecimento: number;
  vencedor: string;
  partido: string;
  pctVencedor: number;
  margem: number;
};

const colunasCandidatos: ColumnDef<LinhaCandidato>[] = [
  {
    header: "Candidato",
    accessorKey: "nome",
    cell: ({ row }) => (
      <div>
        <div className="font-medium">{row.original.nome}</div>
        {row.original.completo && row.original.completo !== row.original.nome && (
          <div className="text-xs text-zinc-500">{row.original.completo}</div>
        )}
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
  { header: "Margem", accessorKey: "margem", cell: ({ getValue }) => fmtPP(getValue<number>()) },
];

type LegendaMapa =
  | { tipo: "partidos"; itens: [string, number][] }
  | { tipo: "faixa"; de: string; ate: string; cor: string };

type Modo = "vencedor" | "candidato" | "abstencao";
const MODOS: { id: Modo; rotulo: string }[] = [
  { id: "vencedor", rotulo: "Vencedor" },
  { id: "candidato", rotulo: "% de um candidato" },
  { id: "abstencao", rotulo: "Abstenção" },
];

const pctTxt = (fracao: number) => (100 * fracao).toFixed(1).replace(".", ",") + "%";

type Props = {
  cargos: Cargo[];
  estados: Record<number, Estado>;
  candidatos: Record<string, Candidato>;
  posicoes: Record<number, { lat: number; lon: number }>;
};

/** Lê ?cargo=&q= da URL (links da busca) e recria a tela quando mudam. */
export default function EstadoView(props: Props) {
  const params = useSearchParams();
  const cargo = Number(params.get("cargo"));
  return (
    <EstadoInterno
      key={params.toString()}
      {...props}
      cargoInicial={props.cargos.some((c) => c.cd === cargo) ? cargo : props.cargos[0].cd}
      buscaInicial={params.get("q") ?? ""}
    />
  );
}

/** Calcula as bolhas (posição, tamanho, cor) e a legenda do mapa para o modo escolhido. */
function calcularMapa(
  estado: Estado,
  modo: Modo,
  sqAtivo: string | undefined,
  candidatos: Record<string, Candidato>,
  posicoes: Props["posicoes"],
): { bolhas: Bolha[]; legenda: LegendaMapa } {
  const base = estado.municipios.filter((m) => posicoes[m.cd]);
  let intens: (m: (typeof base)[number]) => number = () => 1;
  let cor: (m: (typeof base)[number]) => string = () => "#6b7280";
  let detalhe: (m: (typeof base)[number]) => string = () => "";
  let legenda: LegendaMapa = { tipo: "partidos", itens: [] };

  if (modo === "vencedor") {
    cor = (m) => corPartido(candidatos[m.top[0]?.[0]]?.p ?? "?");
    detalhe = (m) => {
      const c = candidatos[m.top[0]?.[0]];
      return `${c?.n ?? "–"} (${c?.p ?? "–"}) · ${((100 * (m.top[0]?.[1] ?? 0)) / (validos(m.totais) || 1)).toFixed(1).replace(".", ",")}%`;
    };
    const cont = new Map<string, number>();
    base.forEach((m) => {
      const p = candidatos[m.top[0]?.[0]]?.p ?? "?";
      cont.set(p, (cont.get(p) ?? 0) + 1);
    });
    legenda = { tipo: "partidos", itens: [...cont.entries()].sort((a, b) => b[1] - a[1]) };
  } else if (modo === "candidato" && sqAtivo) {
    const c = candidatos[sqAtivo];
    const pcts = base.map((m) => {
      const votos = m.principais.find(([sq]) => sq === sqAtivo)?.[1] ?? 0;
      return votos / (validos(m.totais) || 1);
    });
    const [lo, hi] = [Math.min(...pcts), Math.max(...pcts)];
    const por = new Map(base.map((m, i) => [m.cd, pcts[i]]));
    cor = () => corPartido(c?.p ?? "?");
    intens = (m) => (hi > lo ? ((por.get(m.cd) ?? 0) - lo) / (hi - lo) : 1);
    detalhe = (m) => `${c?.n}: ${(100 * (por.get(m.cd) ?? 0)).toFixed(1).replace(".", ",")}% dos válidos`;
    legenda = { tipo: "faixa", de: pctTxt(lo), ate: pctTxt(hi), cor: corPartido(c?.p ?? "?") };
  } else {
    const taxa = (m: (typeof base)[number]) => 1 - m.totais.comparecimento / (m.totais.aptos || 1);
    const ts = base.map(taxa);
    const [lo, hi] = [Math.min(...ts), Math.max(...ts)];
    cor = () => "#b45309";
    intens = (m) => (hi > lo ? (taxa(m) - lo) / (hi - lo) : 1);
    detalhe = (m) => `Abstenção: ${(100 * taxa(m)).toFixed(1).replace(".", ",")}%`;
    legenda = { tipo: "faixa", de: pctTxt(lo), ate: pctTxt(hi), cor: "#b45309" };
  }
  const bolhas: Bolha[] = base.map((m) => ({
    cd: m.cd,
    nome: m.nome,
    lat: posicoes[m.cd].lat,
    lon: posicoes[m.cd].lon,
    aptos: m.totais.aptos,
    cor: cor(m),
    intensidade: intens(m),
    detalhe: detalhe(m),
  }));
  return { bolhas, legenda };
}

function EstadoInterno({
  cargos,
  estados,
  candidatos,
  posicoes,
  cargoInicial,
  buscaInicial,
}: Props & { cargoInicial: number; buscaInicial: string }) {
  const [cargo, setCargo] = useState(cargoInicial);
  const [modo, setModo] = useState<Modo>("vencedor");
  const [sqEscolhido, setSqEscolhido] = useState<string | null>(null);
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
        const vm = validos(m.totais);
        return {
          cd: m.cd,
          nome: m.nome,
          aptos: m.totais.aptos,
          comparecimento: m.totais.comparecimento,
          vencedor: c?.n ?? "–",
          partido: c?.p ?? "–",
          pctVencedor: vm ? (100 * votos) / vm : 0,
          margem: margemPP(m.top.map(([, n]) => n), vm),
        };
      }),
    [estado, candidatos],
  );

  // candidatos que podem ser escolhidos no modo "% de um candidato" (os mais votados do estado)
  const principais = estado.candidatos.slice(0, estado.municipios[0]?.principais.length ?? 0);
  const sqAtivo = sqEscolhido && principais.some(([sq]) => sq === sqEscolhido) ? sqEscolhido : principais[0]?.[0];

  const { bolhas, legenda } = calcularMapa(estado, modo, sqAtivo, candidatos, posicoes);

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

      <section className="space-y-3" aria-label="Mapa dos municípios">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Mapa dos municípios</h2>
          <div role="tablist" aria-label="O que o mapa mostra" className="flex gap-2">
            {MODOS.map((m) => (
              <button
                key={m.id}
                role="tab"
                aria-selected={modo === m.id}
                onClick={() => setModo(m.id)}
                className={
                  "rounded-full border px-3 py-1 text-sm " +
                  (modo === m.id
                    ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                    : "border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800")
                }
              >
                {m.rotulo}
              </button>
            ))}
          </div>
        </div>
        {modo === "candidato" && (
          <label className="flex items-center gap-2 text-sm">
            Candidato:
            <select
              value={sqAtivo}
              onChange={(e) => setSqEscolhido(e.target.value)}
              className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
            >
              {principais.map(([sq]) => (
                <option key={sq} value={sq} className="text-black">
                  {candidatos[sq]?.n} ({candidatos[sq]?.p})
                </option>
              ))}
            </select>
          </label>
        )}
        <MapaEstado bolhas={bolhas} />
        <Legenda legenda={legenda} />
        <p className="text-xs text-zinc-500">
          Cada bolha é um município, posicionada no centro dos seus locais de votação; o tamanho mostra os eleitores aptos.
          Clique para abrir o município. Sem contorno dos municípios por enquanto.
        </p>
      </section>

      <section className="space-y-3" aria-label="Todos os candidatos">
        <h2 className="text-lg font-semibold">
          Todos os candidatos <span className="text-sm font-normal text-zinc-500">({linhasCandidatos.length} com votos)</span>
        </h2>
        <Tabela
          dados={linhasCandidatos}
          colunas={colunasCandidatos}
          placeholderBusca="Buscar candidato ou partido…"
          filtroInicial={buscaInicial}
        />
      </section>

      <section className="space-y-3" aria-label="Municípios">
        <h2 className="text-lg font-semibold">Por município</h2>
        <p className="text-sm text-zinc-500">
          Margem = diferença, em pontos percentuais, entre o 1º e o 2º colocado. Clique no município para ver o mapa e os
          resultados por local de votação.
        </p>
        <Tabela dados={linhasMunicipios} colunas={colunasMunicipios} placeholderBusca="Buscar município…" porPagina={20} />
      </section>
    </div>
  );
}

function Legenda({ legenda }: { legenda: LegendaMapa }) {
  if (legenda.tipo === "faixa") {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <span>{legenda.de}</span>
        <span className="h-3 w-40 rounded" style={{ background: `linear-gradient(to right, ${legenda.cor}22, ${legenda.cor})` }} />
        <span>{legenda.ate}</span>
      </div>
    );
  }
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
      {legenda.itens.slice(0, 8).map(([sigla, n]) => (
        <li key={sigla} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: corPartido(sigla) }} />
          {sigla} <span className="text-zinc-500">({n} {n === 1 ? "município" : "municípios"})</span>
        </li>
      ))}
    </ul>
  );
}
