// Bloco "conversa": fio de mensagens, caixa de envio e botoes de acao (com confirmacao na propria tela).
// Tambem e o painel direito do bloco "caixa" (cheia: ocupa a altura, fio rola por dentro, envio preso embaixo).
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Botao, Cartao, EstadoVazio } from '../../componentes';
import { CLASSE_CAMPO } from './Formulario';
import { copiaDoBotao, criarEnviador, dadosDaMensagem, estaNoFim, itens, textoOuNada, type BlocoCru, type BotaoCopia } from './interativos';
import { Mensagens } from './Mensagens';
import { AvisoEnvio, useEnvio } from './useEnvio';

export function Conversa({ b, moduloId, cheia = false, topo }: { b: BlocoCru; moduloId?: string; cheia?: boolean; topo?: ReactNode }) {
  const mensagens = itens(b.mensagens);
  const enviar = b.enviar && typeof b.enviar === 'object' ? (b.enviar as Record<string, unknown>) : null;
  const botoes = itens(b.botoes).filter((x) => typeof x.acao === 'string' && typeof x.rotulo === 'string');
  const [texto, setTexto] = useState('');
  const [pedindo, setPedindo] = useState<BotaoCopia | null>(null);
  const { enviar: chamar, enviando, ok, erro } = useEnvio(moduloId);
  const fio = useRef<HTMLDivElement>(null);
  const noFim = useRef(true);
  const postar = useRef<(t: string, id: string) => Promise<boolean>>(async () => false);
  postar.current = (t, id) => chamar(String(enviar?.acao), dadosDaMensagem(enviar?.dados_fixos, t, () => id));
  const [mandarTexto] = useState(() => criarEnviador((t, id) => postar.current(t, id)));

  // Acompanha as mensagens novas so se a pessoa ja estava no fim (quem rolou para cima nao e puxado).
  useLayoutEffect(() => {
    const el = fio.current;
    if (el && noFim.current) el.scrollTop = el.scrollHeight;
  }, [mensagens.length, String(mensagens[mensagens.length - 1]?.id ?? '')]);

  async function mandar() {
    const t = texto.trim();
    const acao = textoOuNada(enviar?.acao);
    if (!t || !acao || enviando) return;
    if (await mandarTexto(t)) setTexto((cur) => (cur.trim() === t ? '' : cur)); // nao apaga o que foi digitado durante o envio
  }
  async function botao(x: BotaoCopia) {
    setPedindo(null);
    await chamar(x.acao, x.dados);
  }

  return (
    <Cartao titulo={textoOuNada(b.titulo)} className={cheia ? 'flex flex-col h-full min-h-0' : ''}>
      {topo}
      {mensagens.length === 0 ? (
        <div className={cheia ? 'flex-1' : ''}><EstadoVazio titulo="Nenhuma mensagem" texto={textoOuNada(b.vazio) ?? 'A conversa ainda não tem mensagens.'} /></div>
      ) : (
        <div
          ref={fio}
          role="log"
          aria-label="Mensagens"
          onScroll={(e) => { const el = e.currentTarget; noFim.current = estaNoFim(el.scrollHeight, el.scrollTop, el.clientHeight); }}
          className={`flex flex-col gap-2 overflow-y-auto pr-1 ${cheia ? 'flex-1 min-h-0' : 'max-h-96'}`}
        >
          <Mensagens mensagens={mensagens} moduloId={moduloId} />
        </div>
      )}
      {enviar && (
        <form className="mt-3 grid gap-2 shrink-0" onSubmit={(e) => { e.preventDefault(); void mandar(); }}>
          <label htmlFor={`msg-${moduloId ?? 'm'}`} className="sr-only">Mensagem</label>
          <textarea id={`msg-${moduloId ?? 'm'}`} rows={2} className={CLASSE_CAMPO} value={texto} onChange={(e) => setTexto(e.target.value)} autoComplete="off" placeholder="Escreva aqui (Enter envia, Shift+Enter quebra a linha)"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void mandar(); } }} />
          <div><Botao type="submit" enviando={enviando} disabled={!texto.trim()}>{textoOuNada(enviar.rotulo) ?? 'Enviar'}</Botao></div>
        </form>
      )}
      {botoes.length > 0 && (
        <div className="mt-3 shrink-0 flex flex-wrap gap-2">
          {botoes.map((x, i) => (
            <Botao key={i} variante="secundario" disabled={enviando} onClick={() => { const cp = copiaDoBotao(x); if (cp.confirmar) setPedindo(cp); else void botao(cp); }}>{String(x.rotulo)}</Botao>
          ))}
        </div>
      )}
      {pedindo !== null && (
        <div role="alertdialog" aria-label="Confirmar" className="mt-2 rounded-lg border border-[var(--color-border)] p-3 grid gap-2">
          <p className="text-sm break-words">{pedindo.confirmar}</p>
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
