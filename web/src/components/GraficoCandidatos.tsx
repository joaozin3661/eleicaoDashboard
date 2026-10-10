"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { corPartido, fmt } from "@/lib/formato";

export type BarraCandidato = { nome: string; partido: string; votos: number; pct: number };

/** Barras horizontais com os candidatos mais votados. */
export default function GraficoCandidatos({ dados }: { dados: BarraCandidato[] }) {
  const altura = 34 * dados.length + 30;
  return (
    <div style={{ height: altura }} role="img" aria-label="Gráfico de barras dos candidatos mais votados">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={dados} layout="vertical" margin={{ left: 8, right: 56, top: 4, bottom: 4 }}>
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis
            type="category"
            dataKey="nome"
            width={150}
            tick={{ fontSize: 12, fill: "currentColor" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(128,128,128,0.12)" }}
            formatter={(valor, _nome, item) => [
              `${fmt(Number(valor))} votos (${item.payload.pct.toFixed(1).replace(".", ",")}% dos válidos)`,
              item.payload.partido,
            ]}
            labelStyle={{ color: "#111" }}
          />
          <Bar
            isAnimationActive={false}
            dataKey="votos"
            radius={[0, 4, 4, 0]}
            label={{
              position: "right",
              fontSize: 12,
              fill: "currentColor",
              formatter: (v: unknown) => fmt(Number(v)),
            }}
          >
            {dados.map((d) => (
              <Cell key={d.nome + d.partido} fill={corPartido(d.partido)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
