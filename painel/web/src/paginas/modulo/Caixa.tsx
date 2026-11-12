// Bloco "caixa": caixa de entrada com a lista de conversas a esquerda e a conversa aberta a direita.
// Tela estreita (ate 768 px): um painel por vez, com botao de voltar. Clicar numa linha chama a acao `abrir`
// pela mesma rota de acao do modulo; a linha fica "abrindo" ate a releitura do modulo chegar.
import { useEffect, useRef, useState } from 'react';
import { useIsFetching } from '@tanstack/react-query';
import { ArrowLeft, Search } from 'lucide-react';
import { chaves } from '../../api/ganchos';
import { Cartao, EstadoVazio, Selo } from '../../componentes';
import type { Tom } from '../../componentes/Selo';
import { CLASSE_CAMPO } from './Formulario';
import { Conversa } from './Conversa';
import { conversaAVista, filtrarConversas, lerConversas, pedidoDaLinha, quandoCurto, voltouDepoisDeAbrir, type LinhaCaixa } from './entrada';
import { textoOuNada, type BlocoCru } from './interativos';
import { AvisoEnvio, useEnvio } from './useEnvio';

const TOM_SELO: Record<string, Tom> = { neutro: 'neutro', bom: 'ok', atencao: 'atencao', ruim: 'erro' };
/** Ate 768 px vale um painel por vez (max-[769px] = largura < 769 px). */
const ESTREITA_OCULTA = 'max-[769px]:hidden';

