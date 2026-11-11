// Aba "Skills": busca, grupos recolhiveis e a lista. Clique (ou Enter/Espaco) poe/tira a skill do pedido;
// arrastar para a caixa faz o mesmo. Tune-up fica no topo, sempre ligado, sem clique.
import { useDeferredValue, useMemo, useState } from 'react';
import { ChevronRight, Lock } from 'lucide-react';
import { useHabilidades } from '../../api/ganchos';
import { ErroApi } from '../../api/cliente';
import type { Habilidade } from '../../api/tipos';
import { Erro, Esqueleto } from '../../componentes';
import { agrupar, fatiar, LIMITE_POR_GRUPO, TIPO_ARRASTE, type ModoGrupo } from './habilidades';
import type { SkillsDoPedido } from './useSkillsDoPedido';

function ItemSkill({ h, marcada, bloqueada, aoAlternar }: { h: Habilidade; marcada: boolean; bloqueada: boolean; aoAlternar: () => void }) {
  const corpo = (
    <>
      <span className="flex items-center gap-1.5 min-w-0">
        <span className={`text-sm truncate ${marcada ? 'font-medium text-[var(--color-accent)]' : ''}`}>{h.titulo}</span>
        {!h.listada && (
          <span title="O Claude lê esta skill só quando você escolhe" className="shrink-0 rounded border border-[var(--color-border)] px-1 text-[10px] text-[var(--color-text-tertiary)]">
            fora da lista
          </span>
        )}
      </span>
      <span className="text-[10px] text-[var(--color-text-tertiary)] truncate">{h.origem}</span>
      {h.descricao && (
        <span title={h.descricao} className="text-xs text-[var(--color-text-secondary)] truncate">
          {h.descricao}
        </span>
      )}
    </>
  );
  if (h.fixa) return <li className="grid gap-0.5 rounded-lg px-2 py-1.5 min-w-0">{corpo}</li>;
  if (bloqueada) return <li className="grid gap-0.5 rounded-lg px-2 py-1.5 min-w-0 opacity-60">{corpo}</li>;
  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        aria-pressed={marcada}
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData(TIPO_ARRASTE, h.id);
          e.dataTransfer.effectAllowed = 'copy';
        }}
        onClick={aoAlternar}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            aoAlternar();
          }
        }}
        className={`grid gap-0.5 rounded-lg px-2 py-1.5 min-w-0 cursor-pointer transition-colors ${
          marcada ? 'bg-[var(--color-accent-subtle)]' : 'hover:bg-[var(--color-bg-tertiary)]'
        }`}
      >
        {corpo}
      </div>
    </li>
  );
}

