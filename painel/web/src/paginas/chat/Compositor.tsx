// Caixa de baixo da conversa: responder, interromper e enviar, parar, ou desabilitada (comecando).
// O que mostra vem de estadoCaixa(); o texto digitado fica se o envio falhar.
import { useState } from 'react';
import { Send, StopCircle } from 'lucide-react';
import { useResponder } from '../../api/ganchos';
import type { Execucao } from '../../api/tipos';
import { Botao } from '../../componentes';
import { CaixaTexto } from './CaixaTexto';
import { Perguntas } from './Perguntas';
import { estadoCaixa } from './caixa';
import { MAX_RESPOSTA } from './logica';

export function Compositor({ exec, aoParar }: { exec: Execucao; aoParar: () => void }) {
  const responder = useResponder();
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const limpo = texto.trim();
  const c = estadoCaixa({ estado: exec.estado, pode_responder: exec.pode_responder, pode_interromper: exec.pode_interromper, temPergunta: !!exec.pergunta, espera_terminal: exec.espera_terminal }, !limpo);

  const mandar = (t: string, limparCaixa: boolean) => {
    if (!t || responder.isPending) return;
    setErro(null);
    responder.mutate(
      { id: exec.id, texto: t, interromper: c.interromper },
      {
        onSuccess: () => limparCaixa && setTexto(''),
        onError: (e) => setErro(e instanceof Error && e.message ? e.message : 'Não consegui mandar. Tente de novo.'),
      },
    );
  };

  const enviar = () => {
    if (!c.habilitada) return;
    if (c.modo === 'parar') return; // Enter com a caixa vazia nao para a sessao
    mandar(limpo, true);
  };

  const botao =
    c.modo === 'parar' ? (
      <Botao variante="perigo" onClick={aoParar} icone={<StopCircle size={14} aria-hidden="true" />}>
        Parar
      </Botao>
    ) : c.botao ? (
      <Botao onClick={enviar} disabled={!limpo} enviando={responder.isPending} textoEnviando="Enviando…" icone={<Send size={14} aria-hidden="true" />}>
        {c.botao}
      </Botao>
    ) : null;

  return (
    <div className="grid gap-2">
      {c.modo === 'responder' && exec.pergunta && <Perguntas key={exec.id} pergunta={exec.pergunta} enviando={responder.isPending} aoEscolher={(t) => setTexto(t)} />}
      {c.dica && (
        <p role="status" className="text-xs text-[var(--color-text-secondary)]">
          {c.dica}
        </p>
      )}
      <CaixaTexto
        valor={texto}
        aoMudar={(v) => {
          setTexto(v);
          if (erro) setErro(null);
        }}
        aoEnviar={enviar}
        max={MAX_RESPOSTA}
        rotulo="Escreva para o Claude"
        placeholder={c.placeholder}
        desabilitado={!c.habilitada || responder.isPending}
        linhas={2}
        alturaMax={220}
      >
        {botao}
      </CaixaTexto>
      {erro && (
        <p role="alert" className="text-sm break-words text-[var(--color-error)]">
          {erro}
        </p>
      )}
    </div>
  );
}
