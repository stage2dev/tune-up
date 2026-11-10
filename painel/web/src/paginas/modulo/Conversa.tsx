// Bloco "conversa": fio de mensagens, caixa de envio e botoes de acao (com confirmacao na propria tela).
import { useLayoutEffect, useRef, useState } from 'react';
import type { Bloco } from '../../api/tipos';
import { Botao, Cartao, EstadoVazio } from '../../componentes';
import { CLASSE_CAMPO } from './Formulario';
import { dataHora } from './formato';
import { dadosDaMensagem, dadosFixos, estaNoFim, itens, textoOuNada } from './interativos';
import { AvisoEnvio, useEnvio } from './useEnvio';

const QUEM = { contato: 'Contato', eu: 'Você', ia: 'IA' } as const;
const ESTADO: Record<string, string> = { pendente: 'Enviando…', enviado: 'Enviado', falhou: 'Falhou', incerto: 'Não sei se chegou', negado: 'Não permitido' };
const COR_ESTADO: Record<string, string> = { falhou: 'var(--color-error)', negado: 'var(--color-error)', incerto: 'var(--color-attention)' };

function quando(q: unknown): string {
  if (typeof q !== 'string') return '';
  const d = dataHora(q);
  return d === 'sem dado' ? q : d;
}

export function Conversa({ b, moduloId }: { b: Bloco; moduloId?: string }) {
  const mensagens = itens(b.mensagens);
  const enviar = b.enviar && typeof b.enviar === 'object' ? (b.enviar as Record<string, unknown>) : null;
  const botoes = itens(b.botoes).filter((x) => typeof x.acao === 'string' && typeof x.rotulo === 'string');
  const [texto, setTexto] = useState('');
  const [pedindo, setPedindo] = useState<number | null>(null);
  const { enviar: chamar, enviando, ok, erro } = useEnvio(moduloId);
  const fio = useRef<HTMLDivElement>(null);
  const noFim = useRef(true);

  // Acompanha as mensagens novas so se a pessoa ja estava no fim (quem rolou para cima nao e puxado).
  useLayoutEffect(() => {
    const el = fio.current;
    if (el && noFim.current) el.scrollTop = el.scrollHeight;
  }, [mensagens.length]);

  async function mandar() {
    const t = texto.trim();
    const acao = textoOuNada(enviar?.acao);
    if (!t || !acao || enviando) return;
    if (await chamar(acao, dadosDaMensagem(enviar?.dados_fixos, t))) setTexto('');
  }
  async function botao(i: number) {
    const x = botoes[i];
    setPedindo(null);
    await chamar(String(x.acao), { ...dadosFixos(x.dados) });
  }

  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      {mensagens.length === 0 ? (
        <EstadoVazio titulo="Nenhuma mensagem" texto={textoOuNada(b.vazio) ?? 'A conversa ainda não tem mensagens.'} />
      ) : (
        <div
          ref={fio}
          role="log"
          aria-label="Mensagens"
          onScroll={(e) => { const el = e.currentTarget; noFim.current = estaNoFim(el.scrollHeight, el.scrollTop, el.clientHeight); }}
          className="grid gap-2 max-h-96 overflow-y-auto pr-1"
        >
          {mensagens.map((m, k) => {
            const de = String(m.de) in QUEM ? (String(m.de) as keyof typeof QUEM) : 'contato';
            const estado = typeof m.estado === 'string' ? m.estado : '';
            return (
              <div key={typeof m.id === 'string' ? m.id : k} className={`flex ${de === 'contato' ? 'justify-start' : 'justify-end'}`}>
                <div className={`max-w-[85%] min-w-0 rounded-lg border border-[var(--color-border)] px-3 py-2 ${de === 'contato' ? 'bg-[var(--color-bg-secondary)]' : 'bg-[var(--color-surface)]'}`}>
                  <div className="text-xs text-[var(--color-text-secondary)]">{QUEM[de]} · {quando(m.quando)}</div>
                  <p className="text-sm whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{typeof m.texto === 'string' ? m.texto : ''}</p>
                  {estado in ESTADO && <div className="text-xs mt-0.5" style={{ color: COR_ESTADO[estado] ?? 'var(--color-text-tertiary)' }}>{ESTADO[estado]}</div>}
                  {textoOuNada(m.nota) && <div className="text-xs text-[var(--color-text-tertiary)] break-words">{textoOuNada(m.nota)}</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {enviar && (
        <form className="mt-3 grid gap-2" onSubmit={(e) => { e.preventDefault(); void mandar(); }}>
          <label htmlFor={`msg-${moduloId ?? 'm'}`} className="sr-only">Mensagem</label>
          <textarea id={`msg-${moduloId ?? 'm'}`} rows={2} className={CLASSE_CAMPO} value={texto} onChange={(e) => setTexto(e.target.value)} autoComplete="off" placeholder="Escreva aqui" />
          <div><Botao type="submit" enviando={enviando} disabled={!texto.trim()}>{textoOuNada(enviar.rotulo) ?? 'Enviar'}</Botao></div>
        </form>
      )}
      {botoes.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {botoes.map((x, i) => (
            <Botao key={i} variante="secundario" disabled={enviando} onClick={() => (textoOuNada(x.confirmar) ? setPedindo(i) : void botao(i))}>{String(x.rotulo)}</Botao>
          ))}
        </div>
      )}
      {pedindo !== null && botoes[pedindo] && (
        <div role="alertdialog" aria-label="Confirmar" className="mt-2 rounded-lg border border-[var(--color-border)] p-3 grid gap-2">
          <p className="text-sm break-words">{textoOuNada(botoes[pedindo].confirmar)}</p>
          <div className="flex gap-2">
            <Botao enviando={enviando} onClick={() => void botao(pedindo)}>Confirmar</Botao>
            <Botao variante="fantasma" disabled={enviando} onClick={() => setPedindo(null)}>Cancelar</Botao>
          </div>
        </div>
      )}
      <div className="mt-2"><AvisoEnvio ok={ok} erro={erro} /></div>
    </Cartao>
  );
}
