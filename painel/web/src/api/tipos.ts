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
  /** So em 'texto' sem linhas: o servidor exige https:// sem espaco. */
  formato?: 'url';
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
  /** true quando a sessao trabalha ou espera e da para mandar com `interromper: true`. */
  pode_interromper?: boolean;
  /** Espera presa no terminal (pedido de permissao): mandar mensagem cancela o pedido, nao aprova. */
  espera_terminal?: boolean;
  /** Opcoes da pergunta que a sessao escreveu (so com pode_responder). */
  pergunta?: PerguntaChat;
  /** Nomes das skills escolhidas no pedido inicial (servidor antigo nao manda). */
  habilidades?: string[];
}

export interface PerguntaChat {
  perguntas: {
    pergunta: string;
    cabecalho: string;
    multipla: boolean;
    opcoes: { rotulo: string; descricao: string }[];
  }[];
}

export type TipoEvento = 'usuario' | 'assistente' | 'ferramenta' | 'resultado' | 'subagente' | 'sistema';

export interface EventoExecucao {
  n: number;
  ts: string;
  tipo: TipoEvento;
  texto: string;
  ferramenta?: string;
  erro?: boolean;
  /** Nomes das skills escolhidas nesta fala do dono (evento 'usuario'). */
  habilidades?: string[];
}

/** Skill da lista do chat (GET /api/habilidades). */
export interface Habilidade {
  id: string;
  nome: string;
  titulo: string;
  descricao: string;
  grupo: string;
  origem: string;
  /** false = plugin desligado ou pasta extra: o Claude le o arquivo so quando a pessoa escolhe. */
  listada: boolean;
  /** true = tune-up: sempre ligado, nao da para escolher. */
  fixa: boolean;
}

export interface GrupoHabilidade {
  id: string;
  titulo: string;
}

