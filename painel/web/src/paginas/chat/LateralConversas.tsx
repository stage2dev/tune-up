// Coluna de conversas: "Nova conversa" e as execucoes do grupo chat, a aberta marcada.
import { Link } from 'react-router';
import { Plus } from 'lucide-react';
import { useExecucoes } from '../../api/ganchos';
import type { Acao } from '../../api/tipos';
import { Erro, Esqueleto, PontoStatus } from '../../componentes';
import { comecoDoPedido, conversasDoChat } from './logica';

const quando = (iso: string): string => {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? '' : new Date(t).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

const ROTULO: Record<string, string> = { rodando: 'rodando', precisa_de_voce: 'precisa de você', terminou: 'terminou', parada: 'parada', sumiu: 'sumiu' };

export function LateralConversas({ atual, niveis }: { atual: string | undefined; niveis: Acao[] }) {
  const q = useExecucoes();
  const tituloDo = (acao: string, padrao: string) => niveis.find((a) => a.id === acao)?.titulo ?? padrao;

  let corpo;
  if (q.isPending) {
    corpo = (
      <div role="status" aria-label="Carregando conversas" className="grid gap-2">
        <span className="sr-only">Carregando…</span>
        {[0, 1, 2].map((i) => (
          <div key={i} className="grid gap-1.5 p-2">
            <Esqueleto className="h-3.5 w-5/6" />
            <Esqueleto className="h-3 w-1/2" />
          </div>
        ))}
      </div>
    );
  } else if (q.isError) {
    corpo = <Erro erro={q.error} aoTentar={() => void q.refetch()} />;
  } else {
    const lista = conversasDoChat(q.data);
    corpo =
      lista.length === 0 ? (
        <p className="text-xs text-[var(--color-text-secondary)] px-2 py-4">Nenhuma conversa ainda. Elas aparecem aqui.</p>
      ) : (
        <ul className="grid gap-0.5">
          {lista.map((e) => {
            const marcada = e.id === atual;
            return (
              <li key={e.id}>
                <Link
                  to={`/conversa/${encodeURIComponent(e.id)}`}
                  aria-current={marcada ? 'page' : undefined}
                  className={`grid gap-0.5 rounded-lg px-2 py-1.5 transition-colors ${
                    marcada ? 'bg-[var(--color-accent-subtle)]' : 'hover:bg-[var(--color-bg-tertiary)]'
                  }`}
                >
                  <span className={`text-sm truncate ${marcada ? 'font-medium text-[var(--color-accent)]' : ''}`}>{comecoDoPedido(e.params?.pedido, 60) || e.titulo}</span>
                  <span className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] min-w-0">
                    <PontoStatus estado={e.estado} />
                    <span className="sr-only">{ROTULO[e.estado] ?? e.estado}, </span>
                    <span className="truncate">{tituloDo(e.acao, e.titulo)} · {quando(e.iniciada_em)}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      );
  }

  return (
    <div className="grid gap-3 content-start">
      <Link
        to="/"
        className="inline-flex items-center justify-center gap-2 h-9 px-3 rounded-lg bg-[var(--color-accent)] text-[var(--color-on-accent)] hover:bg-[var(--color-accent-hover)] text-sm font-medium"
      >
        <Plus size={14} aria-hidden="true" />
        Nova conversa
      </Link>
      {corpo}
    </div>
  );
}
