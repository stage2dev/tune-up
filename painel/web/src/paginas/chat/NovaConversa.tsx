// Centro da tela sem conversa escolhida: saudacao, caixa e nivel. Ao enviar, nao sai da tela:
// o balao do pedido aparece com "comecando…" e a URL vira /conversa/<id> (replace).
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Send } from 'lucide-react';
import { chaves, useExecucoes, useIniciarExecucao, useModelos } from '../../api/ganchos';
import type { Acao, Execucao } from '../../api/tipos';
import { Botao, Dialogo } from '../../componentes';
import { traduzirErroInicio, type ResultadoErro } from '../dev/logica';
import { Baloes } from './Baloes';
import { CaixaTexto } from './CaixaTexto';
import { SeletorNivel } from './SeletorNivel';
import { FRASE_CONFIRMAR, comecoDoPedido, destinoDaExecucao, limitePedido, montarConversa, nivelInicial } from './logica';

const CHAVE_NIVEL = 'painel.chat.nivel';

function lerNivel(): string | null {
  try {
    return window.localStorage.getItem(CHAVE_NIVEL);
  } catch {
    return null;
  }
}
function gravarNivel(id: string): void {
  try {
    window.localStorage.setItem(CHAVE_NIVEL, id);
  } catch {
    /* sem localStorage (modo privado): so nao lembra */
  }
}

export function NovaConversa({ niveis }: { niveis: Acao[] }) {
  const modelos = useModelos();
  const execucoes = useExecucoes();
  const iniciar = useIniciarExecucao();
  const qc = useQueryClient();
  const ir = useNavigate();
  const [texto, setTexto] = useState('');
  const [escolhaFeita, setEscolhaFeita] = useState<string | null>(lerNivel);
  const [confirmar, setConfirmar] = useState(false);
  const [problema, setProblema] = useState<ResultadoErro | null>(null);

  const nivel = niveis.find((a) => a.id === nivelInicial(niveis, escolhaFeita)) ?? niveis[0];
  const max = limitePedido(nivel);
  const pedido = texto.trim();
  // Sem /api/modelos (servidor antigo ou falha): status vazio = "nao consegui conferir", nunca "conferindo" para sempre.
  const status = modelos.isError ? {} : modelos.data;

  const mandar = () => {
    setProblema(null);
    setConfirmar(false);
    iniciar.mutate(
      { acao: nivel.id, params: { pedido } },
      {
        onSuccess: (e) => {
          // A conversa nova entra na lista ja, para a tela dela nao piscar "nao achei".
          qc.setQueryData<Execucao[]>(chaves.execucoes, (l) => (l?.some((x) => x.id === e.id) ? l : [e, ...(l ?? [])]));
          setTexto('');
          ir(`/conversa/${encodeURIComponent(e.id)}`, { replace: true });
        },
        onError: (e) => setProblema(traduzirErroInicio(e)),
      },
    );
  };

  const enviar = () => {
    if (!pedido || iniciar.isPending) return;
    if (nivel.confirmar) setConfirmar(true);
    else mandar();
  };

  // Enviando: a conversa ja aparece no lugar, com o balao do pedido.
  if (iniciar.isPending) {
    return (
      <div className="flex-1 min-h-0 flex flex-col w-full max-w-3xl mx-auto p-3 md:p-4 gap-3">
        <p className="text-sm font-semibold">{nivel.titulo}</p>
        <Baloes itens={montarConversa(pedido, [])} trabalhando="começando…" />
        <CaixaTexto valor="" aoMudar={() => {}} aoEnviar={() => {}} max={max} rotulo="Escreva aqui" placeholder="começando…" desabilitado linhas={2} />
      </div>
    );
  }

  const conflito = problema?.tipo === 'conflito' ? problema.execucaoId : null;
  const outra = conflito ? execucoes.data?.find((e) => e.id === conflito) : undefined;
  const destinoConflito = conflito ? (outra ? destinoDaExecucao(outra) : `/execucoes/${encodeURIComponent(conflito)}`) : '';

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="w-full max-w-3xl mx-auto p-3 md:p-6 grid gap-4">
        <div>
          <h1 className="text-xl font-semibold">Olá! O que você quer fazer hoje?</h1>
          <p className="text-sm text-[var(--color-text-secondary)]">Escreva o que você quer. O Claude faz e te mostra aqui mesmo.</p>
        </div>
        <SeletorNivel niveis={niveis} escolhido={nivel.id} aoEscolher={(id) => (setEscolhaFeita(id), gravarNivel(id))} status={status} />
        <CaixaTexto
          valor={texto}
          aoMudar={(v) => {
            setTexto(v);
            if (problema) setProblema(null);
          }}
          aoEnviar={enviar}
          max={max}
          rotulo="Escreva o seu pedido"
          placeholder="Ex.: muda o texto do botão, faz um post sobre a promoção, por que a IA não respondeu?"
          autoFocus
        >
          <Botao onClick={enviar} disabled={!pedido} icone={<Send size={14} aria-hidden="true" />}>
            Enviar
          </Botao>
        </CaixaTexto>
        {problema && (
          <div
            role="alert"
            className="rounded-lg border p-3 text-sm"
            style={{ background: 'color-mix(in srgb, var(--color-attention) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--color-attention) 35%, transparent)' }}
          >
            {conflito && <p className="font-medium">Já tem um pedido assim rodando.</p>}
            <p className="break-words">{problema.texto}</p>
            {conflito && (
              <Link className="underline text-[var(--color-accent)]" to={destinoConflito}>
                Abrir esse pedido
              </Link>
            )}
          </div>
        )}
        <p className="text-xs text-[var(--color-text-tertiary)]">Enter envia. Shift + Enter pula linha.</p>
      </div>
      <Dialogo aberto={confirmar} titulo={`${nivel.titulo}: pode começar?`} textoConfirmar="Começar" aoFechar={() => setConfirmar(false)} aoConfirmar={mandar}>
        <p>{FRASE_CONFIRMAR[nivel.risco] ?? FRASE_CONFIRMAR.codigo}</p>
        <p className="break-words text-[var(--color-text)]">“{comecoDoPedido(pedido, 140)}”</p>
      </Dialogo>
    </div>
  );
}
