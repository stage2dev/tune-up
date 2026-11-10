// Tipos de /api/estado usados pelas telas de desenvolvimento.
// Copiados de contrato/api.d.ts (a pasta api/ do web guarda o estado como "solto" de proposito).
export type StatusParte = 'fechada' | 'precisa_de_voce' | 'rodando' | 'pendente';

export interface PR {
  numero: number;
  titulo: string;
  estado: string;
  branch: string;
  url: string;
  atualizada: string;
}

export interface Volta {
  volta: number | null;
  critico: number;
  alto: number;
}

export interface ItemRevisado {
  id: string;
  voltas: Volta[];
  teve_achado: boolean;
}

export interface Parte {
  id: string;
  itens_plano: string | null;
  status: StatusParte;
  origem: string;
  parcial: boolean;
  pr: PR | null;
  itens: ItemRevisado[];
  comando_copiar: string;
}

export interface Fase {
  numero: string;
  slug: string;
  pasta: string;
  titulo: string | null;
  acompanhada: boolean;
  partes: Parte[];
  depois_abertos: number | null;
  perguntas_abertas: { linha: number; texto: string }[];
  precisa: { parte: string | null; linha: number; texto: string }[];
  completa: boolean;
}

export interface Pendencia {
  fase: string;
  parte: string | null;
  tipo: 'marcador' | 'pergunta';
  texto: string;
  origem: string;
}

export interface Estado {
  gerado_em: string;
  resumo: {
    fases_total: number;
    fases_acompanhadas: number;
    fases_abertas: number;
    partes_fechadas: number;
    partes_total: number;
    pendencias_dono: number;
    prs_abertas: number;
    sessoes_rodando: number;
    sessoes_ativas: number;
  };
  precisa_de_voce: Pendencia[];
  fases: Fase[];
  prs: PR[];
  avisos: string[];
}
