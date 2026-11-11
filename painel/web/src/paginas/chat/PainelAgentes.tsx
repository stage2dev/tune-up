// "Quem esta trabalhando" da conversa aberta: GET /api/agentes?sessao=<id>&todos=1.
// Atualiza a cada 3 s enquanto a conversa roda; quando para, busca uma ultima vez e fica o retrato final.
import { useEffect, useRef } from 'react';
import { Bot } from 'lucide-react';
import { useAgentesDaSessao } from '../../api/agentes';
import { useExecucoes } from '../../api/ganchos';
import { Botao, Esqueleto, Selo } from '../../componentes';
import { useAgora } from '../dev/useAgora';
import { NoAgente } from '../agentes/NoAgente';
import { ChipModelo, MedidorEsforco, PontoAgente } from '../agentes/pecas';
import { plural, seloSessao } from '../agentes/logica';
import '../agentes/agentes.css';
import { itensDoPainel, sessaoDaConversa } from './agentesChat';

export function PainelAgentes({ id }: { id: string }) {
  const execs = useExecucoes();
  const exec = execs.data?.find((e) => e.id === id);
  const ativa = exec ? exec.estado === 'rodando' || exec.estado === 'precisa_de_voce' : false;
  const q = useAgentesDaSessao(id, ativa);
  const agora = useAgora(ativa);

  // Acabou de parar: uma busca final para o retrato ficar certo.
  const antes = useRef(ativa);
  const refazer = q.refetch;
  useEffect(() => {
    if (antes.current && !ativa) void refazer();
    antes.current = ativa;
  }, [ativa, refazer]);

  if (q.isPending) {
    return (
      <div role="status" aria-label="Carregando quem está trabalhando" className="grid gap-2">
        <span className="sr-only">Carregando…</span>
        <Esqueleto className="h-4 w-1/2" />
        <Esqueleto className="h-14 w-full" />
        <Esqueleto className="h-14 w-full" />
      </div>
    );
  }
  if (q.isError) {
    return (
      <div role="alert" className="text-xs text-[var(--color-text-secondary)] grid gap-2">
        <p className="break-words">Não consegui ver quem está trabalhando. {q.error instanceof Error ? q.error.message : ''}</p>
        <div>
          <Botao variante="secundario" className="h-8" onClick={() => void q.refetch()}>
            Tentar de novo
          </Botao>
        </div>
      </div>
    );
  }

  const s = sessaoDaConversa(q.data, id);
  const itens = itensDoPainel(s);
  return (
    <div className="grid gap-3 content-start">
      <h2 className="text-sm font-semibold flex items-center gap-2">
        <Bot size={16} aria-hidden="true" className="text-[var(--color-accent)]" />
        Quem está trabalhando
      </h2>
      {s ? (
        <div className="rounded-lg border border-[var(--color-border)] p-2.5 grid gap-1.5">
          <div className="flex items-center gap-2 min-w-0">
            <PontoAgente rodando={s.estado === 'rodando'} />
            <p className="flex-1 min-w-0 text-sm font-medium truncate">Claude principal</p>
            <Selo estado={s.estado} {...seloSessao(s.estado)} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ChipModelo modelo={s.modelo} />
            <MedidorEsforco esforco={s.esforco} />
          </div>
        </div>
      ) : (
        <p className="text-xs text-[var(--color-text-secondary)]">A sessão ainda não apareceu. Isso é normal nos primeiros segundos.</p>
      )}
      {s && itens.total === 0 && <p className="text-xs text-[var(--color-text-secondary)]">Só o Claude principal está trabalhando.</p>}
      {itens.total > 0 && (
        <p className="text-xs text-[var(--color-text-secondary)]" aria-live="polite">
          {plural(itens.total, 'ajudante', 'ajudantes')}
          {itens.ativos > 0 ? ` · ${itens.ativos} trabalhando agora` : ''}
        </p>
      )}
      {itens.blocos.map((b) => (
        <div key={b.chave} className="grid gap-1">
          {b.titulo && <p className="text-xs font-semibold text-[var(--color-text-secondary)]">{b.titulo}</p>}
          {b.fases.map((f, i) => (
            <div key={f.fase ?? i} className="grid gap-0.5">
              {f.fase && <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-tertiary)]">{f.fase}</p>}
              <ul className="ag-arvore">
                {f.arvore.map((n) => <NoAgente key={n.agente.id} no={n} agora={agora} />)}
              </ul>
            </div>
          ))}
        </div>
      ))}
      {(q.data?.avisos.length ?? 0) > 0 && (
        <details className="text-xs text-[var(--color-text-tertiary)]">
          <summary className="cursor-pointer">Avisos da leitura</summary>
          <ul className="mt-1 grid gap-1 list-disc pl-4">
            {q.data?.avisos.map((a, i) => <li key={i} className="break-words">{a}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
