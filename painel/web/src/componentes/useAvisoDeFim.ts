// Avisa (toast) quando uma execucao muda de estado: terminou, parou, sumiu ou precisa de voce.
// Fica no Layout, entao funciona em qualquer tela. Nunca avisa na primeira carga.
// Conversa do chat ganha o botao "Abrir a conversa" (vai para /conversa/:id); os outros grupos seguem sem botao.
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { useExecucoes } from '../api/ganchos';
import type { EstadoExecucao } from '../api/tipos';
import { useAvisos } from './Avisos';
import { GRUPO_CHAT, grupoDe } from '../paginas/chat/logica';

export function useAvisoDeFim(): void {
  const { data } = useExecucoes();
  const { avisar } = useAvisos();
  const ir = useNavigate();
  const vistas = useRef<Map<string, EstadoExecucao> | null>(null);

  useEffect(() => {
    if (!data) return;
    const atual = new Map(data.map((e) => [e.id, e.estado] as const));
    const antes = vistas.current;
    vistas.current = atual; // a primeira carga so memoriza
    if (!antes) return;
    for (const e of data) {
      const ant = antes.get(e.id);
      if (ant === e.estado || ant === undefined) continue;
      const para = `/conversa/${encodeURIComponent(e.id)}`;
      const acao = grupoDe(e) === GRUPO_CHAT ? { rotulo: 'Abrir a conversa', aoClicar: () => ir(para) } : undefined;
      if (e.estado === 'terminou') avisar({ tipo: 'sucesso', titulo: 'Terminou', texto: e.titulo, acao });
      else if (e.estado === 'precisa_de_voce') avisar({ tipo: 'atencao', titulo: 'Precisa de você', texto: e.titulo, duracao: 0, acao });
      else if (e.estado === 'sumiu') avisar({ tipo: 'erro', titulo: 'A sessão sumiu', texto: e.titulo, acao });
      else if (e.estado === 'parada') avisar({ tipo: 'info', titulo: 'Parada', texto: e.titulo, acao });
    }
  }, [data, avisar, ir]);
}
