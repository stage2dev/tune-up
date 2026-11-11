// Opcoes da pergunta que o Claude escreveu (execucao.pergunta), em botoes grandes.
// Clicar NUNCA envia: poe a resposta na caixa de baixo para a pessoa conferir e enviar (as opcoes vem de um
// arquivo que a sessao escreve, entao um botao nao pode virar mensagem sem a pessoa ver o texto).
// Uma pergunta de uma escolha: um clique escolhe. Varias ou multipla: marca e clica "Usar estas respostas".
import { useState } from 'react';
import { Check } from 'lucide-react';
import type { PerguntaChat } from '../../api/tipos';
import { Botao } from '../../componentes';
import { alternarOpcao, envioDireto, textoDasRespostas } from './caixa';

export function Perguntas({ pergunta, enviando, aoEscolher }: { pergunta: PerguntaChat; enviando: boolean; aoEscolher: (texto: string) => void }) {
  const ps = pergunta.perguntas ?? [];
  const [marcadas, setMarcadas] = useState<string[][]>([]);
  if (ps.length === 0 || ps.every((p) => p.opcoes.length === 0)) return null;
  const direto = envioDireto(ps);
  const texto = textoDasRespostas(ps, marcadas);

  return (
    <div className="grid gap-3" aria-label="Opções de resposta" role="group">
      {ps.map((p, i) => (
        <fieldset key={i} className="grid gap-1.5 min-w-0">
          <legend className="text-sm font-medium mb-1 break-words">
            {p.cabecalho && <span className="text-xs text-[var(--color-text-secondary)] block">{p.cabecalho}</span>}
            {p.pergunta}
            {p.multipla && <span className="text-xs font-normal text-[var(--color-text-secondary)]"> (pode marcar mais de uma)</span>}
          </legend>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {p.opcoes.map((o) => {
              const marcada = (marcadas[i] ?? []).includes(o.rotulo);
              return (
                <button
                  key={o.rotulo}
                  type="button"
                  disabled={enviando}
                  aria-pressed={direto ? undefined : marcada}
                  onClick={() => (direto ? aoEscolher(o.rotulo) : setMarcadas((m) => alternarOpcao(m, ps, i, o.rotulo)))}
                  className={`text-left rounded-lg border px-3 py-2 min-h-11 transition-colors disabled:opacity-60 ${
                    marcada
                      ? 'border-[var(--color-accent)] bg-[var(--color-accent-subtle)]'
                      : 'border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-bg-tertiary)]'
                  }`}
                >
                  <span className="flex items-center gap-1.5 text-sm font-medium break-words">
                    {marcada && <Check size={14} aria-hidden="true" className="shrink-0 text-[var(--color-accent)]" />}
                    {o.rotulo}
                  </span>
                  {o.descricao && <span className="block text-xs text-[var(--color-text-secondary)] break-words">{o.descricao}</span>}
                </button>
              );
            })}
          </div>
        </fieldset>
      ))}
      {!direto && (
        <div>
          <Botao variante="secundario" onClick={() => aoEscolher(texto)} disabled={!texto || enviando}>
            Usar estas respostas
          </Botao>
        </div>
      )}
      <p className="text-xs text-[var(--color-text-tertiary)]">A opção escolhida vai para a caixa abaixo. Confira e envie, ou escreva do seu jeito.</p>
    </div>
  );
}
