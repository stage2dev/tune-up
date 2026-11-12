// Parte pura dos blocos interativos (formulario, conversa, imagem): le o bloco com cuidado e monta os dados
// do envio. Sem React aqui, para testar sem tela.
import { ErroApi } from '../../api/cliente';

/** O bloco como chega do servidor, antes de ser lido: qualquer campo pode faltar ou vir com outro tipo. So o renderizador usa isto. */
export type BlocoCru = { tipo: string; titulo?: string; [campo: string]: unknown };

export interface Opcao { valor: string; rotulo: string }
export interface CampoLido { id: string; rotulo: string; tipo: 'texto' | 'texto_longo' | 'escolha' | 'segredo'; opcoes: Opcao[]; valor: string; obrigatorio: boolean; ajuda?: string }

const TIPOS_CAMPO = ['texto', 'texto_longo', 'escolha', 'segredo'] as const;
const str = (v: unknown): string => (typeof v === 'string' ? v : '');
const objeto = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
export const itens = (v: unknown): Record<string, unknown>[] =>
  Array.isArray(v) ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object') : [];
export const textoOuNada = (v: unknown): string | undefined => (typeof v === 'string' && v.trim() ? v : undefined);
export { objeto as dadosFixos };

export function lerCampos(v: unknown): CampoLido[] {
  return itens(v)
    .filter((c) => typeof c.id === 'string' && c.id)
    .map((c) => ({
      id: String(c.id),
      rotulo: str(c.rotulo) || String(c.id),
      tipo: (TIPOS_CAMPO as readonly string[]).includes(String(c.tipo)) ? (c.tipo as CampoLido['tipo']) : 'texto',
      opcoes: itens(c.opcoes).filter((o) => typeof o.valor === 'string').map((o) => ({ valor: String(o.valor), rotulo: str(o.rotulo) || String(o.valor) })),
      valor: str(c.valor),
      obrigatorio: c.obrigatorio === true,
      ajuda: textoOuNada(c.ajuda),
    }))
    .map((c) => (c.tipo === 'escolha' && !c.opcoes.some((o) => o.valor === c.valor) ? { ...c, valor: '' } : c)); // valor fora das opcoes = vazio
}

/** Valor mostrado: o que a pessoa digitou, senao o do servidor. Segredo nunca vem preenchido. */
export const valorDoCampo = (c: CampoLido, editados: Record<string, string>): string =>
  editados[c.id] ?? (c.tipo === 'segredo' ? '' : c.valor);

/** ids dos campos obrigatorios ainda vazios. */
export const camposFaltando = (campos: CampoLido[], editados: Record<string, string>): string[] =>
  campos.filter((c) => c.obrigatorio && !valorDoCampo(c, editados).trim()).map((c) => c.id);

/** { ...dados_fixos, ...valores }: os valores dos campos ganham dos dados fixos. */
export function dadosDoFormulario(fixos: unknown, campos: CampoLido[], editados: Record<string, string>): Record<string, unknown> {
  const dados: Record<string, unknown> = { ...objeto(fixos) };
  for (const c of campos) dados[c.id] = valorDoCampo(c, editados);
  return dados;
}

/** Depois de enviar: so os segredos somem; o resto fica como a pessoa deixou. */
export function semSegredos(campos: CampoLido[], editados: Record<string, string>): Record<string, string> {
  const out = { ...editados };
  for (const c of campos) if (c.tipo === 'segredo') delete out[c.id];
  return out;
}

/** { ...dados_fixos, texto, id_cliente } (id_cliente e a chave de deduplicacao no servidor: um por mensagem). */
export function dadosDaMensagem(fixos: unknown, texto: string, novoId: () => string = () => crypto.randomUUID()): Record<string, unknown> {
  return { ...objeto(fixos), texto, id_cliente: novoId() };
}

/**
 * Envio de mensagem sem React. O id pertence a MENSAGEM: muda so quando o texto muda ou depois de um sucesso;
 * repetir o mesmo texto apos falha reusa o id (o servidor deduplica). Uma chamada em voo por vez.
 * `post` devolve true quando deu certo; false ou erro = falha.
 */
export function criarEnviador(post: (texto: string, id: string) => Promise<boolean>, novoId: () => string = () => crypto.randomUUID()) {
  let id: string | null = null;
  let textoDoId = '';
  let emVoo = false;
  return async (texto: string): Promise<boolean> => {
    if (emVoo) return false;
    if (id === null || textoDoId !== texto) { id = novoId(); textoDoId = texto; }
    emVoo = true;
    try {
      const ok = await post(texto, id);
      if (ok) id = null;
      return ok;
    } catch {
      return false;
    } finally {
      emVoo = false;
    }
  };
}

