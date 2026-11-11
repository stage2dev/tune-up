// Parte pura do bloco "caixa" (caixa de entrada) e das mensagens da conversa. Sem React: testado em entrada.test.ts.
import { itens, textoOuNada } from './interativos';
import { lerData } from './formato';

export interface LinhaCaixa {
  id: string;
  titulo: string;
  detalhe?: string;
  quando?: string;
  selo?: { texto: string; tom: string };
  naoLidas: number;
  ativa: boolean;
}

const objeto = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});

/** Linhas validas da caixa (id e titulo em texto); o resto e ignorado. */
export function lerConversas(v: unknown): LinhaCaixa[] {
  return itens(v)
    .filter((c) => typeof c.id === 'string' && c.id && typeof c.titulo === 'string')
    .map((c) => {
      const selo = objeto(c.selo);
      const n = typeof c.nao_lidas === 'number' && Number.isFinite(c.nao_lidas) ? Math.max(0, Math.floor(c.nao_lidas)) : 0;
      return {
        id: String(c.id), titulo: String(c.titulo), detalhe: textoOuNada(c.detalhe), quando: textoOuNada(c.quando),
        selo: textoOuNada(selo.texto) ? { texto: String(selo.texto), tom: String(selo.tom ?? 'neutro') } : undefined,
        naoLidas: n, ativa: c.ativa === true,
      };
    });
}

const sem = (t: string) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
/** Filtro da busca no navegador: titulo ou previa, sem diferenciar acento e maiuscula. */
export function filtrarConversas(linhas: LinhaCaixa[], busca: string): LinhaCaixa[] {
  const b = sem(busca.trim());
  if (!b) return linhas;
  return linhas.filter((l) => sem(`${l.titulo} ${l.detalhe ?? ''}`).includes(b));
}

/** Clique numa linha: { acao, dados: { ...dados_fixos, conversa_id } }. null se o bloco nao diz a acao. */
export function pedidoDaLinha(abrir: unknown, id: string): { acao: string; dados: Record<string, unknown> } | null {
  const a = objeto(abrir);
  const acao = textoOuNada(a.acao);
  return acao ? { acao, dados: { ...objeto(a.dados_fixos), conversa_id: id } } : null;
}

const dois = (n: number) => String(n).padStart(2, '0');
const meiaNoite = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
const diasEntre = (d: Date, agora: Date) => Math.round((meiaNoite(agora) - meiaNoite(d)) / 86_400_000);

/** Hora da linha: "agora", "5 min", "14:32" (hoje), "ontem", "09/11". Vazio se a data nao serve. */
export function quandoCurto(texto: string | undefined, agora: Date = new Date()): string {
  const d = lerData(texto);
  if (!d) return '';
  const min = Math.floor((agora.getTime() - d.getTime()) / 60_000);
  if (min >= 0 && min < 1) return 'agora';
  if (min >= 1 && min < 60) return `${min} min`;
  const dias = diasEntre(d, agora);
  if (dias <= 0) return `${dois(d.getHours())}:${dois(d.getMinutes())}`;
  if (dias === 1) return 'ontem';
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)}`;
}

/** Hora do balao ("14:32"). */
export function horaDaMensagem(texto: unknown): string {
  const d = typeof texto === 'string' ? lerData(texto) : null;
  return d ? `${dois(d.getHours())}:${dois(d.getMinutes())}` : '';
}

/** Rotulo do separador de dia: "Hoje", "Ontem" ou "09/11/2026". */
export function rotuloDoDia(d: Date, agora: Date = new Date()): string {
  const n = diasEntre(d, agora);
  if (n === 0) return 'Hoje';
  if (n === 1) return 'Ontem';
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export type ItemFio = { dia: string; chave: string } | { mensagem: Record<string, unknown>; chave: string };
/** Mensagens com um separador antes de cada dia novo. Mensagem sem data fica no dia da anterior. */
export function fioComDias(mensagens: Record<string, unknown>[], agora: Date = new Date()): ItemFio[] {
  const out: ItemFio[] = [];
  let ultimo = '';
  mensagens.forEach((m, k) => {
    const d = typeof m.quando === 'string' ? lerData(m.quando) : null;
    if (d) {
      const dia = rotuloDoDia(d, agora);
      if (dia !== ultimo) { out.push({ dia, chave: `dia:${dia}:${k}` }); ultimo = dia; }
    }
    out.push({ mensagem: m, chave: typeof m.id === 'string' && m.id ? m.id : `i:${k}` });
  });
  return out;
}

const TIPOS: Record<string, string> = {
  audio: 'Áudio – ouça no celular',
  imagem: 'Imagem – veja no celular',
  documento: 'Documento – abra no celular',
  outro: 'Mensagem sem texto – veja no celular',
};
/** Etiqueta da mensagem que nao e texto; undefined para texto (ou tipo ausente/desconhecido). */
export const rotuloDoTipo = (tipo: unknown): string | undefined => (typeof tipo === 'string' ? TIPOS[tipo] : undefined);

/** Texto que acompanha uma mensagem nao textual: some quando e so o marcador "[audio]". */
export function legendaDe(texto: unknown): string | undefined {
  const t = textoOuNada(texto);
  return t && !/^\s*\[[^\]]*\]\s*$/.test(t) ? t : undefined;
}

/** Contador da aba: inteiro positivo, senao nada. */
export const alertaDaAba = (v: unknown): number | undefined =>
  typeof v === 'number' && Number.isFinite(v) && v >= 1 ? Math.floor(v) : undefined;
