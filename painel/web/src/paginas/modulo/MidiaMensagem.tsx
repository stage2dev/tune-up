// Arquivo de uma mensagem da conversa (campo `midia`): player de audio com a transcricao, miniatura de imagem que
// abre ampliada, ou linha de documento com "Baixar". Os bytes vem de GET /api/modulos/<id>/arquivo?ref=: a URL e
// montada aqui so com o id do modulo da pagina e a ref (nunca uma URL vinda do modulo).
import { useEffect, useReducer, useRef, useState } from 'react';
import { FileText } from 'lucide-react';
import { useModuloAtualizado } from '../../api/ganchos';
import { Botao } from '../../componentes';
import { textoOuNada } from './interativos';
import { AvisoEnvio, useEnvio } from './useEnvio';

export interface MidiaLida {
  ref: string;
  tipo: 'audio' | 'imagem' | 'documento';
  nome?: string;
  tamanho?: number;
  duracao?: number;
  estado: 'pronta' | 'pendente' | 'falhou' | 'expirada';
  aviso?: string;
  acao?: { acao: string; dados: Record<string, unknown> };
}

const RE_REF = /^[A-Za-z0-9._:-]{1,200}$/;
const TIPOS = ['audio', 'imagem', 'documento'];
const ESTADOS = ['pronta', 'pendente', 'falhou', 'expirada'];
const numero = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : undefined);

/** A midia da mensagem, ou null se esta fora da forma (a tela cai na etiqueta do `tipo`). */
export function lerMidia(v: unknown): MidiaLida | null {
  if (!v || typeof v !== 'object') return null;
  const m = v as Record<string, unknown>;
  const ref = m.ref;
  if (typeof ref !== 'string' || !RE_REF.test(ref) || ref.includes('..') || ref.startsWith('.')) return null;
  if (typeof m.tipo !== 'string' || !TIPOS.includes(m.tipo)) return null;
  const a = m.acao && typeof m.acao === 'object' ? (m.acao as Record<string, unknown>) : null;
  const dados = a?.dados && typeof a.dados === 'object' && !Array.isArray(a.dados) ? (a.dados as Record<string, unknown>) : {};
  return {
    ref,
    tipo: m.tipo as MidiaLida['tipo'],
    nome: textoOuNada(m.nome),
    tamanho: numero(m.tamanho),
    duracao: numero(m.duracao),
    estado: typeof m.estado === 'string' && ESTADOS.includes(m.estado) ? (m.estado as MidiaLida['estado']) : 'pronta',
    aviso: textoOuNada(m.aviso),
    acao: a && typeof a.acao === 'string' && a.acao ? { acao: a.acao, dados } : undefined,
  };
}

export const urlDaMidia = (moduloId: string, ref: string): string =>
  `/api/modulos/${encodeURIComponent(moduloId)}/arquivo?ref=${encodeURIComponent(ref)}`;

/** 75 -> "1:15". */
export function duracaoCurta(s: number | undefined): string {
  if (s === undefined) return '';
  const t = Math.round(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
}

/** 1536 -> "1,5 KB". */
export function tamanhoCurto(b: number | undefined): string {
  if (b === undefined) return '';
  if (b < 1024) return `${Math.round(b)} B`;
  const [v, u] = b < 1024 * 1024 ? [b / 1024, 'KB'] : [b / (1024 * 1024), 'MB'];
  return `${v.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} ${u}`;
}

const SUAVE = 'text-xs opacity-80';
const ESPERA_NOVA_TENTATIVA = 1500; // ms; o servidor segura ate 5 s por uma vaga, entao uma tentativa basta

export interface Carga { chave: number; restam: number; falhou: boolean }
export const CARGA_INICIAL: Carga = { chave: 0, restam: 1, falhou: false };

/** Carga do <img>/<audio>: o 1o erro gasta a tentativa ('tentar' remonta o elemento depois da espera); o 2o
 *  mostra a falha; 'dado-novo' (chegaram dados do modulo) limpa a falha sem remontar o que carregou bem. */
export function carga(c: Carga, e: 'erro' | 'tentar' | 'dado-novo'): Carga {
  if (e === 'erro') return c.restam > 0 ? { ...c, restam: c.restam - 1 } : { ...c, falhou: true };
  if (e === 'tentar') return { ...c, chave: c.chave + 1 };
  return c.falhou || c.restam < 1 ? { ...c, restam: 1, falhou: false } : c;
}

function useCarga(moduloId: string) {
  const fonte = useModuloAtualizado(moduloId);
  const [c, dispara] = useReducer(carga, CARGA_INICIAL);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => dispara('dado-novo'), [fonte]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const aoErro = () => {
    const tenta = c.restam > 0;
    dispara('erro');
    if (tenta) timer.current = window.setTimeout(() => dispara('tentar'), ESPERA_NOVA_TENTATIVA);
  };
  return { chave: c.chave, falhou: c.falhou, aoErro };
}

function Ampliada({ url, nome, aberta, aoFechar }: { url: string; nome: string; aberta: boolean; aoFechar: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  // showModal(): o navegador prende o foco, fecha com Esc ("cancel"); close() devolve o foco a miniatura.
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (aberta && !d.open) d.showModal();
    if (!aberta && d.open) d.close();
  }, [aberta]);
  return (
    <dialog
      ref={ref}
      aria-label={nome}
      onCancel={(e) => { e.preventDefault(); aoFechar(); }}
      onClick={(e) => { if (e.target === ref.current) aoFechar(); }}
      className="m-auto max-w-[92vw] rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-[var(--color-text)]"
    >
      {aberta && (
        <div className="grid gap-2">
          <img src={url} alt={nome} className="max-h-[80vh] max-w-full object-contain" />
          <div className="flex justify-end gap-2">
            <a href={url} download={nome} className="text-sm underline">Baixar</a>
            <Botao variante="fantasma" autoFocus onClick={aoFechar}>Fechar</Botao>
          </div>
        </div>
      )}
    </dialog>
  );
}

