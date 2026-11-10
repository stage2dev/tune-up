// Tela "Agentes": sessoes do Claude rodando neste projeto e os sub-agentes de cada uma, ao vivo.
import { useCallback, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useAgentes } from '../../api/agentes';
import { Erro, EsqueletoPagina, Pagina } from '../../componentes';
import { useAgora } from '../dev/useAgora';
import type { Recolhimento } from './CartaoSessao';
import { sessaoAtiva } from './logica';
import { VisaoAgentes } from './VisaoAgentes';
import './agentes.css';

const SUBTITULO = 'Cada instância do Claude neste projeto e os agentes que ela abriu, com modelo e esforço. Atualiza a cada 2 s.';

function Filtro({ todos, aoTrocar }: { todos: boolean; aoTrocar: (t: boolean) => void }) {
  const opcao = (valor: boolean, texto: string) => (
    <button
      type="button"
      aria-pressed={todos === valor}
      onClick={() => aoTrocar(valor)}
      className={`h-8 px-3 rounded-md text-sm font-medium transition-colors ${
        todos === valor ? 'bg-[var(--color-surface)] text-[var(--color-text)] shadow-[var(--shadow-sm)]' : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text)]'
      }`}
    >
      {texto}
    </button>
  );
  return (
    <div role="group" aria-label="O que mostrar" className="inline-flex gap-0.5 p-0.5 rounded-lg bg-[var(--color-bg-tertiary)]">
      {opcao(false, 'Só ativos')}
      {opcao(true, 'Todos')}
    </div>
  );
}

export default function Agentes() {
  const [todos, setTodos] = useState(false);
  const q = useAgentes(todos);
  const [recolhidos, setRecolhidos] = useState<ReadonlySet<string>>(() => new Set());

  const alternar = useCallback((chave: string) => {
    setRecolhidos((atual) => {
      const novo = new Set(atual);
      if (novo.has(chave)) novo.delete(chave);
      else novo.add(chave);
      return novo;
    });
  }, []);
  const rec = useMemo<Recolhimento>(() => ({ recolhido: (c) => recolhidos.has(c), alternar }), [recolhidos, alternar]);

  const algoRodando = !!q.data?.sessoes.some((s) => sessaoAtiva(s) || s.agentes_ativos > 0);
  const agora = useAgora(algoRodando);

  const acoes = <Filtro todos={todos} aoTrocar={setTodos} />;

  if (q.isPending) return <Pagina titulo="Agentes" subtitulo={SUBTITULO} acoes={acoes}><EsqueletoPagina cartoes={3} /></Pagina>;
  if (!q.data) return <Pagina titulo="Agentes" subtitulo={SUBTITULO} acoes={acoes}><Erro erro={q.error} aoTentar={() => void q.refetch()} /></Pagina>;

  return (
    <Pagina titulo="Agentes" subtitulo={SUBTITULO} acoes={acoes}>
      <div className="grid gap-3">
        {q.isError && (
          <div role="status" className="flex flex-wrap items-center gap-2 text-xs rounded-lg px-3 py-2 bg-[var(--color-attention-subtle)]">
            <span className="flex-1 min-w-0">Não consegui atualizar agora; mostrando o último retrato. {q.error instanceof Error ? q.error.message : ''}</span>
            <button type="button" onClick={() => void q.refetch()} className="inline-flex items-center gap-1 font-medium hover:underline">
              <RefreshCw size={12} aria-hidden="true" /> Tentar de novo
            </button>
          </div>
        )}
        {q.isPlaceholderData && <p role="status" className="text-xs text-[var(--color-text-secondary)]">Buscando {todos ? 'todos os agentes' : 'só os ativos'}…</p>}
        <VisaoAgentes dados={q.data} agora={agora} rec={rec} todos={todos} />
      </div>
    </Pagina>
  );
}
