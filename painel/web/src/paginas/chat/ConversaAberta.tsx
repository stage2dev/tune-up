// Centro da tela com uma conversa: cabecalho, baloes e a caixa de baixo (Compositor).
// Eventos com ?inteiro=1; o terminal virou um link discreto.
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Copy } from 'lucide-react';
import { useAgentesDaSessao } from '../../api/agentes';
import { estadoFinal } from '../../api/eventos';
import { useAbrirNoTerminal, useEventos, useExecucoes, usePararExecucao } from '../../api/ganchos';
import type { Acao } from '../../api/tipos';
import { Botao, Dialogo, Erro, Esqueleto, EsqueletoPagina, EstadoVazio, Selo, useAvisos } from '../../componentes';
import { Baloes } from './Baloes';
import { Compositor } from './Compositor';
import { fraseTrabalhando, itensDoPainel, sessaoDaConversa } from './agentesChat';
import { comQueSaiu, grupoDe, GRUPO_CHAT, montarConversa } from './logica';
import type { SkillsDoPedido } from './useSkillsDoPedido';

const linkDiscreto = 'underline text-[var(--color-text-secondary)] hover:text-[var(--color-text)] disabled:opacity-60';

export function ConversaAberta({ id, niveis, skills }: { id: string; niveis: Acao[]; skills: SkillsDoPedido }) {
  const lista = useExecucoes();
  const eventos = useEventos(id, true);
  const abrir = useAbrirNoTerminal();
  const parar = usePararExecucao();
  const { avisar } = useAvisos();
  const [confirmaParar, setConfirmaParar] = useState(false);
  const [comando, setComando] = useState<string | null>(null);

  const exec = lista.data?.find((e) => e.id === id);
  const estadoLista = exec?.estado;
  const estadoEventos = eventos.data?.estado;
  const listaAtiva = estadoLista === 'rodando' || estadoLista === 'precisa_de_voce';
  const agentes = useAgentesDaSessao(id, listaAtiva);
  // A lista diz que voltou a rodar (resposta mandada) e os eventos tinham parado: busca de novo.
  const refazer = eventos.refetch;
  useEffect(() => {
    if (listaAtiva && estadoFinal(estadoEventos)) void refazer();
  }, [listaAtiva, estadoEventos, refazer]);

  if (lista.isPending) return <div className="p-4"><EsqueletoPagina cartoes={2} /></div>;
  if (lista.isError) return <div className="p-4"><Erro erro={lista.error} aoTentar={() => void lista.refetch()} /></div>;
  if (!exec) {
    return (
      <EstadoVazio titulo="Não achei esta conversa" texto="Ela pode ter sido apagada ou o painel foi reiniciado.">
        <Link to="/" className="text-sm underline text-[var(--color-accent)]">Começar uma conversa nova</Link>
      </EstadoVazio>
    );
  }

  const estado = listaAtiva && estadoFinal(estadoEventos) ? exec.estado : (estadoEventos ?? exec.estado);
  const ativa = estado === 'rodando' || estado === 'precisa_de_voce';
  const nivel = niveis.find((a) => a.id === exec.acao)?.titulo ?? exec.titulo;
  const saiu = comQueSaiu(exec);
  const cmd = comando ?? exec.comando_attach;
  const evs = eventos.data?.eventos ?? [];
  const ajudando = itensDoPainel(sessaoDaConversa(agentes.data, id)).ativos;
  const frase = estado !== 'rodando' ? null : exec.pode_interromper === false && !exec.pode_responder ? 'começando…' : fraseTrabalhando(evs, ajudando);

  const copiar = () => {
    try {
      void navigator.clipboard.writeText(cmd).then(
        () => avisar({ tipo: 'sucesso', titulo: 'Comando copiado' }),
        () => avisar({ tipo: 'atencao', titulo: 'Não consegui copiar', texto: 'Selecione o comando e copie à mão.' }),
      );
    } catch {
      avisar({ tipo: 'atencao', titulo: 'Não consegui copiar', texto: 'Selecione o comando e copie à mão.' });
    }
  };
  const abrirTerminal = () =>
    abrir.mutate(exec.id, {
      onSuccess: (r) => {
        setComando(r.comando);
        avisar(r.ok ? { tipo: 'sucesso', titulo: 'Abri o Terminal' } : { tipo: 'info', titulo: 'Copie o comando', texto: 'Cole no seu terminal.' });
      },
      onError: (e) => avisar({ tipo: 'erro', titulo: 'Não abriu o Terminal', texto: e.message }),
    });
  const confirmarParar = () =>
    parar.mutate(exec.id, {
      onSuccess: () => {
        setConfirmaParar(false);
        avisar({ tipo: 'info', titulo: 'Mandei parar', texto: nivel });
      },
      onError: (e) => {
        setConfirmaParar(false);
        avisar({ tipo: 'erro', titulo: 'Não consegui parar', texto: e.message });
      },
    });

  // Servidor antigo ou sessao sem chat: a espera so se resolve no terminal.
  // Pedido de permissao preso no terminal: so o terminal aprova (escrever no chat cancela o pedido).
  const soNoTerminal = estado === 'precisa_de_voce' && !exec.pode_responder && (!exec.pode_interromper || !!exec.espera_terminal);
  let fim = null;
  if (soNoTerminal) {
    fim = (
      <div role="status" className="rounded-lg border p-3 text-sm grid gap-2" style={{ background: 'var(--color-attention-subtle)', borderColor: 'color-mix(in srgb, var(--color-attention) 40%, transparent)' }}>
        <p className="font-medium">{exec.espera_terminal ? 'O Claude pediu uma permissão e está esperando no terminal.' : 'O Claude está esperando uma resposta no terminal.'}</p>
        <div>
          <Botao variante="secundario" enviando={abrir.isPending} textoEnviando="Abrindo…" onClick={abrirTerminal}>
            Abrir no terminal
          </Botao>
        </div>
      </div>
    );
  } else if (estado === 'sumiu') {
    fim = (
      <div role="status" className="rounded-lg border p-3 text-sm" style={{ background: 'color-mix(in srgb, var(--color-error) 8%, transparent)', borderColor: 'color-mix(in srgb, var(--color-error) 30%, transparent)' }}>
        <p className="font-medium">Esta conversa não está mais disponível.</p>
        <p className="text-[var(--color-text-secondary)]">
          A sessão do Claude sumiu. <Link to="/" className="underline text-[var(--color-accent)]">Comece uma conversa nova</Link>.
        </p>
      </div>
    );
  }
  const carregando = eventos.isPending ? (
    <div role="status" aria-label="Carregando a conversa" className="grid gap-2">
      <Esqueleto className="h-10 w-2/3" />
      <Esqueleto className="h-16 w-3/4" />
    </div>
  ) : null;

  return (
    <div className="flex-1 min-h-0 flex flex-col w-full max-w-3xl mx-auto p-3 md:p-4 gap-3">
      <header className="grid gap-1 shrink-0">
        <div className="flex items-start gap-2 min-w-0">
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold truncate">{nivel}</h1>
            {saiu && <p className="text-xs text-[var(--color-text-secondary)]">{saiu}</p>}
          </div>
          <Selo estado={estado} />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <Link to={`/execucoes/${encodeURIComponent(exec.id)}`} className={linkDiscreto}>ver detalhes técnicos</Link>
          <button type="button" className={linkDiscreto} onClick={abrirTerminal} disabled={abrir.isPending}>
            {abrir.isPending ? 'abrindo…' : 'abrir no terminal'}
          </button>
          {ativa && (
            <button type="button" className={linkDiscreto} onClick={() => setConfirmaParar(true)}>
              parar
            </button>
          )}
        </div>
        {comando && (
          <div className="flex items-center gap-2 min-w-0">
            <code className="flex-1 min-w-0 truncate rounded bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs font-mono select-all">{cmd}</code>
            <Botao variante="fantasma" className="h-8 px-2" aria-label="Copiar comando" onClick={copiar} icone={<Copy size={14} aria-hidden="true" />} />
          </div>
        )}
      </header>

      {eventos.isError ? (
        <Erro erro={eventos.error} aoTentar={() => void eventos.refetch()} />
      ) : (
        <Baloes itens={montarConversa(exec.params?.pedido, evs, exec.habilidades)} trabalhando={carregando ? null : frase} rodape={carregando ?? fim} />
      )}

      <div className="shrink-0">
        <Compositor key={exec.id} exec={exec} aoParar={() => setConfirmaParar(true)} skills={grupoDe(exec) === GRUPO_CHAT ? skills : undefined} />
      </div>

      <Dialogo aberto={confirmaParar} perigo titulo="Parar este pedido?" textoConfirmar="Parar" enviando={parar.isPending} aoFechar={() => setConfirmaParar(false)} aoConfirmar={confirmarParar}>
        <p>O Claude vai parar de trabalhar agora. O que ele já fez continua salvo.</p>
      </Dialogo>
    </div>
  );
}