function Imagem({ url, nome, moduloId }: { url: string; nome: string; moduloId: string }) {
  const [aberta, setAberta] = useState(false);
  const { chave, falhou, aoErro } = useCarga(moduloId);
  if (falhou) return <span role="alert" className={SUAVE}>Não deu para carregar esta imagem.</span>;
  return (
    <>
      <button type="button" onClick={() => setAberta(true)} aria-label={`Ampliar ${nome}`} className="w-fit rounded-lg overflow-hidden">
        <img key={chave} src={url} alt={nome} loading="lazy" className="max-h-60 max-w-full object-contain" onError={aoErro} />
      </button>
      <Ampliada url={url} nome={nome} aberta={aberta} aoFechar={() => setAberta(false)} />
    </>
  );
}

function Audio({ url, m, moduloId }: { url: string; m: MidiaLida; moduloId: string }) {
  const { chave, falhou, aoErro } = useCarga(moduloId);
  return (
    <div className="grid gap-1">
      {falhou ? (
        <span role="alert" className={SUAVE}>Não deu para carregar este áudio.</span>
      ) : (
        <audio key={chave} controls preload="none" src={url} aria-label={m.nome ?? 'Áudio'} className="max-w-full" onError={aoErro} />
      )}
      {m.duracao !== undefined && <span className={`${SUAVE} tabular-nums`}>Áudio de {duracaoCurta(m.duracao)}</span>}
    </div>
  );
}

function Documento({ url, m }: { url: string; m: MidiaLida }) {
  const nome = m.nome ?? 'Documento';
  return (
    <div className="flex items-center gap-2 min-w-0">
      <FileText size={16} aria-hidden="true" className="shrink-0" />
      <span className="truncate min-w-0">{nome}</span>
      {m.tamanho !== undefined && <span className={`${SUAVE} shrink-0 tabular-nums`}>{tamanhoCurto(m.tamanho)}</span>}
      <a href={url} download={nome} className="shrink-0 underline text-sm">Baixar</a>
    </div>
  );
}

function Falhou({ m, moduloId }: { m: MidiaLida; moduloId: string }) {
  const { enviar, enviando, ok, erro } = useEnvio(moduloId);
  const padrao = m.estado === 'expirada' ? 'Este arquivo expirou.' : 'Não deu para baixar este arquivo.';
  return (
    <div className="grid gap-1">
      <span role="status" className={SUAVE}>{m.aviso ?? padrao}</span>
      {m.acao && (
        <div>
          <Botao variante="secundario" enviando={enviando} onClick={() => { if (m.acao) void enviar(m.acao.acao, m.acao.dados); }}>Tentar de novo</Botao>
        </div>
      )}
      <AvisoEnvio ok={ok} erro={erro} />
    </div>
  );
}

/** Texto do audio: aparece sempre que existe, qualquer que seja o estado da midia (Mensagens.tsx). */
export function Transcricao({ texto }: { texto: string }) {
  return (
    <p className={`${SUAVE} whitespace-pre-wrap break-words`}>
      <span className="font-medium">Transcrição: </span>
      {texto}
    </p>
  );
}

export function MidiaDaMensagem({ m, moduloId }: { m: MidiaLida; moduloId: string }) {
  if (m.estado === 'pendente') return <span role="status" className={SUAVE}>baixando…</span>;
  if (m.estado === 'falhou' || m.estado === 'expirada') return <Falhou m={m} moduloId={moduloId} />;
  const url = urlDaMidia(moduloId, m.ref);
  if (m.tipo === 'audio') return <Audio url={url} m={m} moduloId={moduloId} />;
  if (m.tipo === 'imagem') return <Imagem url={url} nome={m.nome ?? 'Imagem'} moduloId={moduloId} />;
  return <Documento url={url} m={m} />;
}
