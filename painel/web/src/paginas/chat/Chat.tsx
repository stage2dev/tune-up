// Tela inicial: o dono escreve o que quer, escolhe o tamanho do pedido e manda.
// Cada nivel e uma acao do grupo "chat" de /api/acoes; mandar = POST /api/execucoes.
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { MessageSquare, Send } from 'lucide-react';
import { chaves, useAcoes, useExecucoes, useIniciarExecucao, useModelos } from '../../api/ganchos';
import type { Execucao } from '../../api/tipos';
import { Botao, Cartao, Dialogo, Erro, EsqueletoPagina, EstadoVazio, Pagina, useAvisos } from '../../componentes';
import { traduzirErroInicio, type ResultadoErro } from '../dev/logica';
import { CaixaTexto } from './CaixaTexto';
import { ListaConversas } from './ListaConversas';
import { SeletorNivel } from './SeletorNivel';
import { FRASE_CONFIRMAR, acoesDoChat, comecoDoPedido, destinoDaExecucao, limitePedido, nivelInicial } from './logica';

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

const TITULO = 'Chat';
const SUBTITULO = 'Escreva o que você quer. O Claude faz e te mostra.';

export default function Chat() {
  const acoes = useAcoes();
  const modelos = useModelos();
  const execucoes = useExecucoes();
  const iniciar = useIniciarExecucao();
  const qc = useQueryClient();
  const ir = useNavigate();
  const { avisar } = useAvisos();
  const [texto, setTexto] = useState('');
  const [escolhaFeita, setEscolhaFeita] = useState<string | null>(lerNivel);
  const [confirmar, setConfirmar] = useState(false);
  const [problema, setProblema] = useState<ResultadoErro | null>(null);

  if (acoes.isPending) return <Pagina titulo={TITULO} subtitulo={SUBTITULO}><EsqueletoPagina cartoes={2} /></Pagina>;
  if (acoes.isError) return <Pagina titulo={TITULO} subtitulo={SUBTITULO}><Erro erro={acoes.error} aoTentar={() => void acoes.refetch()} /></Pagina>;

  const niveis = acoesDoChat(acoes.data);
  if (niveis.length === 0) {
    return (
      <Pagina titulo={TITULO} subtitulo={SUBTITULO}>
        <EstadoVazio
          icone={<MessageSquare size={32} aria-hidden="true" />}
          titulo="O chat ainda não está disponível"
          texto="Este painel não trouxe nenhum tipo de pedido para o chat. Atualize o painel para a versão nova e abra esta página de novo."
        >
          <Link to="/resumo" className="text-sm underline text-[var(--color-accent)]">Ver o resumo</Link>
        </EstadoVazio>
      </Pagina>
    );
  }

  const nivelId = nivelInicial(niveis, escolhaFeita);
  const nivel = niveis.find((a) => a.id === nivelId) ?? niveis[0];
  const max = limitePedido(nivel);
  const pedido = texto.trim();
  // Sem /api/modelos (servidor antigo ou falha): status vazio = "nao consegui conferir", nunca "conferindo" para sempre.
  const status = modelos.isError ? {} : modelos.data;

  const escolher = (id: string) => {
    setEscolhaFeita(id);
    gravarNivel(id);
  };

  const mandar = () => {
    setProblema(null);
    iniciar.mutate(
      { acao: nivel.id, params: { pedido } },
      {
        onSuccess: (e) => {
          // Poe a conversa nova na lista ja, para a tela dela nao piscar "nao achei".
          qc.setQueryData<Execucao[]>(chaves.execucoes, (l) => (l?.some((x) => x.id === e.id) ? l : [e, ...(l ?? [])]));
          setConfirmar(false);
          setTexto('');
          avisar({ tipo: 'sucesso', titulo: 'Começou', texto: 'Vou te avisar quando terminar.' });
          ir(`/conversa/${encodeURIComponent(e.id)}`);
        },
        onError: (e) => {
          setConfirmar(false);
          setProblema(traduzirErroInicio(e));
        },
      },
    );
  };

  const enviar = () => {
    if (!pedido || iniciar.isPending) return;
    if (nivel.confirmar) setConfirmar(true);
    else mandar();
  };

  const conflito = problema?.tipo === 'conflito' ? problema.execucaoId : null;
  const outra = conflito ? execucoes.data?.find((e) => e.id === conflito) : undefined;
  const destinoConflito = conflito ? (outra ? destinoDaExecucao(outra) : `/execucoes/${encodeURIComponent(conflito)}`) : '';

  return (
    <Pagina titulo={TITULO} subtitulo={SUBTITULO}>
      <div className="grid gap-5">
        <Cartao>
          <div className="grid gap-3">
            <p className="text-base font-medium">Olá! O que você quer fazer hoje?</p>
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
              desabilitado={iniciar.isPending}
              autoFocus
            >
              <Botao onClick={enviar} disabled={!pedido} enviando={iniciar.isPending} textoEnviando="Enviando…" icone={<Send size={14} aria-hidden="true" />}>
                Enviar
              </Botao>
            </CaixaTexto>
            {problema && (
              <div
                role="alert"
                className="rounded-lg border p-3 text-sm"
                style={{
                  background: 'color-mix(in srgb, var(--color-attention) 12%, transparent)',
                  borderColor: 'color-mix(in srgb, var(--color-attention) 35%, transparent)',
                }}
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
            <SeletorNivel niveis={niveis} escolhido={nivel.id} aoEscolher={escolher} status={status} />
          </div>
        </Cartao>
        <ListaConversas niveis={niveis} />
      </div>
      <Dialogo
        aberto={confirmar}
        titulo={`${nivel.titulo}: pode começar?`}
        textoConfirmar="Começar"
        enviando={iniciar.isPending}
        aoFechar={() => setConfirmar(false)}
        aoConfirmar={mandar}
      >
        <p>{FRASE_CONFIRMAR[nivel.risco] ?? FRASE_CONFIRMAR.codigo}</p>
        <p className="break-words text-[var(--color-text)]">“{comecoDoPedido(pedido, 140)}”</p>
      </Dialogo>
    </Pagina>
  );
}