/** Copia do botao no momento do clique: a confirmacao executa exatamente isto, mesmo se a lista mudar depois. */
export interface BotaoCopia { acao: string; dados: Record<string, unknown>; confirmar?: string; rotulo: string }
export const copiaDoBotao = (x: Record<string, unknown>): BotaoCopia => ({
  acao: String(x.acao), dados: { ...objeto(x.dados) }, confirmar: textoOuNada(x.confirmar), rotulo: String(x.rotulo),
});

const EXT_IMAGEM = ['png', 'jpg', 'jpeg', 'webp'];
const EXT_VIDEO = ['mp4', 'webm'];
/** Tipo de midia pela extensao do caminho (a mesma lista da rota do servidor); outra extensao = null. */
export function tipoDaMidia(c: unknown): 'imagem' | 'video' | null {
  if (typeof c !== 'string') return null;
  const ext = c.split('.').pop()?.toLowerCase() ?? '';
  return EXT_IMAGEM.includes(ext) ? 'imagem' : EXT_VIDEO.includes(ext) ? 'video' : null;
}
/** URL da rota de midia do modulo (GET /api/modulos/<id>/arquivo?c=<caminho>). */
export const urlDoArquivo = (moduloId: string, c: string): string => `/api/modulos/${encodeURIComponent(moduloId)}/arquivo?c=${encodeURIComponent(c)}`;

export const CONFIRMAR_PADRAO = 'Quer mesmo começar? Você poderá parar a qualquer momento na tela da execução.';
/** Texto do dialogo antes de enviar, ou undefined = envia direto. Acao do catalogo com `confirmar` sempre pede,
 *  mesmo com a descricao vazia (texto padrao); sem acao do catalogo vale o `confirmar` do bloco. */
export function textoDeConfirmacao(acaoCat: { confirmar: boolean; descricao: string } | null, doBloco: unknown): string | undefined {
  if (acaoCat) return acaoCat.confirmar ? (textoOuNada(acaoCat.descricao) ?? CONFIRMAR_PADRAO) : undefined;
  return textoOuNada(doBloco);
}

const COM_ESTADO = ['formulario', 'conversa', 'caixa', 'cores', 'envio', 'opcoes'];
/** Chave estavel do bloco: o que ele digita nao migra para outro quando a lista reordena. Indice so para blocos sem estado. */
export function chaveDoBloco(b: { tipo?: unknown; [k: string]: unknown }, i: number): string {
  if (typeof b?.id === 'string' && b.id) return `id:${b.id}`;
  if (!COM_ESTADO.includes(String(b?.tipo))) return `i:${i}`;
  const extra = b.campo ?? b.destino; // opcoes e envio: o mesmo comando serve campos ou destinos diferentes
  return `${String(b.tipo)}|${String(b.acao ?? b.catalogo ?? '')}|${JSON.stringify(b.dados_fixos ?? b.enviar ?? '')}${extra === undefined ? '' : `|${String(extra)}`}`;
}
/** Chaves de todos os blocos; iguais ganham sufixo para nao colidirem. */
export function chavesDosBlocos(bs: { tipo?: unknown; [k: string]: unknown }[]): string[] {
  const vistas = new Map<string, number>();
  return bs.map((b, i) => {
    const k = chaveDoBloco(b, i);
    const n = vistas.get(k) ?? 0;
    vistas.set(k, n + 1);
    return n ? `${k}#${n}` : k;
  });
}

/** So png e jpeg em base64 (svg pode levar script). */
export const imagemSegura = (uri: unknown): uri is string =>
  typeof uri === 'string' && /^data:image\/(?:png|jpeg);base64,[A-Za-z0-9+/]+={0,2}$/.test(uri);

/** true quando a pessoa esta (quase) no fim da conversa: so ai o fio acompanha as mensagens novas. */
export const estaNoFim = (alturaTotal: number, rolado: number, alturaVisivel: number): boolean => alturaTotal - rolado - alturaVisivel < 40;

export function mensagemDoErro(e: unknown): string {
  if (e instanceof ErroApi) {
    if (e.status === 403 && /^Algo deu errado/.test(e.message)) return 'Você não tem permissão para fazer isso.';
    return e.message;
  }
  return e instanceof Error && e.message ? e.message : 'Algo deu errado.';
}
