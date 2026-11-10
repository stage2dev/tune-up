import { useState } from 'react';
import { Play } from 'lucide-react';
import { Botao, Dialogo } from '../../componentes';
import { AvisoProblema } from './AvisoProblema';
import { pedidoRodarParte } from './logica';
import { useRodar } from './useRodar';
import type { Acao } from '../../api/tipos';

interface Props {
  fase: string;
  parte: string;
  acao: Acao | undefined;
}

/** "Rodar Parte": abre a confirmacao em palavras simples e so depois envia. */
export function BotaoRodarParte({ fase, parte, acao }: Props) {
  const [aberto, setAberto] = useState(false);
  const { rodar, enviando, problema, limpar } = useRodar(() => setAberto(false));
  const fechar = () => {
    limpar();
    setAberto(false);
  };
  return (
    <>
      <Botao
        variante="secundario"
        className="h-8"
        icone={<Play size={14} aria-hidden="true" />}
        disabled={!acao}
        title={acao ? undefined : 'Esta ação não está disponível agora.'}
        onClick={() => setAberto(true)}
      >
        Rodar Parte
      </Botao>
      <Dialogo
        aberto={aberto}
        titulo={`Rodar a Parte ${parte} da Fase ${fase}?`}
        textoConfirmar="Rodar agora"
        enviando={enviando}
        aoFechar={fechar}
        aoConfirmar={() => rodar(pedidoRodarParte(fase, parte))}
      >
        <p>Uma sessão do Claude vai trabalhar no código desta Parte, sozinha, em segundo plano.</p>
        <p>Se ela precisar de você, o painel avisa. Você pode acompanhar tudo na tela da execução.</p>
        <AvisoProblema problema={problema} />
      </Dialogo>
    </>
  );
}
