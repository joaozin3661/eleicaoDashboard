"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ItemBusca } from "@/lib/tipos";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const semAcento = (t: string) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const ROTULO: Record<ItemBusca["t"], string> = { m: "Municípios", c: "Candidatos", l: "Locais de votação" };
const LIMITE: Record<ItemBusca["t"], number> = { m: 5, c: 5, l: 6 };

/** Busca global (município, candidato, local de votação). O índice só é baixado no primeiro uso. */
export default function Busca({ ano, turno }: { ano: number; turno: number }) {
  const router = useRouter();
  const [texto, setTexto] = useState("");
  const [itens, setItens] = useState<ItemBusca[] | null>(null);
  const [erro, setErro] = useState(false);
  const [aberto, setAberto] = useState(false);
  const [sel, setSel] = useState(0);
  const carregando = useRef(false);

  function carregar() {
    if (itens || carregando.current) return;
    carregando.current = true;
    fetch(`${BASE}/data/busca-${ano}-${turno}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((dados: ItemBusca[]) => setItens(dados))
      .catch(() => {
        setErro(true);
        carregando.current = false;
      });
  }

  const indice = useMemo(() => (itens ?? []).map((item) => ({ item, nome: semAcento(item.n), tudo: semAcento(`${item.n} ${item.s}`) })), [itens]);

  const resultados = useMemo(() => {
    const termos = semAcento(texto).split(/\s+/).filter(Boolean);
    if (termos.join("").length < 2) return [];
    const achados = indice
      .filter((x) => termos.every((t) => x.tudo.includes(t)))
      .map((x) => ({
        item: x.item,
        // 0 = nome começa com o termo; 1 = termo no nome; 2 = termo só no subtítulo (município/bairro)
        nota: x.nome.startsWith(termos[0]) ? 0 : termos.every((t) => x.nome.includes(t)) ? 1 : 2,
      }))
      .sort((a, b) => a.nota - b.nota || a.item.n.localeCompare(b.item.n, "pt-BR"));
    const contagem = { m: 0, c: 0, l: 0 };
    const lista: ItemBusca[] = [];
    for (const t of ["m", "c", "l"] as const) {
      for (const a of achados) {
        if (a.item.t === t && contagem[t] < LIMITE[t]) {
          lista.push(a.item);
          contagem[t]++;
        }
      }
    }
    return lista;
  }, [indice, texto]);

  function ir(item: ItemBusca) {
    setAberto(false);
    setTexto("");
    router.push(item.u);
  }

  function aoTeclar(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSel((s) => Math.min(resultados.length - 1, s + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSel((s) => Math.max(0, s - 1));
    } else if (e.key === "Enter" && resultados[sel]) {
      ir(resultados[sel]);
    } else if (e.key === "Escape") {
      setAberto(false);
    }
  }

  return (
    <div className="relative w-full max-w-sm">
      <input
        type="search"
        value={texto}
        onChange={(e) => {
          setTexto(e.target.value);
          setSel(0);
          setAberto(true);
        }}
        onFocus={() => {
          carregar();
          setAberto(true);
        }}
        onBlur={() => setTimeout(() => setAberto(false), 150)}
        onKeyDown={aoTeclar}
        placeholder="Buscar candidato, município ou escola…"
        aria-label="Buscar candidato, município ou escola"
        role="combobox"
        aria-expanded={aberto && resultados.length > 0}
        aria-controls="resultados-busca"
        className="w-full rounded-md border border-zinc-300 bg-transparent px-3 py-1.5 text-sm dark:border-zinc-700"
      />
      {aberto && texto.trim().length >= 2 && (
        <div
          id="resultados-busca"
          role="listbox"
          className="absolute right-0 z-[1000] mt-1 max-h-96 w-full min-w-72 overflow-y-auto rounded-md border border-zinc-200 bg-white p-1 text-sm shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          {erro && <div className="px-3 py-2 text-zinc-500">Não foi possível carregar a busca.</div>}
          {!erro && !itens && <div className="px-3 py-2 text-zinc-500">Carregando…</div>}
          {!erro && itens && resultados.length === 0 && <div className="px-3 py-2 text-zinc-500">Nada encontrado.</div>}
          {resultados.map((r, i) => (
            <div key={r.t + r.u + r.n}>
              {(i === 0 || resultados[i - 1].t !== r.t) && (
                <div className="px-3 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-zinc-500">{ROTULO[r.t]}</div>
              )}
              <button
                role="option"
                aria-selected={i === sel}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => ir(r)}
                onMouseEnter={() => setSel(i)}
                className={"block w-full rounded px-3 py-1.5 text-left " + (i === sel ? "bg-zinc-100 dark:bg-zinc-800" : "")}
              >
                <span className="block truncate font-medium">{r.n}</span>
                {r.s && <span className="block truncate text-xs text-zinc-500">{r.s}</span>}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
