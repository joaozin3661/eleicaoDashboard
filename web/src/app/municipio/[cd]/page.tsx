import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import MunicipioView from "@/components/MunicipioView";
import { eleicaoAtual, lerCandidatos, lerIndex, lerMunicipio } from "@/lib/dados";

// Site estático: só existem as páginas listadas aqui (uma por município).
export const dynamicParams = false;

export async function generateStaticParams() {
  const index = await lerIndex();
  return index.municipios.map((m) => ({ cd: String(m.cd) }));
}

export async function generateMetadata({ params }: { params: Promise<{ cd: string }> }): Promise<Metadata> {
  const { cd } = await params;
  const index = await lerIndex();
  const { ano, turno } = eleicaoAtual(index);
  const m = await lerMunicipio(ano, turno, cd);
  return {
    title: `${m.nome} — Eleições ${ano} no Piauí`,
    description: `Resultados das eleições de ${ano} em ${m.nome} (PI): votos por zona e local de votação, com mapa.`,
  };
}

export default async function PaginaMunicipio({ params }: { params: Promise<{ cd: string }> }) {
  const { cd } = await params;
  const index = await lerIndex();
  const { ano, turno, cargos } = eleicaoAtual(index);
  const [municipio, candidatos] = await Promise.all([lerMunicipio(ano, turno, cd), lerCandidatos(ano)]);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-blue-700 hover:underline dark:text-blue-400">
          ← Piauí
        </Link>
        <h1 className="mt-2 text-2xl font-bold">{municipio.nome}</h1>
        <p className="text-zinc-500">
          Eleições {ano} · {turno}º turno
        </p>
      </div>
      <Suspense>
        <MunicipioView municipio={municipio} cargos={cargos} candidatos={candidatos} />
      </Suspense>
    </div>
  );
}
