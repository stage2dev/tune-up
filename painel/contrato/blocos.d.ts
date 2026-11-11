// Blocos das telas de módulo (GET /api/modulos/<id>) e a ação de módulo. Reexportado por api.d.ts.

export type Tom = 'neutro' | 'bom' | 'atencao' | 'ruim';

export type Bloco =
  | { tipo: 'kpis'; titulo?: string; itens: { rotulo: string; valor: string | number | null; detalhe?: string; tom?: Tom }[] }
  | { tipo: 'tabela'; titulo?: string; colunas: { id: string; rotulo: string; alinhar?: 'esq' | 'dir' }[];
      linhas: Record<string, string | number | null>[]; vazio?: string }
  | { tipo: 'lista'; titulo?: string; itens: { titulo: string; detalhe?: string; selo?: { texto: string; tom: Tom } }[];
      vazio?: string }
  | { tipo: 'serie'; titulo?: string; unidade?: string;
      series: { nome: string; pontos: { x: string; y: number | null }[] }[]; vazio?: string }
  | { tipo: 'texto'; titulo?: string; texto: string }
  | { tipo: 'acoes'; titulo?: string; grupo: string }
  | BlocoFormulario
  | BlocoConversa
  | BlocoCaixa
  | BlocoImagem
  | { tipo: string; [k: string]: unknown }; // desconhecido: a tela mostra um aviso discreto

/** Blocos interativos. O envio chama POST /api/modulos/<id>/acao (ver ReqAcaoModulo). */
export interface CampoFormulario {
  id: string;
  rotulo: string;
  tipo: 'texto' | 'texto_longo' | 'escolha' | 'segredo';
  opcoes?: { valor: string; rotulo: string }[];
  valor?: string;
  obrigatorio?: boolean;
  ajuda?: string;
}
/** Envia { acao, dados: { ...dados_fixos, ...valores } }. Campo "segredo": senha, nunca preenchido. */
export interface BlocoFormulario {
  tipo: 'formulario';
  /** Opcional: chave estável do bloco (senão a tela usa tipo + ação + dados fixos). */
  id?: string;
  titulo?: string;
  descricao?: string;
  acao: string;
  botao: string;
  campos: CampoFormulario[];
  dados_fixos?: Record<string, unknown>;
}
export interface MensagemConversa {
  id: string;
  de: 'contato' | 'eu' | 'ia';
  texto: string;
  quando: string;
  /** Sem tipo (ou 'texto') = texto. O resto vira uma etiqueta ("Áudio – ouça no celular"); texto "[audio]" some. */
  tipo?: 'texto' | 'audio' | 'imagem' | 'documento' | 'outro';
  estado?: 'pendente' | 'enviado' | 'falhou' | 'incerto' | 'negado';
  nota?: string;
}
/** Enviar posta { acao, dados: { ...dados_fixos, texto, id_cliente } }; um id_cliente por mensagem, o mesmo nas tentativas de reenvio. */
export interface BlocoConversa {
  tipo: 'conversa';
  /** Opcional: chave estável do bloco. */
  id?: string;
  titulo?: string;
  mensagens: MensagemConversa[];
  enviar?: { acao: string; dados_fixos?: Record<string, unknown>; rotulo?: string };
  botoes?: { rotulo: string; acao: string; dados?: Record<string, unknown>; confirmar?: string }[];
  vazio?: string;
}
/** Caixa de entrada: lista de conversas (busca no navegador) e a conversa aberta ao lado; tela estreita = uma por vez.
 *  Clicar numa linha posta { acao: abrir.acao, dados: { ...abrir.dados_fixos, conversa_id: id } } e relê o módulo.
 *  O servidor descarta o bloco sem `abrir.acao` e as linhas sem id/titulo (com aviso). */
export interface BlocoCaixa {
  tipo: 'caixa';
  id?: string;
  titulo?: string;
  conversas: {
    id: string;
    titulo: string;
    /** Prévia da última mensagem (uma linha). */
    detalhe?: string;
    quando?: string;
    selo?: { texto: string; tom: Tom };
    nao_lidas?: number;
    ativa?: boolean;
  }[];
  abrir: { acao: string; dados_fixos?: Record<string, unknown> };
  /** A conversa aberta: mesmo formato do bloco conversa (sem tipo). */
  conversa?: Omit<BlocoConversa, 'tipo'>;
  vazio?: string;
  vazio_conversa?: string;
}
/** Só data:image/png;base64 e data:image/jpeg;base64 (svg pode carregar script). */
export interface BlocoImagem {
  tipo: 'imagem';
  titulo?: string;
  data_uri: string;
  alt: string;
  legenda?: string;
}

/** POST /api/modulos/<id>/acao. 200 { ok: true, resultado }; erros { erro } com 400/403/404/409/422/500/503
 *  (422: agir devolveu { ok: false, mensagem }; erro = mensagem).
 *  GET /api/modulos/<id>?fresco=1 devolve o módulo sem o cache do servidor. */
export interface ReqAcaoModulo {
  acao: string;
  dados: Record<string, unknown>;
}
export interface RespAcaoModulo {
  ok: true;
  resultado: Record<string, unknown>;
}
