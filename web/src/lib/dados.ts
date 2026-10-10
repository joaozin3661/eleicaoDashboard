// Leitura dos JSON em tempo de build (roda só no servidor/build, nunca no navegador).
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { Candidato, Estado, Index, Municipio } from "./tipos";

const DIR = path.join(process.cwd(), "public", "data");

async function ler<T>(...partes: string[]): Promise<T> {
  return JSON.parse(await readFile(path.join(DIR, ...partes), "utf-8")) as T;
}

export const lerIndex = () => ler<Index>("index.json");
export const lerCandidatos = (ano: number) => ler<Record<string, Candidato>>(`candidatos-${ano}.json`);
export const lerEstado = (ano: number, turno: number, cargo: number) =>
  ler<Estado>("estado", `${ano}-${turno}-${cargo}.json`);
export const lerMunicipio = (ano: number, turno: number, cd: number | string) =>
  ler<Municipio>("municipios", `${ano}-${turno}`, `${cd}.json`);

/** Eleição mais recente disponível (ano e turno). */
export function eleicaoAtual(index: Index) {
  return [...index.eleicoes].sort((a, b) => a.ano - b.ano || a.turno - b.turno).at(-1)!;
}
