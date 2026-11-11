// Logica pura da lista de skills do chat: busca, grupos, escolha (teto de 6) e ids que vao para o servidor.
import type { GrupoHabilidade, Habilidade } from '../../api/tipos';

export const MAX_HABILIDADES = 6;
export const TIPO_ARRASTE = 'application/x-tune-up-habilidade';
export const ID_GRUPO_FIXO = '__tune-up';
export const ID_GRUPO_OUTROS = '__outros';

/** Sem acento e sem maiuscula. */
export function normalizar(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

export function filtrar(habs: Habilidade[], busca: string): Habilidade[] {
  const q = normalizar(busca);
  if (!q) return habs;
  const partes = q.split(/\s+/);
  return habs.filter((h) => {
    const alvo = normalizar(`${h.nome} ${h.titulo} ${h.descricao} ${h.origem}`);
    return partes.every((p) => alvo.includes(p));
  });
}

export type ModoGrupo = 'tema' | 'origem';

export interface GrupoMontado {
  id: string;
  titulo: string;
  fixo: boolean;
  itens: Habilidade[];
}

/** Tune-up (fixas) primeiro; depois os grupos na ordem do servidor. So devolve grupo com item. */
export function agrupar(
  grupos: GrupoHabilidade[],
  habs: Habilidade[],
  busca = '',
  modo: ModoGrupo = 'tema',
): GrupoMontado[] {
  const lista = filtrar(habs, busca);
  const saida: GrupoMontado[] = [];
  const fixas = lista.filter((h) => h.fixa);
  if (fixas.length) saida.push({ id: ID_GRUPO_FIXO, titulo: 'Tune-up (sempre ligado)', fixo: true, itens: fixas });
  if (modo === 'origem') {
    // De onde a skill veio (plugin, suas skills, projeto), em ordem alfabetica.
    const porOrigem = new Map<string, Habilidade[]>();
    for (const h of lista) if (!h.fixa) porOrigem.set(h.origem, [...(porOrigem.get(h.origem) ?? []), h]);
    const nomes = [...porOrigem.keys()].sort((a, b) => normalizar(a).localeCompare(normalizar(b)));
    for (const o of nomes) saida.push({ id: `origem:${o}`, titulo: o, fixo: false, itens: porOrigem.get(o)! });
    return saida;
  }
  const conhecidos = new Set(grupos.map((g) => g.id));
  for (const g of grupos) {
    const itens = lista.filter((h) => !h.fixa && h.grupo === g.id);
    if (itens.length) saida.push({ id: g.id, titulo: g.titulo, fixo: false, itens });
  }
  const soltas = lista.filter((h) => !h.fixa && !conhecidos.has(h.grupo));
  if (soltas.length) saida.push({ id: ID_GRUPO_OUTROS, titulo: 'Outras', fixo: false, itens: soltas });
  return saida;
}

/** Poe ou tira o id. `cheio` = ja tinha o maximo e a skill nao entrou. */
export function alternar(escolhidas: string[], id: string, teto = MAX_HABILIDADES): { ids: string[]; cheio: boolean } {
  if (escolhidas.includes(id)) return { ids: escolhidas.filter((x) => x !== id), cheio: false };
  if (escolhidas.length >= teto) return { ids: escolhidas, cheio: true };
  return { ids: [...escolhidas, id], cheio: false };
}

/** So poe (nunca tira). `cheio` = ja tinha o maximo e a skill nao entrou; ja estar na caixa nao e cheio. */
export function incluir(escolhidas: string[], id: string, teto = MAX_HABILIDADES): { ids: string[]; cheio: boolean } {
  if (escolhidas.includes(id)) return { ids: escolhidas, cheio: false };
  return alternar(escolhidas, id, teto);
}

/** Tira so os ids enviados; o resto (escolhido durante o envio) continua. */
export function tirarEnviados(escolhidas: string[], enviados: string[]): string[] {
  const n = escolhidas.filter((id) => !enviados.includes(id));
  return n.length === escolhidas.length ? escolhidas : n;
}

/** Tira os ids que nao existem mais na lista do servidor. */
export function podarInexistentes(escolhidas: string[], habs: Habilidade[]): string[] {
  const ok = new Set(habs.map((h) => h.id));
  const n = escolhidas.filter((id) => ok.has(id));
  return n.length === escolhidas.length ? escolhidas : n;
}

export const LIMITE_POR_GRUPO = 50;

/** Desenha no maximo `limite` itens; `restam` alimenta o botao "mostrar mais (N)". */
export function fatiar<T>(itens: T[], limite: number): { visiveis: T[]; restam: number } {
  return { visiveis: itens.slice(0, limite), restam: Math.max(0, itens.length - limite) };
}

/** Ids que vao para o servidor: sem repetir, so de skills que existem e nao sao fixas. */
export function idsParaEnviar(escolhidas: string[], habs: Habilidade[]): string[] {
  const ok = new Set(habs.filter((h) => !h.fixa).map((h) => h.id));
  return [...new Set(escolhidas)].filter((id) => ok.has(id)).slice(0, MAX_HABILIDADES);
}

/** Etiquetas da caixa: id + titulo, na ordem da escolha (id que sumiu da lista fica de fora). */
export function etiquetasDe(escolhidas: string[], habs: Habilidade[]): { id: string; titulo: string }[] {
  const porId = new Map(habs.map((h) => [h.id, h]));
  return escolhidas.flatMap((id) => {
    const h = porId.get(id);
    return h && !h.fixa ? [{ id, titulo: h.titulo }] : [];
  });
}
