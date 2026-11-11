// Blocos das telas de módulo (GET /api/modulos/<id>) e a ação de módulo. Reexportado por api.d.ts.

export type Tom = 'neutro' | 'bom' | 'atencao' | 'ruim';

export type Bloco =
  | { tipo: 'kpis'; titulo?: string; itens: { rotulo: string; valor: string | number | null; detalhe?: string; tom?: Tom }[] }
  | { tipo: 'tabela'; titulo?: string; colunas: { id: string; rotulo: string; alinhar?: 'esq' | 'dir'; secundaria?: boolean }[];
      linhas: Record<string, string | number | null>[]; vazio?: string }
  | { tipo: 'lista'; titulo?: string; itens: { titulo: string; detalhe?: string; selo?: { texto: string; tom: Tom } }[];
      vazio?: string }
  | { tipo: 'serie'; titulo?: string; unidade?: string;
      series: { nome: string; pontos: { x: string; y: number | null }[] }[]; vazio?: string }
  | { tipo: 'texto'; titulo?: string; texto: string; /** Botão que abre outra aba do mesmo módulo. */ ir_para?: { aba: string; rotulo: string } }
  | { tipo: 'acoes'; titulo?: string; grupo: string }
  | BlocoFormulario
  | BlocoConversa
  | BlocoImagem
  | BlocoGaleria
  | BlocoMidia
  | BlocoCores
  | BlocoEnvio
  | BlocoPrevia
  | BlocoOpcoes
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
  /** Comando do módulo (POST /api/modulos/<id>/acao). Use este OU `catalogo`. */
  acao?: string;
  /** Id de uma ação do catálogo; cada campo.id é o nome de um parâmetro dela. Com `confirmar: true` na ação, a tela pede confirmação. */
  catalogo?: string;
  /** Texto do diálogo de confirmação de um comando do módulo. */
  confirmar?: string;
  botao: string;
  campos: CampoFormulario[];
  dados_fixos?: Record<string, unknown>;
  /** Segundo botão no mesmo cartão (ex.: Recusar ao lado de Aprovar): outro comando do módulo, mesmos campos. */
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
/** Só data:image/png;base64 e data:image/jpeg;base64 (svg pode carregar script). */
export interface BlocoImagem {
  tipo: 'imagem';
  titulo?: string;
  data_uri: string;
  alt: string;
  legenda?: string;
}

/** Arquivos vêm de GET /api/modulos/<id>/arquivo?c=<arquivo> (pasta declarada em INFO["midia"]; png, jpg, webp, mp4, webm).
 *  A tela só pede arquivos com essas extensões; o servidor responde 404 para o resto. */
export interface BlocoGaleria {
  tipo: 'galeria';
  titulo?: string;
  itens: { arquivo: string; rotulo?: string; selo?: { texto: string; tom: Tom } }[];
  vazio?: string;
}
/** Uma imagem, ou um vídeo com controles (decidido pela extensão de `arquivo`). `.csv`: só um link de download,
 *  servido como anexo e só de pasta que o módulo lista em INFO["baixar"]. */
export interface BlocoMidia {
  tipo: 'midia';
  titulo?: string;
  arquivo: string;
  alt?: string;
  legenda?: string;
}

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

/** POST /api/modulos/<id>/acao. 200 { ok: true, resultado }; erros { erro } com 400/403/404/409/500/503.
 *  GET /api/modulos/<id>?fresco=1 devolve o módulo sem o cache do servidor. */
export interface ReqAcaoModulo {
  acao: string;
  dados: Record<string, unknown>;
}
export interface RespAcaoModulo {
  ok: true;
  resultado: Record<string, unknown>;
}
