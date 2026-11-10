import { describe, expect, it } from 'vitest';
import { buscarEventos, intervaloEventos } from './eventos';
import type { Eventos, EventoExecucao } from './tipos';

// Servidor falso: 1000 eventos, devolve no maximo 300 por pedido, execucao ja terminada.
function servidor(total: number, porPedido = 300, estado: Eventos['estado'] = 'terminou') {
  const pedidos: number[] = [];
  const buscar = async (desde: number): Promise<Eventos> => {
    pedidos.push(desde);
    const fim = Math.min(total, desde + porPedido);
    const eventos: EventoExecucao[] = [];
    for (let n = desde; n < fim; n++) eventos.push({ n, ts: '2026-11-10T10:00:00Z', tipo: 'assistente', texto: `passo ${n}` });
    return { eventos, proximo: fim, estado };
  };
  return { buscar, pedidos };
}

describe('buscarEventos', () => {
  it('execucao terminada com 1000 eventos chega ate o fim', async () => {
    const s = servidor(1000);
    const r = await buscarEventos(s.buscar, undefined);
    expect(r.eventos).toHaveLength(1000);
    expect(r.eventos.at(-1)?.texto).toBe('passo 999');
    expect(r.proximo).toBe(1000);
    expect(r.incompleto).toBe(false);
    expect(intervaloEventos(r)).toBe(false);
    expect(s.pedidos).toEqual([0, 300, 600, 900, 1000]);
  });

  it('continua do cache sem repetir eventos', async () => {
    const s = servidor(500);
    const antes = await buscarEventos(s.buscar, undefined, 1);
    expect(antes.eventos).toHaveLength(300);
    expect(antes.incompleto).toBe(true);
    expect(intervaloEventos(antes)).not.toBe(false);
    const r = await buscarEventos(s.buscar, antes);
    expect(r.eventos.map((e) => e.n)).toEqual(Array.from({ length: 500 }, (_, i) => i));
    expect(r.incompleto).toBe(false);
  });

  it('para no teto de pedidos e marca incompleto', async () => {
    const s = servidor(10_000, 10);
    const r = await buscarEventos(s.buscar, undefined, 3);
    expect(s.pedidos).toHaveLength(3);
    expect(r.eventos).toHaveLength(30);
    expect(r.incompleto).toBe(true);
    expect(intervaloEventos(r)).toBe(300);
  });

  it('rodando: segue buscando a cada 2 s', async () => {
    const s = servidor(5, 300, 'rodando');
    const r = await buscarEventos(s.buscar, undefined);
    expect(r.eventos).toHaveLength(5);
    expect(intervaloEventos(r)).toBe(2000);
  });
});
