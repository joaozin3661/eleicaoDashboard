import { Suspense } from "react";
import EstadoView from "@/components/EstadoView";
import { eleicaoAtual, lerCandidatos, lerEstado, lerIndex } from "@/lib/dados";
import type { Estado } from "@/lib/tipos";

export default async function Home() {
  const index = await lerIndex();
  const { ano, turno, cargos } = eleicaoAtual(index);

  // Os JSON são lidos no build: o HTML já sai com os dados dentro.
  const [candidatos, ...lista] = await Promise.all([
    lerCandidatos(ano),
    ...cargos.map((c) => lerEstado(ano, turno, c.cd)),
  ]);
  const estados: Record<number, Estado> = Object.fromEntries(lista.map((e) => [e.cargo.cd, e]));

  const posicoes: Record<number, { lat: number; lon: number }> = {};
  for (const m of index.municipios) if (m.lat !== null && m.lon !== null) posicoes[m.cd] = { lat: m.lat, lon: m.lon };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Resultados das eleições de {ano} no Piauí</h1>
        <p className="mt-1 text-zinc-500">
          {turno}º turno · votos por município, zona eleitoral e local de votação. Dados do TSE (gerados em{" "}
          {index.dados_gerados_em.split("-").reverse().join("/")}).
        </p>
      </div>
      {/* useSearchParams (links da busca) exige Suspense em site estático */}
      <Suspense>
        <EstadoView cargos={cargos} estados={estados} candidatos={candidatos} posicoes={posicoes} />
      </Suspense>
    </div>
  );
}
