// Conversas anteriores do chat (execucoes do grupo chat), mais novas primeiro.
import { Link } from 'react-router';
import { ChevronRight, MessageSquare } from 'lucide-react';
import { useExecucoes } from '../../api/ganchos';
import type { Acao } from '../../api/tipos';
import { Cartao, Erro, Esqueleto, EstadoVazio, Selo } from '../../componentes';
import { comecoDoPedido, conversasDoChat, destinoDaExecucao } from './logica';

const quando = (iso: string): string => {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? '' : new Date(t).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

export function ListaConversas({ niveis }: { niveis: Acao[] }) {
  const q = useExecucoes();
  const tituloDo = (acao: string, padrao: string) => niveis.find((a) => a.id === acao)?.titulo ?? padrao;

  let corpo;
  if (q.isPending) {
    corpo = (
      <div role="status" aria-label="Carregando conversas" className="grid gap-2">
        <span className="sr-only">Carregando…</span>
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-lg border border-[var(--color-border)] p-3 grid gap-2">
            <Esqueleto className="h-4 w-2/3" />
            <Esqueleto className="h-3 w-1/3" />
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
        <EstadoVazio titulo="Nenhuma conversa ainda" texto="Escreva o que você quer na caixa acima. A conversa aparece aqui." />
      ) : (
        <ul className="grid gap-2">
          {lista.map((e) => (
            <li key={e.id}>
              <Link
                to={destinoDaExecucao(e)}
                className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 hover:bg-[var(--color-bg-tertiary)] transition-colors"
              >
                <div className="flex-1 min-w-0 grid gap-1">
                  <p className="text-sm font-medium truncate">{comecoDoPedido(e.params?.pedido) || e.titulo}</p>
                  <p className="text-xs text-[var(--color-text-secondary)] truncate">
                    {tituloDo(e.acao, e.titulo)} · {quando(e.iniciada_em)}
                  </p>
                </div>
                <Selo estado={e.estado} />
                <ChevronRight size={16} aria-hidden="true" className="text-[var(--color-text-tertiary)] shrink-0" />
              </Link>
            </li>
          ))}
        </ul>
      );
  }

  return (
    <Cartao titulo="Conversas" icone={<MessageSquare size={16} aria-hidden="true" />}>
      {corpo}
    </Cartao>
  );
}
