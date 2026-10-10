// Formato dos JSON gerados por exportar_json.py (web/public/data).

export type Totais = {
  aptos: number;
  comparecimento: number;
  brancos: number;
  nulos: number;
  legenda: number;
  nominais: number;
};

export type Cargo = { cd: number; nome: string };

export type Index = {
  fonte: string;
  dados_gerados_em: string;
  eleicoes: { ano: number; turno: number; cargos: Cargo[] }[];
  municipios: { cd: number; nome: string }[];
};

export type Candidato = {
  n: string; // nome de urna
  p: string; // partido
  nr: number; // número
  c: number; // código do cargo
  nc: string; // nome completo
  pessoa: number;
};

/** [sq_candidato, votos] */
export type VotoCandidato = [string, number];

export type Estado = {
  ano: number;
  turno: number;
  cargo: Cargo;
  totais: Totais;
  candidatos: VotoCandidato[];
  municipios: { cd: number; nome: string; totais: Totais; top: VotoCandidato[] }[];
};

export type LocalVotacao = {
  z: number; // zona
  l: number; // número do local
  nome: string | null;
  bairro: string | null;
  end: string | null;
  lat: number | null;
  lon: number | null;
  prec: string | null; // tse | exata | rua | povoado | municipio | manual
  tipo: string | null;
  sit: string | null;
};

/** [idx_local, aptos, comparecimento, brancos, nulos, legenda, { sq: votos }] */
export type LinhaLocal = [number, number, number, number, number, number, Record<string, number>];

export type CargoMunicipio = {
  nome: string;
  totais: Totais;
  candidatos: VotoCandidato[];
  por_local: LinhaLocal[];
};

export type Municipio = {
  cd: number;
  nome: string;
  locais: LocalVotacao[];
  cargos: Record<string, CargoMunicipio>;
};
