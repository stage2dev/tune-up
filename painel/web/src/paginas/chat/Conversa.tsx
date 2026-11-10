// Uma conversa do chat = uma execucao. Eventos com ?inteiro=1; resposta continua a mesma sessao.
import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router';
import { ArrowLeft, Copy, SquareTerminal, StopCircle } from 'lucide-react';
import { useAbrirNoTerminal, useAcoes, useEventos, useExecucoes, usePararExecucao } from '../../api/ganchos';
import { Botao, Dialogo, Erro, EsqueletoPagina, EstadoVazio, Pagina, Selo, useAvisos } from '../../componentes';
import { estadoFinal } from '../../api/eventos';
import { Baloes } from './Baloes';
import { Resposta } from './Resposta';
import { comQueSaiu, montarConversa } from './logica';

const voltar = (
  <Link to="/" className="inline-flex items-center gap-1 text-sm text-[var(--color-accent)] mb-3">
    <ArrowLeft size={14} aria-hidden="true" />
    Voltar ao chat
  </Link>
);

function Faixa({ tom, children }: { tom: 'atencao' | 'erro'; children: ReactNode }) {
  const cor = tom === 'atencao' ? 'var(--color-attention)' : 'var(--color-error)';
  return (
    <div
      role="status"
      className="rounded-lg border p-3 text-sm grid gap-2"
      style={{ background: `color-mix(in srgb, ${cor} 10%, transparent)`, borderColor: `color-mix(in srgb, ${cor} 35%, transparent)` }}
    >
      {children}
    </div>
  );
}

export default function Conversa() {
  const { id = '' } = useParams();
  const lista = useExecucoes();
  const acoes = useAcoes();
  const eventos = useEventos(id, true);
  const abrir = useAbrirNoTerminal();
  const parar = usePararExecucao();
  const { avisar } = useAvisos();
  const [confirmaParar, setConfirmaParar] = useState(false);
  const [comando, setComando] = useState<string | null>(null);

  const exec = lista.data?.find((e) => e.id === id);
  const estadoLista = exec?.estado;
  const estadoEventos = eventos.data?.estado;
  // A lista diz que voltou a rodar (resposta mandada de outro lugar) e os eventos tinham parado: busca de novo.
  const listaAtiva = estadoLista === 'rodando' || estadoLista === 'precisa_de_voce';
  const refazer = eventos.refetch;
  useEffect(() => {
    if (listaAtiva && estadoFinal(estadoEventos)) void refazer();
  }, [listaAtiva, estadoEventos, refazer]);

  if (lista.isPending) return <Pagina titulo="Conversa">{voltar}<EsqueletoPagina cartoes={2} /></Pagina>;
  if (lista.isError) return <Pagina titulo="Conversa">{voltar}<Erro erro={lista.error} aoTentar={() => void lista.refetch()} /></Pagina>;
  if (!exec) {
    return (
      <Pagina titulo="Conversa">
        <EstadoVazio titulo="Não achei esta conversa" texto="Ela pode ter sido apagada ou o painel foi reiniciado.">
          <Link to="/" className="text-sm underline text-[var(--color-accent)]">Voltar ao chat</Link>
        </EstadoVazio>
      </Pagina>
    );
  }

  const estado = listaAtiva && estadoFinal(estadoEventos) ? exec.estado : (estadoEventos ?? exec.estado);
  const ativa = estado === 'rodando' || estado === 'precisa_de_voce';
  const nivel = acoes.data?.find((a) => a.id === exec.acao)?.titulo ?? exec.titulo;
  const saiu = comQueSaiu(exec);
  const cmd = comando ?? exec.comando_attach;

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

  const botaoTerminal = (
    <Botao variante="secundario" icone={<SquareTerminal size={14} aria-hidden="true" />} enviando={abrir.isPending} textoEnviando="Abrindo…" onClick={abrirTerminal}>
      Abrir no terminal
    </Botao>
  );

  let fim = null;
  if (estado === 'precisa_de_voce') {
    fim = (
      <Faixa tom="atencao">
        <p className="font-medium">O Claude fez uma pergunta e está esperando você.</p>
        <p className="text-[var(--color-text-secondary)]">Abra no terminal para ver a pergunta e responder.</p>
        <div>{botaoTerminal}</div>
      </Faixa>
    );
  } else if (estado === 'sumiu') {
    fim = (
      <Faixa tom="erro">
        <p className="font-medium">Esta conversa não está mais disponível.</p>
        <p className="text-[var(--color-text-secondary)]">
          A sessão do Claude sumiu. Você pode <Link to="/" className="underline text-[var(--color-accent)]">começar um pedido novo no chat</Link>.
        </p>
      </Faixa>
    );
  }

  return (
    <Pagina titulo={nivel} subtitulo={saiu || undefined} acoes={<Selo estado={estado} />}>
      {voltar}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {ativa && (
          <Botao variante="perigo" icone={<StopCircle size={14} aria-hidden="true" />} onClick={() => setConfirmaParar(true)}>
            Parar
          </Botao>
        )}
        {botaoTerminal}
        <Link to={`/execucoes/${encodeURIComponent(exec.id)}`} className="text-sm underline text-[var(--color-text-secondary)] hover:text-[var(--color-text)]">
          ver detalhes técnicos
        </Link>
      </div>
      {comando && (
        <div className="mb-3 flex items-center gap-2 min-w-0">
          <code className="flex-1 min-w-0 truncate rounded bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs font-mono select-all">{cmd}</code>
          <Botao variante="fantasma" className="h-8 px-2" aria-label="Copiar comando" onClick={copiar} icone={<Copy size={14} aria-hidden="true" />} />
        </div>
      )}
      {eventos.isPending ? (
        <EsqueletoPagina cartoes={2} />
      ) : eventos.isError ? (
        <Erro erro={eventos.error} aoTentar={() => void eventos.refetch()} />
      ) : (
        <Baloes itens={montarConversa(exec.params?.pedido, eventos.data.eventos)} trabalhando={estado === 'rodando'} rodape={fim} />
      )}
      {!eventos.isPending && (estado === 'terminou' || estado === 'parada') && (
        <div className="mt-3">
          {exec.pode_responder ? (
            <Resposta id={exec.id} />
          ) : (
            <p className="text-xs text-[var(--color-text-secondary)]">Esta conversa não aceita resposta. Para pedir outra coisa, use o chat.</p>
          )}
        </div>
      )}
      <Dialogo aberto={confirmaParar} perigo titulo="Parar este pedido?" textoConfirmar="Parar" enviando={parar.isPending} aoFechar={() => setConfirmaParar(false)} aoConfirmar={confirmarParar}>
        <p>O Claude vai parar de trabalhar agora. O que ele já fez continua salvo.</p>
      </Dialogo>
    </Pagina>
  );
}