function Linha({ l, abrindo, desligada, aoAbrir }: { l: LinhaCaixa; abrindo: boolean; desligada: boolean; aoAbrir: () => void }) {
  const hora = quandoCurto(l.quando);
  return (
    <li>
      <button
        type="button"
        onClick={aoAbrir}
        disabled={desligada}
        aria-current={l.ativa ? 'true' : undefined}
        aria-busy={abrindo || undefined}
        data-ativa={l.ativa || undefined}
        className={`w-full text-left grid gap-0.5 rounded-lg px-2.5 py-2 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:cursor-wait ${
          l.ativa ? 'bg-[var(--color-accent-subtle)]' : 'hover:bg-[var(--color-bg-tertiary)]'
        } ${abrindo ? 'opacity-60' : ''}`}
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className={`text-sm truncate flex-1 min-w-0 ${l.ativa || l.naoLidas ? 'font-medium' : ''} ${l.ativa ? 'text-[var(--color-accent)]' : ''}`}>{l.titulo}</span>
          {(hora || abrindo) && <span className="shrink-0 text-[11px] tabular-nums text-[var(--color-text-tertiary)]">{abrindo ? 'abrindo…' : hora}</span>}
        </span>
        <span className="flex items-center gap-2 min-w-0">
          <span className="text-xs truncate flex-1 min-w-0 text-[var(--color-text-secondary)]">{l.detalhe ?? ''}</span>
          {l.selo && <Selo estado={l.selo.texto} rotulo={l.selo.texto} tom={TOM_SELO[l.selo.tom] ?? 'neutro'} />}
          {l.naoLidas > 0 && (
            <span className="shrink-0 min-w-5 h-5 px-1.5 rounded-full bg-[var(--color-accent)] text-[var(--color-on-accent)] text-[11px] font-medium grid place-items-center tabular-nums" aria-label={`${l.naoLidas} não lidas`}>
              {l.naoLidas > 99 ? '99+' : l.naoLidas}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

export function Caixa({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const linhas = lerConversas(b.conversas);
  const ativa = linhas.find((l) => l.ativa);
  const aberta = b.conversa && typeof b.conversa === 'object' && !Array.isArray(b.conversa) ? (b.conversa as Record<string, unknown>) : null;
  const [busca, setBusca] = useState('');
  const [pendente, setPendente] = useState<string | null>(null);
  const [voltou, setVoltou] = useState(false); // tela estreita: a pessoa voltou para a lista
  const { enviar, enviando, erro } = useEnvio(moduloId);
  const buscando = useIsFetching({ queryKey: chaves.modulo(moduloId ?? '') });
  const viuBusca = useRef(false);

  // "abrindo" acaba quando a releitura que veio depois da acao termina (ou a acao falha).
  useEffect(() => {
    if (!pendente || enviando) return;
    if (buscando > 0) viuBusca.current = true;
    else if (viuBusca.current) setPendente(null);
  }, [pendente, enviando, buscando]);
  useEffect(() => {
    if (!pendente) return;
    const t = setTimeout(() => setPendente(null), 20_000); // rede: nunca fica "abrindo" para sempre
    return () => clearTimeout(t);
  }, [pendente]);

  async function abrir(id: string) {
    const p = pedidoDaLinha(b.abrir, id);
    if (!p || pendente) return;
    viuBusca.current = false;
    setPendente(id);
    const ok = await enviar(p.acao, p.dados);
    setVoltou((v) => voltouDepoisDeAbrir(v, ok)); // falha: a lista (com o erro) fica a vista, nunca a conversa velha
    if (!ok) setPendente(null);
  }

  const vistas = filtrarConversas(linhas, busca);
  const mostraConversa = conversaAVista(!!aberta, voltou, pendente);
  const titulo = textoOuNada(aberta?.titulo) ?? ativa?.titulo;
  const voltar = (
    <button type="button" onClick={() => setVoltou(true)} className="min-[769px]:hidden mb-2 inline-flex items-center gap-1.5 text-sm text-[var(--color-accent)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] rounded">
      <ArrowLeft size={14} aria-hidden="true" /> Conversas
    </button>
  );

  return (
    <section aria-label={textoOuNada(b.titulo) ?? 'Caixa de entrada'} className="caixa grid gap-3 min-[769px]:grid-cols-[320px_minmax(0,1fr)] h-[calc(100dvh-14rem)] min-h-[26rem]">
      <Cartao titulo={textoOuNada(b.titulo)} data-painel="lista" className={`flex flex-col min-h-0 ${mostraConversa ? ESTREITA_OCULTA : ''}`}>
        <label className="relative mb-2 block shrink-0">
          <span className="sr-only">Buscar conversa</span>
          <Search size={14} aria-hidden="true" className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)]" />
          <input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar" autoComplete="off" className={`${CLASSE_CAMPO} pl-8`} />
        </label>
        <div className="shrink-0"><AvisoEnvio ok={false} erro={erro} /></div>
        <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1">
          {linhas.length === 0 ? (
            <EstadoVazio titulo="Nenhuma conversa" texto={textoOuNada(b.vazio) ?? 'As conversas aparecem aqui quando chegarem.'} />
          ) : vistas.length === 0 ? (
            <p className="text-xs text-[var(--color-text-secondary)] px-2 py-4 break-words">Nenhuma conversa com “{busca.trim()}”.</p>
          ) : (
            <ul className="grid gap-0.5" aria-label="Conversas">
              {vistas.map((l) => (
                <Linha key={l.id} l={l} abrindo={pendente === l.id} desligada={!!pendente} aoAbrir={() => void abrir(l.id)} />
              ))}
            </ul>
          )}
        </div>
      </Cartao>
      <div data-painel="conversa" className={`min-h-0 ${mostraConversa ? '' : ESTREITA_OCULTA}`}>
        {aberta ? (
          <Conversa
            key={`c:${String(aberta.id ?? ativa?.id ?? '')}`} // trocar de conversa zera o rascunho: texto nao vai para outro contato
            b={{ ...aberta, tipo: 'conversa', titulo }}
            moduloId={moduloId}
            cheia
            topo={voltar}
          />
        ) : (
          <Cartao className="h-full grid place-items-center">
            <EstadoVazio titulo="Nenhuma conversa aberta" texto={textoOuNada(b.vazio_conversa) ?? 'Escolha uma conversa na lista.'} />
          </Cartao>
        )}
      </div>
    </section>
  );
}
