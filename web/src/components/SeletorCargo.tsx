"use client";

import type { Cargo } from "@/lib/tipos";

/** Abas para trocar o cargo exibido. */
export default function SeletorCargo({
  cargos,
  atual,
  onChange,
}: {
  cargos: Cargo[];
  atual: number;
  onChange: (cd: number) => void;
}) {
  return (
    <div role="tablist" aria-label="Cargo" className="flex flex-wrap gap-2">
      {cargos.map((c) => (
        <button
          key={c.cd}
          role="tab"
          aria-selected={c.cd === atual}
          onClick={() => onChange(c.cd)}
          className={
            "rounded-full border px-4 py-1.5 text-sm transition " +
            (c.cd === atual
              ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
              : "border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800")
          }
        >
          {c.nome}
        </button>
      ))}
    </div>
  );
}