export interface RespHabilidades {
  grupos: GrupoHabilidade[];
  habilidades: Habilidade[];
  avisos?: string[];
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

// Blocos: copiados de contrato/blocos.d.ts. Um bloco de tipo desconhecido (versao mais nova do pacote) cai em BlocoDesconhecido.
export type Tom = TomBloco;
export type BlocoKpis = { tipo: 'kpis'; titulo?: string; itens: { rotulo: string; valor: string | number | null; detalhe?: string; tom?: Tom }[] };
export type BlocoTabela = { tipo: 'tabela'; titulo?: string; colunas: { id: string; rotulo: string; alinhar?: 'esq' | 'dir'; secundaria?: boolean }[];
  linhas: Record<string, string | number | null>[]; vazio?: string };
export type BlocoLista = { tipo: 'lista'; titulo?: string; itens: { titulo: string; detalhe?: string; selo?: { texto: string; tom: Tom } }[]; vazio?: string };
export type BlocoSerie = { tipo: 'serie'; titulo?: string; unidade?: string; series: { nome: string; pontos: { x: string; y: number | null }[] }[]; vazio?: string };
export type BlocoTexto = { tipo: 'texto'; titulo?: string; texto: string; ir_para?: { aba: string; rotulo: string } };
export type BlocoAcoes = { tipo: 'acoes'; titulo?: string; grupo: string };
export interface CampoFormulario {
  id: string;
  rotulo: string;
  tipo: 'texto' | 'texto_longo' | 'escolha' | 'segredo';
  opcoes?: { valor: string; rotulo: string }[];
  valor?: string;
  obrigatorio?: boolean;
  ajuda?: string;
}
export interface BlocoFormulario {
  tipo: 'formulario';
  id?: string;
  titulo?: string;
  descricao?: string;
  /** Comando do modulo (POST /api/modulos/<id>/acao). Use este OU `catalogo`. */
  acao?: string;
  /** Id de uma acao do catalogo; cada campo.id e o nome de um parametro dela. */
  catalogo?: string;
  /** Texto do dialogo de confirmacao de um comando do modulo (uma acao do catalogo usa o proprio `confirmar`). */
  confirmar?: string;
  botao: string;
  campos: CampoFormulario[];
  dados_fixos?: Record<string, unknown>;
  /** Segundo botao no mesmo cartao (ex.: Recusar ao lado de Aprovar): outro comando do modulo, mesmos campos. */
  secundario?: { acao: string; botao: string; confirmar?: string };
}
export interface MensagemConversa {
  id: string;
  de: 'contato' | 'eu' | 'ia';
  texto: string;
  quando: string;
  estado?: 'pendente' | 'enviado' | 'falhou' | 'incerto' | 'negado';
  nota?: string;
}
export interface BlocoConversa {
  tipo: 'conversa';
  id?: string;
  titulo?: string;
  mensagens: MensagemConversa[];
  enviar?: { acao: string; dados_fixos?: Record<string, unknown>; rotulo?: string };
  botoes?: { rotulo: string; acao: string; dados?: Record<string, unknown>; confirmar?: string }[];
  vazio?: string;
}
export interface BlocoImagem { tipo: 'imagem'; titulo?: string; data_uri: string; alt: string; legenda?: string }
export interface BlocoGaleria {
  tipo: 'galeria';
  titulo?: string;
  /** `arquivo` e relativo a pasta de midia do modulo; png, jpg, webp, mp4 ou webm. */
  itens: { arquivo: string; rotulo?: string; selo?: { texto: string; tom: Tom } }[];
  vazio?: string;
}
export interface BlocoMidia { tipo: 'midia'; titulo?: string; arquivo: string; alt?: string; legenda?: string }
/** Blocos de marca. Todos chamam POST /api/modulos/<id>/acao com o comando do bloco e mostram "Salvando…" e o aviso de fim.
 *  "cores" e "opcoes" (modo "um") escrevem num rascunho da aba: a "previa" da mesma aba muda na hora, antes do servidor responder;
 *  se o comando falha, volta ao valor do servidor. */
export interface BlocoCores {
  tipo: 'cores';
  id?: string;
  titulo?: string;
  descricao?: string;
  /** Comando do módulo. Ao soltar o seletor, envia { campo: chave, valor: "#rrggbb" }. */
  acao: string;
  itens: { chave: string; rotulo: string; uso?: string; valor: string }[];
  /** Pares de chaves conferidos na hora: contraste abaixo de 4,5:1 mostra `aviso` (ou um texto padrão). */
  contraste?: { a: string; b: string; aviso?: string }[];
  /** Botão opcional (ex.: "Pegar as cores da logo"): outro comando, com `dados`. */
  botao?: { rotulo: string; acao: string; dados?: Record<string, unknown> };
  vazio?: string;
}
/** Envio de imagem para POST /api/modulos/<id>/envio?destino=<destino> (INFO["envios"]). A tela confere tipo
 *  (png, jpeg, webp) e tamanho (`max_bytes`, teto 8 MB) antes; o servidor confere de novo pelos bytes. */
export interface BlocoEnvio {
  tipo: 'envio';
  id?: string;
  titulo?: string;
  descricao?: string;
  destino: string;
  /** "um" (padrão; ex.: logo) ou "grade" (várias fotos, uma de cada vez). */
  variante?: 'um' | 'grade';
  /** "um": imagem atual, caminho para GET /api/modulos/<id>/arquivo?c=. */
  atual?: string;
  alt?: string;
  /** "grade": fotos atuais (mesma rota). */
  itens?: { arquivo: string; rotulo?: string }[];
  /** "grade": botão Remover em cada foto; com confirmação, envia { destino, arquivo }. */
  remover?: { acao: string; confirmar?: string };
  max_bytes?: number;
  botao?: string;
  vazio?: string;
}
/** Post de exemplo desenhado pela tela (HTML e CSS), 4:5. `campos` liga um papel ao campo de um bloco "cores"
 *  (chave) ou "opcoes" (campo; papel "letras", usa as `fontes` da opção) da mesma aba. */
export interface BlocoPrevia {
  tipo: 'previa';
  titulo?: string;
  nome: string;
  /** Caminho para GET /api/modulos/<id>/arquivo?c= (png, jpg, webp). */
  logo?: string;
  cores: { fundo: string; texto: string; principal: string; destaque: string; superficie?: string };
  fontes?: { titulo?: string; texto?: string };
  campos?: { fundo?: string; texto?: string; principal?: string; destaque?: string; superficie?: string; letras?: string };
  textos?: { numero?: string; chamada?: string; frase?: string; botao?: string };
  legenda?: string;
}
/** Modo "um": cartões, 1 entre N; envia { campo, valor }. Com `fontes`, o cartão vem escrito naquelas letras (`exemplo`).
 *  Modo "varios": chips liga/desliga; envia { campo, valor, ligado }. */
export interface BlocoOpcoes {
  tipo: 'opcoes';
  id?: string;
  titulo?: string;
  descricao?: string;
  acao: string;
  campo: string;
  modo?: 'um' | 'varios';
  /** Modo "um": o valor escolhido hoje. */
  valor?: string;
  opcoes: { valor: string; rotulo: string; detalhe?: string; fontes?: { titulo: string; texto?: string }; ligado?: boolean }[];
  exemplo?: { titulo?: string; texto?: string };
  vazio?: string;
}
export interface BlocoDesconhecido { tipo: string; titulo?: string; [campo: string]: unknown }
export type Bloco =
  | BlocoKpis | BlocoTabela | BlocoLista | BlocoSerie | BlocoTexto | BlocoAcoes
  | BlocoFormulario | BlocoConversa | BlocoImagem | BlocoGaleria | BlocoMidia
  | BlocoCores | BlocoEnvio | BlocoPrevia | BlocoOpcoes | BlocoDesconhecido;

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
