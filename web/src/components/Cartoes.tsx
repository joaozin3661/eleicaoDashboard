import { fmt, pct, validos } from "@/lib/formato";
import type { Totais } from "@/lib/tipos";

function Cartao({ titulo, valor, detalhe }: { titulo: string; valor: string; detalhe?: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="text-xs uppercase tracking-wide text-zinc-500">{titulo}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{valor}</div>
      {detalhe && <div className="text-xs text-zinc-500">{detalhe}</div>}
    </div>
  );
}

/** Resumo de participação e votos de uma região. */
export default function Cartoes({ totais }: { totais: Totais }) {
  const v = validos(totais);
  const votosTotais = v + totais.brancos + totais.nulos;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Cartao titulo="Eleitores aptos" valor={fmt(totais.aptos)} />
      <Cartao
        titulo="Comparecimento"
        valor={fmt(totais.comparecimento)}
        detalhe={`${pct(totais.comparecimento, totais.aptos)} dos aptos`}
      />
      <Cartao
        titulo="Abstenção"
        valor={fmt(totais.aptos - totais.comparecimento)}
        detalhe={pct(totais.aptos - totais.comparecimento, totais.aptos) + " dos aptos"}
      />
      <Cartao titulo="Votos válidos" valor={fmt(v)} detalhe={pct(v, votosTotais) + " dos votos"} />
      <Cartao titulo="Brancos" valor={fmt(totais.brancos)} detalhe={pct(totais.brancos, votosTotais) + " dos votos"} />
      <Cartao titulo="Nulos" valor={fmt(totais.nulos)} detalhe={pct(totais.nulos, votosTotais) + " dos votos"} />
    </div>
  );
}
