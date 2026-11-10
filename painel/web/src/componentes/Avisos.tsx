// Aviso flutuante (toast). Use: const { avisar } = useAvisos(); avisar({ tipo:'sucesso', titulo:'Pronto' })
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';

export type TipoAviso = 'sucesso' | 'erro' | 'atencao' | 'info';
export interface NovoAviso {
  tipo: TipoAviso;
  titulo: string;
  texto?: string;
  /** milissegundos; 0 = fica ate fechar. Padrao 6000 (erro: 9000). */
  duracao?: number;
  /** Botao opcional no aviso (ex.: "Abrir a conversa"); o aviso fecha ao clicar. */
  acao?: { rotulo: string; aoClicar: () => void };
}
interface Aviso extends NovoAviso {
  id: number;
}

const COR: Record<TipoAviso, string> = {
  sucesso: 'var(--color-success)',
  erro: 'var(--color-error)',
  atencao: 'var(--color-attention)',
  info: 'var(--color-accent)',
};
const ICONE = { sucesso: CheckCircle2, erro: XCircle, atencao: AlertTriangle, info: Info } as const;

interface Ctx {
  avisar: (a: NovoAviso) => void;
}
const Contexto = createContext<Ctx | null>(null);

export function ProvedorAvisos({ children }: { children: ReactNode }) {
  const [lista, setLista] = useState<Aviso[]>([]);
  const proximo = useRef(1);

  const fechar = useCallback((id: number) => setLista((l) => l.filter((a) => a.id !== id)), []);
  const avisar = useCallback(
    (a: NovoAviso) => {
      const id = proximo.current++;
      setLista((l) => [...l.slice(-4), { ...a, id }]);
      const ms = a.duracao ?? (a.tipo === 'erro' ? 9000 : 6000);
      if (ms > 0) window.setTimeout(() => fechar(id), ms);
    },
    [fechar],
  );
  const valor = useMemo(() => ({ avisar }), [avisar]);

  return (
    <Contexto.Provider value={valor}>
      {children}
      <div
        aria-live="polite"
        role="status"
        className="fixed z-50 bottom-4 right-4 left-4 sm:left-auto sm:w-[360px] flex flex-col gap-2 pointer-events-none"
      >
        {lista.map((a) => {
          const Icone = ICONE[a.tipo];
          return (
            <div
              key={a.id}
              className="anim-entrar pointer-events-auto flex gap-3 p-3 rounded-lg border bg-[var(--color-surface)] shadow-[var(--shadow-lg)]"
              style={{ borderColor: `color-mix(in srgb, ${COR[a.tipo]} 40%, var(--color-border))` }}
            >
              <Icone size={18} aria-hidden="true" className="shrink-0 mt-0.5" style={{ color: COR[a.tipo] }} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{a.titulo}</p>
                {a.texto && <p className="text-xs text-[var(--color-text-secondary)] break-words">{a.texto}</p>}
                {a.acao && (
                  <button
                    type="button"
                    onClick={() => {
                      a.acao?.aoClicar();
                      fechar(a.id);
                    }}
                    className="mt-1 text-xs font-medium underline text-[var(--color-accent)]"
                  >
                    {a.acao.rotulo}
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={() => fechar(a.id)}
                aria-label="Fechar aviso"
                className="shrink-0 p-1 rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-text)]"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </Contexto.Provider>
  );
}

export function useAvisos(): Ctx {
  const c = useContext(Contexto);
  if (!c) throw new Error('useAvisos fora do ProvedorAvisos');
  return c;
}
