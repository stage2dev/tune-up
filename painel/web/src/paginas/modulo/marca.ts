// Parte pura dos blocos de marca (cores, envio, previa, opcoes): cor, contraste, fonte e arquivo. Sem React, para testar sem tela.

/** "#abc" ou "#aabbcc" (qualquer caixa) vira "#aabbcc"; outra coisa vira null. O <input type=color> so aceita 6 digitos minusculos. */
export function corHex(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  const s = v.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(s)) return s;
  if (/^#[0-9a-f]{3}$/.test(s)) return `#${s[1]}${s[1]}${s[2]}${s[2]}${s[3]}${s[3]}`;
  return null;
}

function luminancia(hex: string): number {
  const canal = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * canal(1) + 0.7152 * canal(3) + 0.0722 * canal(5);
}

/** Razao de contraste WCAG entre duas cores (1 a 21); null se alguma cor e invalida. */
export function contraste(a: unknown, b: unknown): number | null {
  const x = corHex(a);
  const y = corHex(b);
  if (!x || !y) return null;
  const la = luminancia(x);
  const lb = luminancia(y);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

export const CONTRASTE_MINIMO = 4.5;

/** Texto legivel em cima de `fundo`: preto ou branco, o que tiver mais contraste. */
export const textoSobre = (fundo: string): string => ((contraste(fundo, '#000000') ?? 0) >= (contraste(fundo, '#ffffff') ?? 0) ? '#000000' : '#ffffff');

/** Nome de fonte vira font-family seguro (so letras, numeros, espaco, virgula, hifen e aspas); outra coisa = herda da tela. */
export function fonteSegura(v: unknown): string {
  return typeof v === 'string' && /^[A-Za-z0-9 ,'"-]{1,120}$/.test(v.trim()) ? v.trim() : 'inherit';
}

export const TIPOS_ACEITOS = ['image/png', 'image/jpeg', 'image/webp'];
export const TETO_ENVIO = 8 * 1024 * 1024; // o mesmo teto global do servidor (envio.py)

/** Tamanho em MB para a frase de erro: "8 MB", "1,5 MB". */
const mb = (n: number): string => `${(n / (1024 * 1024)).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB`;

/** Conferencia antes de mandar (o servidor confere de novo pelos bytes). Frase do problema, ou null = pode mandar. */
export function conferirArquivo(a: { name: string; type: string; size: number }, maxBytes?: unknown): string | null {
  const teto = typeof maxBytes === 'number' && maxBytes > 0 ? Math.min(maxBytes, TETO_ENVIO) : TETO_ENVIO;
  if (!TIPOS_ACEITOS.includes(a.type)) return `“${a.name}” não é uma foto aceita. Use PNG, JPG ou WebP.`;
  if (a.size <= 0) return `“${a.name}” está vazio.`;
  if (a.size > teto) return `“${a.name}” é grande demais (${mb(a.size)}). O limite é ${mb(teto)}.`;
  return null;
}

/** Rascunho da aba: o que a pessoa acabou de escolher e o servidor ainda nao devolveu. Chave = campo do comando. */
export interface ValorRascunho { valor: string; fontes?: { titulo: string; texto: string } }
export type Rascunho = Record<string, ValorRascunho>;

export function comRascunho(r: Rascunho, campo: string, v: ValorRascunho): Rascunho {
  return { ...r, [campo]: v };
}
export function semRascunho(r: Rascunho, campo: string): Rascunho {
  if (!(campo in r)) return r;
  const out = { ...r };
  delete out[campo];
  return out;
}

export const PAPEIS = ['fundo', 'texto', 'principal', 'destaque', 'superficie'] as const;
export type Papel = (typeof PAPEIS)[number];
export interface VistaPrevia { cores: Record<Papel, string>; fontes: { titulo: string; texto: string } }

/**
 * Cores e letras da previa: o que o modulo mandou, trocado pelo rascunho do campo ligado (`campos`), na hora.
 * Cor invalida cai num padrao legivel; superficie sem valor usa o fundo.
 */
export function vistaDaPrevia(b: Record<string, unknown>, r: Rascunho): VistaPrevia {
  const c = b.cores && typeof b.cores === 'object' ? (b.cores as Record<string, unknown>) : {};
  const f = b.fontes && typeof b.fontes === 'object' ? (b.fontes as Record<string, unknown>) : {};
  const ligados = b.campos && typeof b.campos === 'object' ? (b.campos as Record<string, unknown>) : {};
  const doRascunho = (papel: string): ValorRascunho | undefined => (typeof ligados[papel] === 'string' ? r[ligados[papel] as string] : undefined);
  const padrao: Record<Papel, string> = { fundo: '#ffffff', texto: '#1a1a1a', principal: '#333333', destaque: '#555555', superficie: '' };
  const cores = {} as Record<Papel, string>;
  for (const p of PAPEIS) cores[p] = corHex(doRascunho(p)?.valor) ?? corHex(c[p]) ?? padrao[p];
  if (!cores.superficie) cores.superficie = cores.fundo;
  const letras = doRascunho('letras')?.fontes;
  return {
    cores,
    fontes: { titulo: fonteSegura(letras?.titulo ?? f.titulo), texto: fonteSegura(letras?.texto ?? f.texto) },
  };
}
