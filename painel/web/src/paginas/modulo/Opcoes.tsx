// Bloco "opcoes": cartoes para escolher 1 entre N (modo "um"; com `fontes`, o cartao ja vem escrito naquelas letras)
// ou chips liga/desliga (modo "varios"). Cada escolha chama o comando do modulo na hora.
// Modo "um" escreve no rascunho da aba (a previa acompanha); modo "varios" guarda a troca so ate o servidor devolver.
import { useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Cartao } from '../../componentes';
import { itens, textoOuNada, type BlocoCru } from './interativos';
import { fonteSegura } from './marca';
import { useRascunho } from './Rascunho';
import { AvisoEnvio, useEnvio } from './useEnvio';

export interface OpcaoLida { valor: string; rotulo: string; detalhe?: string; fontes?: { titulo: string; texto: string }; ligado: boolean }

export function lerOpcoes(v: unknown): OpcaoLida[] {
  return itens(v)
    .filter((o) => typeof o.valor === 'string' && o.valor)
    .map((o) => {
      const f = o.fontes && typeof o.fontes === 'object' ? (o.fontes as Record<string, unknown>) : null;
      return {
        valor: String(o.valor),
        rotulo: textoOuNada(o.rotulo) ?? String(o.valor),
        detalhe: textoOuNada(o.detalhe),
        fontes: f ? { titulo: fonteSegura(f.titulo), texto: fonteSegura(f.texto ?? f.titulo) } : undefined,
        ligado: o.ligado === true,
      };
    });
}

/** Chip: a troca local vale enquanto o servidor ainda mostra o valor de antes (`base`); quando ele muda, vale o servidor. */
export const chipLigado = (o: OpcaoLida, troca?: { ligado: boolean; base: boolean }): boolean =>
  troca && troca.base === o.ligado ? troca.ligado : o.ligado;

const BASE = 'min-h-11 rounded-xl border-2 text-left transition-colors disabled:cursor-wait break-words';

export function Opcoes({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const opcoes = lerOpcoes(b.opcoes);
  const acao = textoOuNada(b.acao);
  const campo = textoOuNada(b.campo);
  const varios = b.modo === 'varios';
  const { rascunho, por, tirar } = useRascunho();
  const { enviar, enviando, ok, erro } = useEnvio(moduloId);
  const [trocas, setTrocas] = useState<Record<string, { ligado: boolean; base: boolean }>>({});
  const exemplo = b.exemplo && typeof b.exemplo === 'object' ? (b.exemplo as Record<string, unknown>) : {};
  const doServidor = typeof b.valor === 'string' ? b.valor : '';
  const escolhido = (campo && rascunho[campo]?.valor) ?? doServidor;

  // Escolha unica: o servidor devolveu outro valor, o rascunho ja cumpriu o papel.
  const visto = useRef<string | null>(null);
  useEffect(() => {
    if (campo && visto.current !== null && visto.current !== doServidor) tirar(campo);
    visto.current = doServidor;
  }, [campo, doServidor, tirar]);

  async function escolher(o: OpcaoLida) {
    if (!acao || !campo || enviando || o.valor === escolhido) return;
    por(campo, { valor: o.valor, fontes: o.fontes });
    if (!(await enviar(acao, { campo, valor: o.valor }))) tirar(campo);
  }

  async function alternar(o: OpcaoLida) {
    if (!acao || !campo || enviando) return;
    const novo = !chipLigado(o, trocas[o.valor]);
    setTrocas((t) => ({ ...t, [o.valor]: { ligado: novo, base: o.ligado } }));
    if (!(await enviar(acao, { campo, valor: o.valor, ligado: novo }))) {
      setTrocas((t) => { const n = { ...t }; delete n[o.valor]; return n; });
    }
  }

  const desligado = enviando || !acao || !campo;
  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <div className="grid gap-3">
        {textoOuNada(b.descricao) && <p className="text-sm text-[var(--color-text-secondary)] break-words">{textoOuNada(b.descricao)}</p>}
        {opcoes.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary)]">{textoOuNada(b.vazio) ?? 'Ainda não há opções.'}</p>
        ) : varios ? (
          <div role="group" aria-label={textoOuNada(b.titulo) ?? 'Opções'} className="flex flex-wrap gap-2">
            {opcoes.map((o) => {
              const on = chipLigado(o, trocas[o.valor]);
              return (
                <button key={o.valor} type="button" aria-pressed={on} disabled={desligado} onClick={() => void alternar(o)}
                  className={`${BASE} rounded-full px-4 text-sm font-medium ${on ? 'bg-[var(--color-accent)] text-[var(--color-on-accent)] border-[var(--color-accent)]' : 'bg-[var(--color-surface)] text-[var(--color-text)] border-[var(--color-border)]'}`}>
                  {o.rotulo}
                </button>
              );
            })}
          </div>
        ) : (
          <div role="group" aria-label={textoOuNada(b.titulo) ?? 'Opções'} className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(min(100%,13rem),1fr))]">
            {opcoes.map((o) => {
              const on = o.valor === escolhido;
              return (
                <button key={o.valor} type="button" aria-pressed={on} disabled={desligado} onClick={() => void escolher(o)}
                  className={`${BASE} grid gap-1 p-4 bg-[var(--color-surface)] text-[var(--color-text)] ${on ? 'border-[var(--color-accent)]' : 'border-[var(--color-border)]'}`}>
                  {o.fontes && (
                    <>
                      <span className="text-2xl leading-tight font-bold" style={{ fontFamily: o.fontes.titulo }}>{textoOuNada(exemplo.titulo) ?? 'O seu negócio'}</span>
                      <span className="text-sm text-[var(--color-text-secondary)]" style={{ fontFamily: o.fontes.texto }}>{textoOuNada(exemplo.texto) ?? 'Um texto curto, do jeito que vai sair nas peças.'}</span>
                    </>
                  )}
                  <span className={`text-sm font-semibold ${on ? 'text-[var(--color-accent)]' : ''}`}>{o.rotulo}{on ? ' (escolhida)' : ''}</span>
                  {o.detalhe && <span className="text-xs text-[var(--color-text-secondary)]">{o.detalhe}</span>}
                </button>
              );
            })}
          </div>
        )}
        {(!acao || !campo) && opcoes.length > 0 && <p role="note" className="text-xs text-[var(--color-text-tertiary)]">Este bloco não diz qual comando salva a escolha.</p>}
        {enviando ? (
          <p role="status" className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]"><Loader2 size={14} className="anim-girar" aria-hidden="true" />Salvando…</p>
        ) : <AvisoEnvio ok={ok} erro={erro} />}
      </div>
    </Cartao>
  );
}
