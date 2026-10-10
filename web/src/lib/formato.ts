import type { Totais } from "./tipos";

const inteiro = new Intl.NumberFormat("pt-BR");
export const fmt = (n: number) => inteiro.format(n);

export const pct = (parte: number, total: number, casas = 1) =>
  total > 0 ? `${((100 * parte) / total).toFixed(casas).replace(".", ",")}%` : "–";

/** Votos válidos = votos em candidatos + votos de legenda (brancos e nulos ficam de fora). */
export const validos = (t: Totais) => t.nominais + t.legenda;

/** Cores fixas dos partidos (iguais em todo o site). Os maiores têm cores bem distintas entre si. */
const CORES: Record<string, string> = {
  PT: "#dc2626",
  PL: "#1d4ed8",
  PP: "#0891b2",
  MDB: "#16a34a",
  PSD: "#f59e0b",
  PSDB: "#60a5fa",
  AVANTE: "#7c3aed",
  PSOL: "#c026d3",
  NOVO: "#fb923c",
  DEMOCRATA: "#854d0e",
  DC: "#0f766e",
  MOBILIZA: "#be185d",
  REPUBLICANOS: "#1e3a8a",
  MISSAO: "#f472b6",
  PDT: "#ea580c",
  UNIAO: "#0369a1",
  PODE: "#84cc16",
  PV: "#15803d",
  UP: "#6b7280",
  PCO: "#7f1d1d",
  PSTU: "#9f1239",
  CIDADANIA: "#a16207",
  PCDOB: "#991b1b",
  REDE: "#059669",
  PRTB: "#4d7c0f",
  PCB: "#450a0a",
};

const semAcento = (t: string) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();

/** Cor do partido; partido desconhecido recebe uma cor estável derivada da sigla. */
export function corPartido(sigla: string): string {
  const fixa = CORES[semAcento(sigla)];
  if (fixa) return fixa;
  let h = 0;
  for (const ch of sigla) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h} 55% 40%)`;
}

export const PRECISAO: Record<string, string> = {
  tse: "Coordenada do cadastro do TSE",
  exata: "Prédio localizado pelo nome",
  rua: "Aproximada: centro da rua",
  povoado: "Aproximada: centro do povoado",
  municipio: "Aproximada: centro do município",
  manual: "Marcada manualmente",
};

/** Pontos que não indicam o prédio com exatidão. */
export const APROXIMADA = new Set(["rua", "povoado", "municipio"]);
