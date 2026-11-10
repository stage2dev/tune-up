// Caixa de resposta no rodape da conversa (POST /api/execucoes/{id}/responder).
import { useState } from 'react';
import { Send } from 'lucide-react';
import { useResponder } from '../../api/ganchos';
import { Botao } from '../../componentes';
import { CaixaTexto } from './CaixaTexto';
import { MAX_RESPOSTA } from './logica';

export function Resposta({ id }: { id: string }) {
  const responder = useResponder();
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const limpo = texto.trim();

  const enviar = () => {
    if (!limpo || responder.isPending) return;
    setErro(null);
    responder.mutate(
      { id, texto: limpo },
      {
        onSuccess: () => setTexto(''),
        onError: (e) => setErro(e instanceof Error && e.message ? e.message : 'Não consegui mandar. Tente de novo.'),
      },
    );
  };

  return (
    <div className="grid gap-2">
      <CaixaTexto
        valor={texto}
        aoMudar={(v) => {
          setTexto(v);
          if (erro) setErro(null);
        }}
        aoEnviar={enviar}
        max={MAX_RESPOSTA}
        rotulo="Responder ao Claude"
        placeholder="Quer pedir mais alguma coisa? Escreva aqui."
        desabilitado={responder.isPending}
        linhas={2}
        alturaMax={240}
      >
        <Botao onClick={enviar} disabled={!limpo} enviando={responder.isPending} textoEnviando="Enviando…" icone={<Send size={14} aria-hidden="true" />}>
          Responder
        </Botao>
      </CaixaTexto>
      {erro && (
        <p role="alert" className="text-sm break-words text-[var(--color-error)]">
          {erro}
        </p>
      )}
    </div>
  );
}
