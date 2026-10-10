"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import Cartoes from "./Cartoes";
import GraficoCandidatos from "./GraficoCandidatos";
import type { PontoLocal } from "./MapaLocais";
import SeletorCargo from "./SeletorCargo";
import Tabela from "./Tabela";
import { APROXIMADA, PRECISAO, corPartido, fmt, fmtPP, margemPP, validos } from "@/lib/formato";
import type { Candidato, Cargo, Municipio } from "@/lib/tipos";

// Leaflet precisa do navegador (window), então o mapa só é carregado no cliente.
const MapaLocais = dynamic(() => import("./MapaLocais"), {
  ssr: false,
  loading: () => <div className="h-[460px] w-full animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-900" />,
});

type LinhaLocal = {
  id: string;
  nome: string;
  bairro: string;
  zona: number;
  aptos: number;
  comparecimento: number;
  votos: number;
  vencedor: string;
  partido: string;
  pct: number;
  margem: number;
  precisao: string;
};

const colunas: ColumnDef<LinhaLocal>[] = [
  {
    header: "Local de votação",
    accessorKey: "nome",
    cell: ({ row }) => (
      <div>
        <div className="font-medium">{row.original.nome}</div>
        {APROXIMADA.has(row.original.precisao) && (
          <div className="text-xs text-amber-700 dark:text-amber-400">posição aproximada no mapa</div>
        )}
      </div>
    ),
  },
  { header: "Bairro", accessorKey: "bairro" },
  { header: "Zona", accessorKey: "zona" },
  { header: "Aptos", accessorKey: "aptos", cell: ({ getValue }) => fmt(getValue<number>()) },
  {
    header: "Comparec.",
    accessorFn: (l) => (l.aptos ? l.comparecimento / l.aptos : 0),
    cell: ({ getValue }) => (100 * getValue<number>()).toFixed(1).replace(".", ",") + "%",
  },
  { header: "Votos válidos", accessorKey: "votos", cell: ({ getValue }) => fmt(getValue<number>()) },
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
  { header: "% dele", accessorKey: "pct", cell: ({ getValue }) => getValue<number>().toFixed(1).replace(".", ",") + "%" },
  { header: "Margem", accessorKey: "margem", cell: ({ getValue }) => fmtPP(getValue<number>()) },
];

type Props = { municipio: Municipio; cargos: Cargo[]; candidatos: Record<string, Candidato> };

/** Lê ?q= da URL (link da busca por escola) e recria a tela quando muda. */
export default function MunicipioView(props: Props) {
  const params = useSearchParams();
  return <MunicipioInterno key={params.toString()} {...props} buscaInicial={params.get("q") ?? ""} />;
}

function MunicipioInterno({ municipio, cargos, candidatos, buscaInicial }: Props & { buscaInicial: string }) {
  const disponiveis = cargos.filter((c) => municipio.cargos[String(c.cd)]);
  const [cargo, setCargo] = useState(disponiveis[0].cd);
  const dados = municipio.cargos[String(cargo)];
  const v = validos(dados.totais);

  const linhas = useMemo(() => {
    return dados.por_local.map(([idx, aptos, comparecimento, brancos, nulos, legenda, votos]) => {
      void brancos;
      void nulos;
      const local = municipio.locais[idx];
      const entradas = Object.entries(votos);
      const nominais = entradas.reduce((s, [, n]) => s + n, 0);
      const validosLocal = nominais + legenda;
      const [sqVenc, votosVenc] = entradas.reduce<[string, number]>((m, e) => (e[1] > m[1] ? e : m), ["", -1]);
      const cand = candidatos[sqVenc];
      const linha: LinhaLocal = {
        id: `${local.z}-${local.l}`,
        nome: local.nome ?? `Local ${local.l}`,
        bairro: local.bairro ?? "–",
        zona: local.z,
        aptos,
        comparecimento,
        votos: validosLocal,
        vencedor: cand?.n ?? "–",
        partido: cand?.p ?? "–",
        pct: validosLocal && votosVenc > 0 ? (100 * votosVenc) / validosLocal : 0,
        margem: margemPP(entradas.map(([, n]) => n), validosLocal),
        precisao: local.prec ?? "",
      };
      return { linha, local };
    });
  }, [dados, municipio.locais, candidatos]);

  const pontos = useMemo<PontoLocal[]>(
    () =>
      linhas
        .filter(({ local }) => local.lat !== null && local.lon !== null)
        .map(({ linha, local }) => ({
          id: linha.id,
          lat: local.lat as number,
          lon: local.lon as number,
          nome: linha.nome,
          bairro: local.bairro,
          endereco: local.end,
          precisao: local.prec,
          votos: linha.votos,
          vencedor: linha.vencedor,
          partido: linha.partido,
          pct: linha.pct.toFixed(1).replace(".", ",") + "%",
          cor: corPartido(linha.partido),
        })),
    [linhas],
  );

  const legenda = useMemo(() => {
    const porPartido = new Map<string, number>();
    for (const { linha } of linhas) porPartido.set(linha.partido, (porPartido.get(linha.partido) ?? 0) + 1);
    return [...porPartido.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  }, [linhas]);

  const topCandidatos = dados.candidatos.slice(0, 10).map(([sq, votos]) => ({
    nome: candidatos[sq]?.n ?? sq,
    partido: candidatos[sq]?.p ?? "?",
    votos,
    pct: v ? (100 * votos) / v : 0,
  }));
  const aproximados = pontos.filter((p) => p.precisao && APROXIMADA.has(p.precisao)).length;

  return (
    <div className="space-y-8">
      <SeletorCargo cargos={disponiveis} atual={cargo} onChange={setCargo} />

      <section className="space-y-3" aria-label="Resumo do município">
        <h2 className="text-lg font-semibold">
          {municipio.nome} · {dados.nome}
        </h2>
        <Cartoes totais={dados.totais} />
      </section>

      <section className="space-y-3" aria-label="Candidatos mais votados">
        <h2 className="text-lg font-semibold">Mais votados no município</h2>
        <GraficoCandidatos dados={topCandidatos} />
      </section>

      <section className="space-y-3" aria-label="Mapa dos locais de votação">
        <h2 className="text-lg font-semibold">Mapa dos locais de votação</h2>
        <p className="text-sm text-zinc-500">
          Cada círculo é um local de votação: o tamanho mostra os votos válidos e a cor, o partido do candidato mais votado ali.
          Círculos vazados e tracejados têm posição aproximada ({aproximados} neste município). Clique para ver detalhes.
        </p>
        <MapaLocais key={cargo} pontos={pontos} />
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {legenda.map(([partido, qtd]) => (
            <li key={partido} className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: corPartido(partido) }} />
              {partido} <span className="text-zinc-500">({qtd} {qtd === 1 ? "local" : "locais"})</span>
            </li>
          ))}
        </ul>
        <details className="text-sm text-zinc-500">
          <summary className="cursor-pointer">Como as posições foram obtidas</summary>
          <ul className="mt-2 list-disc pl-5">
            {Object.entries(PRECISAO).map(([k, t]) => (
              <li key={k}>{t}</li>
            ))}
          </ul>
        </details>
      </section>

      <section className="space-y-3" aria-label="Resultados por local de votação">
        <h2 className="text-lg font-semibold">
          Por local de votação <span className="text-sm font-normal text-zinc-500">({linhas.length} locais)</span>
        </h2>
        <Tabela dados={linhas.map((l) => l.linha)} colunas={colunas} placeholderBusca="Buscar local ou bairro…" filtroInicial={buscaInicial} />
      </section>
    </div>
  );
}