export function LateralSkills({ skills, aceita }: { skills: SkillsDoPedido; aceita: boolean }) {
  const q = useHabilidades();
  const [busca, setBusca] = useState('');
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const [mais, setMais] = useState<Record<string, number>>({});
  const buscaAdiada = useDeferredValue(busca);
  const [modo, setModo] = useState<ModoGrupo>('tema');
  const grupos = useMemo(
    () => agrupar(q.data?.grupos ?? [], q.data?.habilidades ?? [], buscaAdiada, modo),
    [q.data, buscaAdiada, modo],
  );

  if (q.isPending) {
    return (
      <div role="status" aria-label="Carregando skills" className="grid gap-2">
        <span className="sr-only">Carregando…</span>
        {[0, 1, 2, 3].map((i) => (
          <Esqueleto key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }
  if (q.isError) {
    if (q.error instanceof ErroApi && q.error.status === 404) {
      return <p className="text-xs text-[var(--color-text-secondary)] px-2 py-4">Esta versão do painel ainda não lista skills.</p>;
    }
    return <Erro erro={q.error} aoTentar={() => void q.refetch()} />;
  }

  const total = q.data.habilidades.length;
  const buscando = buscaAdiada.trim() !== '';
  const alternarGrupo = (id: string) =>
    setAbertos((s) => {
      const n = new Set(s);
      if (!n.delete(id)) n.add(id);
      return n;
    });

  return (
    <div className="grid gap-3 content-start min-w-0">
      <input
        type="search"
        aria-label="Buscar skill"
        placeholder="Buscar skill…"
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
        className="h-9 w-full rounded-lg border border-[var(--color-input-border)] bg-[var(--color-input-bg)] px-3 text-sm outline-none focus:border-[var(--color-accent)]"
      />
      <div className="flex gap-1 text-xs" role="group" aria-label="Como separar as skills">
        {(['tema', 'origem'] as const).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={modo === m}
            onClick={() => setModo(m)}
            className={`rounded-md px-2 py-1 border ${modo === m ? 'border-[var(--color-accent)] text-[var(--color-text-primary)]' : 'border-transparent text-[var(--color-text-secondary)]'}`}
          >
            {m === 'tema' ? 'Por tema' : 'Por plugin'}
          </button>
        ))}
      </div>
      {aceita ? (
        <p className="text-xs text-[var(--color-text-secondary)]">Clique ou arraste uma skill para a caixa de escrever.</p>
      ) : (
        <p className="text-xs text-[var(--color-text-secondary)]">Esta conversa não aceita skills. Comece uma conversa nova para escolher.</p>
      )}
      <p role="status" className="text-xs text-[var(--color-text-secondary)] empty:hidden">
        {skills.aviso}
      </p>
      {q.data.avisos?.map((a, i) => (
        <p key={i} className="text-xs text-[var(--color-text-secondary)] break-words">{a}</p>
      ))}
      {total === 0 ? (
        <p className="text-xs text-[var(--color-text-secondary)] px-2 py-4">Nenhuma skill encontrada neste computador.</p>
      ) : grupos.length === 0 ? (
        <p className="text-xs text-[var(--color-text-secondary)] px-2 py-4">Nenhuma skill combina com “{buscaAdiada.trim()}”.</p>
      ) : (
        grupos.map((g) => {
          const aberto = buscando || abertos.has(g.id);
          const { visiveis, restam } = fatiar(g.itens, LIMITE_POR_GRUPO + (mais[g.id] ?? 0));
          return (
            <section key={g.id} aria-label={g.titulo} className="grid gap-1 min-w-0">
              {g.fixo ? (
                <button
                  type="button"
                  aria-expanded={aberto}
                  onClick={() => alternarGrupo(g.id)}
                  className="grid gap-0.5 rounded-md px-1 py-1 text-left hover:bg-[var(--color-bg-tertiary)]"
                >
                  <span className="flex items-center gap-1.5 text-xs font-semibold">
                    <Lock size={12} aria-hidden="true" className="shrink-0" />
                    <span className="flex-1 truncate">{g.titulo}</span>
                    <span className="text-[var(--color-text-tertiary)] font-normal">{g.itens.length}</span>
                  </span>
                  <span className="text-xs text-[var(--color-text-secondary)]">Sempre ligado. Não precisa escolher.</span>
                </button>
              ) : (
                <button
                  type="button"
                  aria-expanded={aberto}
                  onClick={() => alternarGrupo(g.id)}
                  className="flex items-center gap-1.5 rounded-md px-1 py-1 text-xs font-semibold hover:bg-[var(--color-bg-tertiary)] text-left"
                >
                  <ChevronRight size={12} aria-hidden="true" className={`shrink-0 transition-transform ${aberto ? 'rotate-90' : ''}`} />
                  <span className="flex-1 truncate">{g.titulo}</span>
                  <span className="text-[var(--color-text-tertiary)] font-normal">{g.itens.length}</span>
                </button>
              )}
              {aberto && (
                <>
                  <ul className="grid gap-0.5">
                    {visiveis.map((h) => (
                      <ItemSkill key={h.id} h={h} marcada={skills.ids.includes(h.id)} bloqueada={!aceita} aoAlternar={() => skills.alternar(h.id)} />
                    ))}
                  </ul>
                  {restam > 0 && (
                    <button
                      type="button"
                      onClick={() => setMais((m) => ({ ...m, [g.id]: (m[g.id] ?? 0) + LIMITE_POR_GRUPO }))}
                      className="rounded-md px-2 py-1 text-xs text-[var(--color-accent)] hover:bg-[var(--color-bg-tertiary)] text-left"
                    >
                      mostrar mais ({restam})
                    </button>
                  )}
                </>
              )}
            </section>
          );
        })
      )}
    </div>
  );
}
