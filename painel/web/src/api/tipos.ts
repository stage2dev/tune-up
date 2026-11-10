// Tipos do contrato da API do painel (servidor Python em 127.0.0.1).

export interface Sessao {
  token: string;
  projeto: { nome: string };
  versao: string;
}

export type Risco = 'leitura' | 'rascunho' | 'codigo' | 'credito';

export interface ParamAcao {
  nome: string;
  rotulo: string;
  tipo: 'fase' | 'parte' | 'texto' | 'escolha';
  obrigatorio: boolean;
  opcoes?: string[];
  max?: number;
  /** So em 'texto': true aceita quebra de linha (caixa grande). */
  linhas?: boolean;
  ajuda?: string;
}

export type Esforco = 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export interface Acao {
  id: string;
  /** Grupo da acao (ex.: "dev"); os blocos "acoes" dos modulos filtram por ele. */
  grupo: string;
  titulo: string;
  descricao: string;
  risco: Risco;
  confirmar: boolean;
  params: ParamAcao[];
  /** Modelos em ordem de preferencia; o ultimo e a reserva. [] = padrao do CLI. Opcional: servidor antigo nao manda. */
  modelos?: string[];
  esforco?: Esforco | null;
  equipe?: string;
}

/** GET /api/modelos: o que a licenca tem. */
export type StatusModelo = 'sim' | 'nao' | 'verificando' | 'nao_sei';
export interface RespModelos {
  modelos: Record<string, StatusModelo>;
}

export type EstadoExecucao = 'rodando' | 'precisa_de_voce' | 'terminou' | 'parada' | 'sumiu';

export interface Execucao {
  id: string;
  sessao_id: string;
  nome: string;
  acao: string;
  grupo?: string;
  /** Nome antigo de `grupo`, mantido para servidores antigos. */
  area?: string;
  titulo: string;
  params: Record<string, string>;
  iniciada_em: string;
  estado: EstadoExecucao;
  comando_attach: string;
  fase?: string;
  parte?: string;
  /** Apelido com que a sessao saiu; '' = padrao do CLI. Opcional: servidor antigo nao manda. */
  modelo?: string;
  esforco?: string;
  /** true quando da para mandar outra mensagem (POST /api/execucoes/{id}/responder). */
  pode_responder?: boolean;
}

export type TipoEvento = 'usuario' | 'assistente' | 'ferramenta' | 'resultado' | 'subagente' | 'sistema';

export interface EventoExecucao {
  n: number;
  ts: string;
  tipo: TipoEvento;
  texto: string;
  ferramenta?: string;
  erro?: boolean;
}

export interface Eventos {
  eventos: EventoExecucao[];
  proximo: number;
  estado: EstadoExecucao;
}

export type StatusItem = 'todo' | 'doing' | 'done' | 'dropped';

export interface ItemLista {
  tarefa: string;
  status: StatusItem;
  notas: string;
  produtos: { titulo: string; url: string }[];
  atualizado_em: string;
}

export interface ListaAcompanhamento {
  nome: string;
  area: string;
  atualizado_em: string;
  aberta: boolean;
  itens: ItemLista[];
  estado: Record<string, string>;
}

export interface AreaAcompanhamento {
  id: string;
  titulo: string;
}

export interface Acompanhamento {
  /** Areas conhecidas pelo servidor (opcional; sem ela, as areas saem das proprias listas). */
  areas?: AreaAcompanhamento[];
  listas: ListaAcompanhamento[];
  avisos: string[];
}

// O formato de /api/estado fica solto de proposito.
export type EstadoPainel = Record<string, unknown> & { avisos?: string[] };

// ---- Modulos (telas extras declarativas vindas do pacote do projeto) ----
export type TomBloco = 'neutro' | 'bom' | 'atencao' | 'ruim';
export type NivelAlerta = 'info' | 'atencao' | 'critico';

export interface ResumoModulo {
  id: string;
  titulo: string;
  icone?: string;
  alertas: number;
}

export interface ListaModulos {
  modulos: ResumoModulo[];
  avisos: string[];
}

export interface AlertaModulo {
  nivel: NivelAlerta;
  texto: string;
}

export interface Bloco {
  tipo: string;
  titulo?: string;
  [campo: string]: unknown;
}

/** Corpo e resposta de POST /api/modulos/<id>/acao (blocos formulario e conversa). */
export interface ReqAcaoModulo {
  acao: string;
  dados: Record<string, unknown>;
}
export interface RespAcaoModulo {
  ok: true;
  resultado: Record<string, unknown>;
}

export interface AbaModulo {
  id: string;
  titulo: string;
  blocos: Bloco[];
}

export interface DadosModulo {
  id: string;
  titulo: string;
  gerado_em: string;
  alertas: AlertaModulo[];
  abas: AbaModulo[];
  avisos: string[];
}
