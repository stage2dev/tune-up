// Funcoes puras de texto para as telas de modulo e de Acompanhamento (testadas em formato.test.ts).

/** Mensagem de campo sem dado: nunca mostramos zero no lugar de "nao li". */
export const SEM_DADO = 'sem dado';

const MS_DIA = 86_400_000;

/** Converte "AAAA-MM-DD" (meia-noite local), ISO local ou ISO com fuso em Date. null se nao entender. */
export function lerData(texto: string | null | undefined): Date | null {
  if (!texto) return null;
  const solto = /^(\d{4})-(\d{2})-(\d{2})$/.exec(texto);
  if (solto) {
    const d = new Date(Number(solto[1]), Number(solto[2]) - 1, Number(solto[3]));
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(texto);
  return Number.isNaN(d.getTime()) ? null : d;
}

function meiaNoite(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Quantos dias de calendario se passaram (0 = hoje). null se a data nao serve. Futuro vira 0. */
export function diasDesde(texto: string | null | undefined, agora: Date = new Date()): number | null {
  const d = lerData(texto);
  if (!d) return null;
  return Math.max(0, Math.round((meiaNoite(agora) - meiaNoite(d)) / MS_DIA));
}

export function textoDias(n: number | null): string {
  if (n === null) return SEM_DADO;
  if (n === 0) return 'hoje';
  if (n === 1) return 'ontem';
  return `há ${n} dias`;
}

/** "há 3 dias" a partir de uma data. */
export function ha(texto: string | null | undefined, agora: Date = new Date()): string {
  return textoDias(diasDesde(texto, agora));
}

/** "atualizado há 3 dias" / "atualizado hoje". */
export function atualizadoHa(texto: string | null | undefined, agora: Date = new Date()): string {
  const n = diasDesde(texto, agora);
  if (n === null) return 'atualização sem data';
  return `atualizado ${textoDias(n)}`;
}

/** "09/11" ou "09/11/2026" (com ano). */
export function dataCurta(texto: string | null | undefined, comAno = false): string {
  const d = lerData(texto);
  if (!d) return SEM_DADO;
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return comAno ? `${dd}/${mm}/${d.getFullYear()}` : `${dd}/${mm}`;
}

export function dataHora(texto: string | null | undefined): string {
  const d = lerData(texto);
  if (!d) return SEM_DADO;
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${dataCurta(texto)} às ${hh}:${mi}`;
}

export function numero(v: number | null | undefined, casas = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return SEM_DADO;
  return v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export function reais(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return SEM_DADO;
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

export function porcento(v: number | null | undefined, casas = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return SEM_DADO;
  return `${numero(v, casas)}%`;
}

export function plural(n: number, um: string, varios: string): string {
  return n === 1 ? `${n} ${um}` : `${n} ${varios}`;
}

/** So deixa passar link http(s); o resto (caminho de arquivo, javascript:) nao vira <a>. */
export function linkSeguro(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.href : null;
  } catch {
    return null;
  }
}

/** Ultimos dois pedacos de um caminho local, para mostrar sem despejar a pasta inteira. */
export function caminhoCurto(caminho: string): string {
  const partes = caminho.split('/').filter(Boolean);
  return partes.slice(-2).join('/');
}

/** Corta texto longo com reticencias. */
export function cortar(texto: string, max: number): string {
  return texto.length <= max ? texto : `${texto.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}
