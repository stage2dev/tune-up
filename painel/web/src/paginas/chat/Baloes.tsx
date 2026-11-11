// Area da conversa: baloes do dono e do Claude, atividade recolhida entre as falas.
// Rolagem: desce para o fim quando chega coisa nova so se a pessoa ja estava perto do fim.
import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { AlertTriangle, ArrowDown, ChevronRight, Wrench } from 'lucide-react';
import type { EventoExecucao } from '../../api/tipos';
import { estaNoFim, horaDoEvento } from '../dev/logica';
import { descreverEvento, pedacosDoTexto, ultimaAcao, type ItemConversa } from './logica';

function TextoFala({ texto }: { texto: string }) {
  return (
    <>
      {pedacosDoTexto(texto).map((p, i) =>
        p.codigo ? (
          <pre key={i} className="my-1 overflow-x-auto rounded-md bg-[var(--color-bg-tertiary)] px-2 py-1.5 text-xs font-mono whitespace-pre">
            {p.texto}
          </pre>
        ) : (
          <p key={i} className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
            {p.texto}
          </p>
        ),
      )}
    </>
  );
}

function Balao({ dono, quem, ts, erro, children }: { dono: boolean; quem: string; ts: string; erro?: boolean; children: ReactNode }) {
  const hora = ts ? horaDoEvento(ts) : '';
  return (
    <div className={`flex ${dono ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] min-w-0 rounded-2xl px-3 py-2 text-sm grid gap-1 ${
          dono ? 'rounded-br-sm bg-[var(--color-accent)] text-[var(--color-on-accent)]' : 'rounded-bl-sm bg-[var(--color-bg-tertiary)] text-[var(--color-text)]'
        }`}
        style={erro ? { boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--color-error) 50%, transparent)' } : undefined}
      >
        <span className={`text-[11px] ${dono ? 'opacity-80' : 'text-[var(--color-text-tertiary)]'}`}>
          {quem}
          {hora && ` · ${hora}`}
        </span>
        {children}
      </div>
    </div>
  );
}

function LinhaAtividade({ ev }: { ev: EventoExecucao }) {
  return (
    <li className="flex gap-2 text-xs min-w-0" style={ev.erro ? { color: 'var(--color-error)' } : undefined}>
      <span className="shrink-0 tabular-nums text-[var(--color-text-tertiary)]">{horaDoEvento(ev.ts)}</span>
      <span className="min-w-0 break-words [overflow-wrap:anywhere]">{descreverEvento(ev)}</span>
    </li>
  );
}

function Atividade({ eventos, erros, ativa }: { eventos: EventoExecucao[]; erros: number; ativa: boolean }) {
  const n = eventos.length;
  return (
    <details className="group mx-auto w-full max-w-[90%] text-xs text-[var(--color-text-secondary)]">
      <summary className="flex items-center gap-1.5 cursor-pointer list-none rounded-md px-2 py-1 hover:bg-[var(--color-bg-tertiary)] min-w-0">
        <ChevronRight size={12} aria-hidden="true" className="shrink-0 transition-transform group-open:rotate-90" />
        <Wrench size={12} aria-hidden="true" className="shrink-0" />
        <span className="shrink-0">
          {ativa ? 'trabalhando…' : 'trabalhou'} {n} {n === 1 ? 'passo' : 'passos'}
        </span>
        {erros > 0 && (
          <span className="shrink-0 inline-flex items-center gap-0.5 text-[var(--color-error)]">
            <AlertTriangle size={11} aria-hidden="true" />
            {erros} com erro
          </span>
        )}
        <span className="min-w-0 truncate text-[var(--color-text-tertiary)]">· {ultimaAcao(eventos)}</span>
      </summary>
      <ul className="mt-1 grid gap-1 rounded-md border border-[var(--color-border)] p-2">
        {eventos.map((ev) => (
          <LinhaAtividade key={ev.n} ev={ev} />
        ))}
      </ul>
    </details>
  );
}

interface Props {
  itens: ItemConversa[];
  /** Frase do fim ("trabalhando… lendo arquivos"); null = nao esta trabalhando. */
  trabalhando: string | null;
  /** Algo para o fim da conversa (aviso de "precisa de voce", "sumiu"...). */
  rodape?: ReactNode;
}

export function Baloes({ itens, trabalhando, rodape }: Props) {
  const caixa = useRef<HTMLDivElement>(null);
  const noFim = useRef(true);
  const [longe, setLonge] = useState(false);

  const aoRolar = useCallback(() => {
    const c = caixa.current;
    if (!c) return;
    noFim.current = estaNoFim(c.scrollHeight, c.scrollTop, c.clientHeight, 80);
    setLonge(!noFim.current);
  }, []);

  const irAoFim = useCallback(() => {
    const c = caixa.current;
    if (!c) return;
    c.scrollTop = c.scrollHeight;
    noFim.current = true;
    setLonge(false);
  }, []);

  // Conta eventos (nao so itens): atividade nova dentro do mesmo bloco tambem desce.
  const tamanho = itens.reduce((s, i) => s + (i.tipo === 'atividade' ? i.eventos.length : 1), 0);
  useLayoutEffect(() => {
    const c = caixa.current;
    if (c && noFim.current) c.scrollTop = c.scrollHeight;
  }, [tamanho, trabalhando, rodape]);

  const ultimo = itens[itens.length - 1];
  return (
    <div className="relative flex-1 min-h-0">
      <div
        ref={caixa}
        onScroll={aoRolar}
        role="log"
        aria-live="polite"
        aria-label="Conversa"
        className="grid grid-cols-1 gap-3 content-start overflow-y-auto overflow-x-hidden h-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
      >
        {itens.map((it) =>
          it.tipo === 'atividade' ? (
            <Atividade key={it.chave} eventos={it.eventos} erros={it.erros} ativa={!!trabalhando && it === ultimo} />
          ) : (
            <Balao key={it.chave} dono={it.tipo === 'dono'} quem={it.tipo === 'dono' ? 'Você' : 'Claude'} ts={it.ts} erro={it.tipo === 'claude' && it.erro}>
              <TextoFala texto={it.texto} />
              {it.tipo === 'dono' && it.habilidades && (
                <span className="text-[11px] opacity-80 break-words [overflow-wrap:anywhere]">com: {it.habilidades.join(', ')}</span>
              )}
            </Balao>
          ),
        )}
        {trabalhando && (
          <p role="status" className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] px-1">
            <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] hud-dot-pulse" aria-hidden="true" />
            {trabalhando}
          </p>
        )}
        {rodape}
      </div>
      {longe && (
        <button
          type="button"
          onClick={irAoFim}
          className="absolute bottom-3 right-5 inline-flex items-center gap-1 rounded-full bg-[var(--color-accent)] text-[var(--color-on-accent)] text-xs px-3 py-1.5 shadow-[var(--shadow-lg)]"
        >
          <ArrowDown size={12} aria-hidden="true" />
          Ir para o fim
        </button>
      )}
    </div>
  );
}
