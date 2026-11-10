// Adaptado de OpenJarvis (Apache-2.0), frontend/src/components/Layout.tsx e components/Sidebar/Sidebar.tsx; alterado
// (sem zustand/API deles; menu em gaveta no celular; navegacao do painel tune-up)
import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router';
import { Bot, ClipboardList, Home, ListChecks, Menu, MessageSquare, Play, X, Zap, type LucideIcon } from 'lucide-react';
import { useEstado, useModulos, useSessao } from './api/ganchos';
import { nomeDoProjeto } from './api/projeto';
import { iconeDoModulo } from './componentes/iconesModulo';
import { BotaoTema } from './tema/BotaoTema';
import { useAvisoDeFim } from './componentes/useAvisoDeFim';

interface ItemMenu {
  para: string;
  rotulo: string;
  icone: LucideIcon;
  fim?: boolean;
  alertas?: number;
}

const ITENS: ItemMenu[] = [
  { para: '/', rotulo: 'Chat', icone: MessageSquare, fim: true },
  { para: '/resumo', rotulo: 'Resumo', icone: Home },
  { para: '/agentes', rotulo: 'Agentes', icone: Bot },
  { para: '/fases', rotulo: 'Fases', icone: ListChecks },
  { para: '/execucoes', rotulo: 'Execuções', icone: Play },
  { para: '/acompanhamento', rotulo: 'Acompanhamento', icone: ClipboardList },
];

function Navegacao({ aoEscolher }: { aoEscolher?: () => void }) {
  const estado = useEstado();
  const modulos = useModulos();
  const extras: ItemMenu[] = (modulos.data?.modulos ?? []).map((m) => ({
    para: `/m/${encodeURIComponent(m.id)}`,
    rotulo: m.titulo,
    icone: iconeDoModulo(m.icone),
    alertas: m.alertas,
  }));
  const itens = [...ITENS, ...extras];
  return (
    <>
      <div className="flex items-center gap-2 px-4 h-14 shrink-0">
        <span className="grid place-items-center w-8 h-8 rounded-lg bg-[var(--color-accent)] text-[var(--color-on-accent)]">
          <Zap size={16} aria-hidden="true" />
        </span>
        <div className="min-w-0 leading-tight">
          <p className="text-sm font-semibold truncate">{nomeDoProjeto(estado.data)}</p>
          <p className="text-xs text-[var(--color-text-secondary)] truncate">Painel</p>
        </div>
      </div>
      <nav aria-label="Principal" className="flex-1 overflow-y-auto px-2 py-2 grid gap-0.5 content-start">
        {itens.map(({ para, rotulo, icone: Icone, fim, alertas }) => (
          <NavLink
            key={para}
            to={para}
            end={fim}
            onClick={aoEscolher}
            className={({ isActive }) =>
              `relative flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-[var(--color-accent-subtle)] text-[var(--color-accent)] font-medium before:content-[""] before:absolute before:left-0 before:top-2 before:bottom-2 before:w-0.5 before:rounded-full before:bg-[var(--color-accent)]'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text)]'
              }`
            }
          >
            <Icone size={16} aria-hidden="true" />
            <span className="flex-1 min-w-0 truncate">{rotulo}</span>
            {!!alertas && alertas > 0 && (
              <span
                className="shrink-0 min-w-5 h-5 px-1.5 grid place-items-center rounded-full text-xs font-medium bg-[var(--color-attention)] text-[var(--color-on-accent)]"
                aria-label={`${alertas} ${alertas === 1 ? 'alerta' : 'alertas'}`}
              >
                {alertas}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="px-2 py-3 border-t border-[var(--color-border)]">
        <BotaoTema />
      </div>
    </>
  );
}

export function Layout() {
  const [aberto, setAberto] = useState(false);
  const { pathname } = useLocation();
  const sessao = useSessao();
  const estado = useEstado();
  useAvisoDeFim();

  const nome = nomeDoProjeto(estado.data);
  useEffect(() => {
    document.title = `Painel ${nome}`;
  }, [nome]);
  useEffect(() => setAberto(false), [pathname]);
  useEffect(() => {
    if (!aberto) return;
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setAberto(false);
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [aberto]);

  const lateral =
    'flex flex-col bg-[var(--color-sidebar)] backdrop-blur-[20px] border-r border-[var(--color-border)]';

  return (
    <div className="flex h-full w-full overflow-hidden relative">
      <div className="hud-backdrop" aria-hidden="true" />

      {/* barra fixa no computador */}
      <aside className={`${lateral} hidden md:flex w-[var(--sidebar-width)] shrink-0 relative z-10`}>
        <Navegacao />
      </aside>

      {/* gaveta no celular */}
      {aberto && (
        <div className="md:hidden fixed inset-0 z-30">
          <div className="absolute inset-0 bg-black/40" onClick={() => setAberto(false)} aria-hidden="true" />
          <aside className={`${lateral} absolute inset-y-0 left-0 w-[min(80vw,280px)] bg-[var(--color-surface)]`} aria-label="Menu">
            <button
              type="button"
              onClick={() => setAberto(false)}
              aria-label="Fechar menu"
              className="absolute top-3 right-3 p-1.5 rounded text-[var(--color-text-secondary)]"
            >
              <X size={18} aria-hidden="true" />
            </button>
            <Navegacao aoEscolher={() => setAberto(false)} />
          </aside>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        <header className="md:hidden flex items-center gap-2 px-3 h-12 shrink-0 border-b border-[var(--color-border)] bg-[var(--color-sidebar)] backdrop-blur-[20px]">
          <button
            type="button"
            onClick={() => setAberto(true)}
            aria-label="Abrir menu"
            aria-expanded={aberto}
            className="p-2 -ml-1 rounded text-[var(--color-text-secondary)]"
          >
            <Menu size={20} aria-hidden="true" />
          </button>
          <span className="text-sm font-semibold">{nomeDoProjeto(estado.data)}</span>
        </header>

        {/* aviso de servidor fora do ar: so depois de a tentativa falhar */}
        {sessao.isError && (
          <div
            role="alert"
            className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm shrink-0"
            style={{
              background: 'color-mix(in srgb, var(--color-error) 8%, transparent)',
              borderBottom: '1px solid color-mix(in srgb, var(--color-error) 15%, transparent)',
            }}
          >
            <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-[var(--color-error)]" aria-hidden="true" />
            <span className="flex-1">Não consegui falar com o painel. Ele está ligado?</span>
            <button type="button" onClick={() => void sessao.refetch()} className="underline text-[var(--color-accent)] shrink-0">
              Tentar de novo
            </button>
          </div>
        )}

        <main className="flex-1 min-h-0 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
