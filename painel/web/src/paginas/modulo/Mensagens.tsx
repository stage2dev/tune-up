// Fio de mensagens da conversa: separador por dia, hora em cada balao e etiqueta para o que nao e texto.
// Mesma linguagem visual dos baloes do chat (paginas/chat/Baloes.tsx). So texto: nada de HTML vindo do modulo.
import { FileText, Image, Mic, Paperclip } from 'lucide-react';
import { fioComDias, horaDaMensagem, legendaDe, rotuloDoTipo } from './entrada';
import { textoOuNada } from './interativos';
import { lerMidia, MidiaDaMensagem } from './MidiaMensagem';

const QUEM = { contato: 'Contato', eu: 'Você', ia: 'IA' } as const;
const ESTADO: Record<string, string> = { pendente: 'Enviando…', enviado: 'Enviado', falhou: 'Falhou', incerto: 'Não sei se chegou', negado: 'Não permitido' };
const COR_ESTADO: Record<string, string> = { falhou: 'var(--color-error)', negado: 'var(--color-error)', incerto: 'var(--color-attention)' };
const ICONE = { audio: Mic, imagem: Image, documento: FileText, outro: Paperclip } as const;

function Etiqueta({ tipo, rotulo }: { tipo: string; rotulo: string }) {
  const Icone = ICONE[tipo as keyof typeof ICONE] ?? Paperclip;
  return (
    <span data-tipo={tipo} className="inline-flex items-center gap-1.5 rounded-full border border-current/30 px-2 py-0.5 text-xs w-fit">
      <Icone size={12} aria-hidden="true" />
      {rotulo}
    </span>
  );
}

function Balao({ m, moduloId }: { m: Record<string, unknown>; moduloId?: string }) {
  const de = String(m.de) in QUEM ? (String(m.de) as keyof typeof QUEM) : 'contato';
  const estado = typeof m.estado === 'string' ? m.estado : '';
  const tipo = rotuloDoTipo(m.tipo);
  const texto = tipo ? legendaDe(m.texto) : typeof m.texto === 'string' ? m.texto : '';
  const hora = horaDaMensagem(m.quando);
  const midia = moduloId ? lerMidia(m.midia) : null; // sem midia valida fica a etiqueta do tipo
  const cor =
    de === 'contato'
      ? 'rounded-bl-sm bg-[var(--color-bg-tertiary)] text-[var(--color-text)]'
      : de === 'eu'
        ? 'rounded-br-sm bg-[var(--color-accent)] text-[var(--color-on-accent)]'
        : 'rounded-br-sm bg-[var(--color-accent-subtle)] text-[var(--color-text)]';
  const suave = de === 'eu' ? 'opacity-80' : 'text-[var(--color-text-tertiary)]';
  return (
    <div className={`flex ${de === 'contato' ? 'justify-start' : 'justify-end'}`}>
      <div className={`max-w-[85%] min-w-0 rounded-2xl px-3 py-2 text-sm grid gap-1 ${cor}`}>
        {de !== 'contato' && <span className={`text-[11px] ${suave}`}>{QUEM[de]}</span>}
        {midia && moduloId ? (
          <MidiaDaMensagem m={midia} moduloId={moduloId} transcricao={textoOuNada(m.transcricao)} />
        ) : (
          tipo && <Etiqueta tipo={String(m.tipo)} rotulo={tipo} />
        )}
        {texto && <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{texto}</p>}
        {textoOuNada(m.nota) && <span className={`text-xs break-words ${suave}`}>{textoOuNada(m.nota)}</span>}
        <span className={`flex justify-end gap-1.5 text-[11px] ${suave}`}>
          {estado in ESTADO && <span style={COR_ESTADO[estado] ? { color: COR_ESTADO[estado] } : undefined}>{ESTADO[estado]}</span>}
          {hora && <span className="tabular-nums">{hora}</span>}
        </span>
      </div>
    </div>
  );
}

export function Mensagens({ mensagens, moduloId }: { mensagens: Record<string, unknown>[]; moduloId?: string }) {
  return (
    <>
      {fioComDias(mensagens).map((it) =>
        'dia' in it ? (
          <div key={it.chave} role="separator" className="flex justify-center my-1">
            <span className="rounded-full bg-[var(--color-bg-secondary)] px-2.5 py-0.5 text-[11px] text-[var(--color-text-secondary)]">{it.dia}</span>
          </div>
        ) : (
          <Balao key={it.chave} m={it.mensagem} moduloId={moduloId} />
        ),
      )}
    </>
  );
}
