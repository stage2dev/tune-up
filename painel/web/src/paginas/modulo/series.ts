// Prepara as series de um bloco "serie" para o grafico de linha. Valor nulo continua nulo (linha quebrada), nunca vira zero.
import { dataCurta } from './formato';

export interface PontoEntrada {
  x: string;
  y: number | null;
}
export interface SerieEntrada {
  nome: string;
  pontos: PontoEntrada[];
}
export interface LinhaGrafico {
  [campo: string]: number | string | null;
}
export interface SerieMontada {
  /** Uma linha por data, com as chaves s0, s1... (uma por serie). */
  linhas: LinhaGrafico[];
  campos: Array<{ campo: string; nome: string }>;
  /** Quantas datas tem numero em pelo menos uma serie. */
  comDado: number;
}

export function montarSeries(series: SerieEntrada[]): SerieMontada {
  const validas = series.filter((s) => s && Array.isArray(s.pontos));
  const porData = new Map<string, LinhaGrafico>();
  validas.forEach((s, i) => {
    for (const p of s.pontos) {
      if (!p || typeof p.x !== 'string') continue;
      const linha = porData.get(p.x) ?? { data: p.x, rotulo: dataCurta(p.x) };
      linha[`s${i}`] = typeof p.y === 'number' && Number.isFinite(p.y) ? p.y : null;
      porData.set(p.x, linha);
    }
  });
  const linhas = [...porData.values()].sort((a, b) => String(a.data).localeCompare(String(b.data)));
  const campos = validas
    .map((s, i) => ({ campo: `s${i}`, nome: s.nome }))
    .filter((c) => linhas.some((l) => typeof l[c.campo] === 'number'));
  const comDado = linhas.filter((l) => campos.some((c) => typeof l[c.campo] === 'number')).length;
  return { linhas, campos, comDado };
}
