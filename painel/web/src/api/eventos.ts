// Busca dos eventos de uma execucao em pedacos. O servidor devolve no maximo um
// pedaco por pedido (300 eventos ou 4 MB), entao uma execucao longa precisa de
// varios pedidos ate chegar ao fim do arquivo.
import type { Eventos } from './tipos';

/** Eventos guardados no cache. `incompleto` = parou no teto de pedidos e ainda pode faltar o fim. */
export type EventosCache = Eventos & { incompleto?: boolean };

/** Teto de pedidos seguidos numa busca, para nao travar a tela num arquivo enorme. */
export const MAX_PEDIDOS = 25;

const FINAIS = new Set(['terminou', 'parada', 'sumiu']);

export const estadoFinal = (estado: string | undefined) => !!estado && FINAIS.has(estado);

/**
 * Pede pedacos (desde=proximo) e junta com o que ja havia ate o `proximo` parar
 * de andar. Com a execucao ainda rodando, para no primeiro pedaco vazio.
 */
export async function buscarEventos(
  buscar: (desde: number) => Promise<Eventos>,
  antes: EventosCache | undefined,
  maxPedidos = MAX_PEDIDOS,
): Promise<EventosCache> {
  let desde = antes?.proximo ?? 0;
  const eventos = [...(antes?.eventos ?? [])];
  let ultimo: Eventos | undefined;
  for (let i = 0; i < maxPedidos; i++) {
    const novo = await buscar(desde);
    ultimo = novo;
    eventos.push(...novo.eventos);
    const andou = novo.proximo > desde;
    desde = novo.proximo;
    if (!andou) return { ...novo, eventos, proximo: desde, incompleto: false };
  }
  // Bateu no teto: o proximo ciclo continua de onde parou.
  return { ...(ultimo as Eventos), eventos, proximo: desde, incompleto: true };
}

/** Intervalo de nova busca: continua enquanto roda ou enquanto faltar o fim. */
export function intervaloEventos(dados: EventosCache | undefined): number | false {
  if (!dados) return 2000;
  if (dados.incompleto) return 300;
  return estadoFinal(dados.estado) ? false : 2000;
}
