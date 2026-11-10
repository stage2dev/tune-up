import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import { useExecucoes } from '../../api/ganchos';
import { Cartao, Erro, EsqueletoPagina, EstadoVazio, Pagina, Selo } from '../../componentes';
import { useAgora } from './useAgora';
import { emAndamento, tempoDecorrido } from './logica';
import type { Execucao } from '../../api/tipos';
import { destinoDaExecucao } from '../chat/logica';

function Linha({ e, agora }: { e: Execucao; agora: number }) {
  return (
    <li>
      <Link
        to={destinoDaExecucao(e)}
        className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 hover:bg-[var(--color-bg-tertiary)] transition-colors"
      >
        <div className="flex-1 min-w-0 grid grid-cols-1 gap-1">
          <p className="text-sm font-medium truncate">{e.titulo}</p>
          <p className="text-xs text-[var(--color-text-secondary)] truncate">
            {e.nome}{(e.grupo ?? e.area) === 'dev' ? ' · Desenvolvimento' : ''}
          </p>
        </div>
        <div className="text-right grid grid-cols-1 gap-1 justify-items-end shrink-0">
          <Selo estado={e.estado} />
          <span className="text-xs text-[var(--color-text-secondary)]">{emAndamento(e) ? tempoDecorrido(e.iniciada_em, agora) : new Date(e.iniciada_em).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
        </div>
        <ChevronRight size={16} aria-hidden="true" className="text-[var(--color-text-tertiary)] shrink-0" />
      </Link>
    </li>
  );
}

export default function Execucoes() {
  const q = useExecucoes(); // a cada 3 s (o Layout ja usa o mesmo gancho)
  const agora = useAgora(!!q.data?.some(emAndamento));

  if (q.isPending) return <Pagina titulo="Execuções"><EsqueletoPagina /></Pagina>;
  if (q.isError) return <Pagina titulo="Execuções"><Erro erro={q.error} aoTentar={() => void q.refetch()} /></Pagina>;

  const andando = q.data.filter(emAndamento);
  const resto = q.data.filter((e) => !emAndamento(e));
  return (
    <Pagina titulo="Execuções" subtitulo="Sessões do Claude que o painel colocou para trabalhar em segundo plano.">
      {q.data.length === 0 ? (
        <EstadoVazio titulo="Nenhuma execução ainda" texto="Quando você rodar uma Parte ou uma ação, ela aparece aqui." />
      ) : (
        <div className="grid grid-cols-1 gap-5">
          {andando.length > 0 && (
            <Cartao titulo={`Em andamento (${andando.length})`}>
              <ul className="grid grid-cols-1 gap-2">{andando.map((e) => <Linha key={e.id} e={e} agora={agora} />)}</ul>
            </Cartao>
          )}
          {resto.length > 0 && (
            <Cartao titulo={`Anteriores (${resto.length})`}>
              <ul className="grid grid-cols-1 gap-2">{resto.map((e) => <Linha key={e.id} e={e} agora={agora} />)}</ul>
            </Cartao>
          )}
        </div>
      )}
    </Pagina>
  );
}
