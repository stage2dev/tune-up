import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { ArrowLeft, Copy, SquareTerminal, StopCircle, Clock } from 'lucide-react';
import { useAbrirNoTerminal, useEventos, useExecucoes, useModulos, usePararExecucao } from '../../api/ganchos';
import { Botao, Cartao, Dialogo, Erro, EsqueletoPagina, EstadoVazio, Pagina, Selo, useAvisos } from '../../componentes';
import { LinhaDoTempo } from './LinhaDoTempo';
import { emAndamento, estadoEmPalavras, moduloDaExecucao, paraMs, tempoDecorrido, ultimoSinal } from './logica';
import { useAgora } from './useAgora';

export default function ExecucaoDetalhe() {
  const { id = '' } = useParams();
  const lista = useExecucoes();
  const eventos = useEventos(id);
  const abrir = useAbrirNoTerminal();
  const parar = usePararExecucao();
  const modulos = useModulos();
  const navegar = useNavigate();
  const { avisar } = useAvisos();
  const [confirmaParar, setConfirmaParar] = useState(false);
  const [comando, setComando] = useState<string | null>(null);

  const exec = lista.data?.find((e) => e.id === id);
  const estado = eventos.data?.estado ?? exec?.estado;
  const agora = useAgora(estado === 'rodando' || estado === 'precisa_de_voce');
  const voltar = (
    <Link to="/execucoes" className="inline-flex items-center gap-1 text-sm text-[var(--color-accent)] mb-3">
      <ArrowLeft size={14} aria-hidden="true" />
      Todas as execuções
    </Link>
  );

  if (lista.isPending || modulos.isPending) return <Pagina titulo="Execução">{voltar}<EsqueletoPagina cartoes={2} /></Pagina>;
  if (lista.isError) return <Pagina titulo="Execução">{voltar}<Erro erro={lista.error} aoTentar={() => void lista.refetch()} /></Pagina>;
  if (!exec) return <Pagina titulo="Execução">{voltar}<EstadoVazio titulo="Não achei esta execução" texto="Ela pode ter sido apagada." /></Pagina>;

  const ativa = estado ? estado === 'rodando' || estado === 'precisa_de_voce' : emAndamento(exec);
  const fim = ativa ? agora : (ultimoSinal(eventos.data?.eventos ?? []) ?? paraMs(exec.iniciada_em) ?? agora);
  const cmd = comando ?? exec.comando_attach;
  const mod = moduloDaExecucao(exec, modulos.data?.modulos); // ação de módulo/plugin: estado em palavras primeiro

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
        avisar({ tipo: 'info', titulo: 'Mandei parar', texto: exec.titulo });
      },
      onError: (e) => {
        setConfirmaParar(false);
        avisar({ tipo: 'erro', titulo: 'Não consegui parar', texto: e.message });
      },
    });

  const controles = (
    <Cartao className="mb-4" titulo="Controles" icone={<Clock size={16} aria-hidden="true" />} acao={<span className="text-sm tabular-nums" aria-label="Tempo">{tempoDecorrido(exec.iniciada_em, fim)}</span>}>
      <div className="flex flex-wrap gap-2">
        <Botao icone={<SquareTerminal size={14} aria-hidden="true" />} enviando={abrir.isPending} textoEnviando="Abrindo…" onClick={abrirTerminal}>
          Abrir no terminal
        </Botao>
        {ativa && !mod && (
          <Botao variante="perigo" icone={<StopCircle size={14} aria-hidden="true" />} onClick={() => setConfirmaParar(true)}>
            Parar
          </Botao>
        )}
      </div>
      <div className="mt-3 flex items-center gap-2 min-w-0">
        <code className="flex-1 min-w-0 truncate rounded bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs font-mono select-all">{cmd}</code>
        <Botao variante="fantasma" className="h-8 px-2" aria-label="Copiar comando" onClick={copiar} icone={<Copy size={14} aria-hidden="true" />} />
      </div>
    </Cartao>
  );

  return (
    <Pagina titulo={exec.titulo} subtitulo={exec.nome} acoes={estado && <Selo estado={estado} />}>
      {voltar}
      {mod && (
        <Cartao className="mb-4" titulo="O que está acontecendo">
          <p role="status" className="text-sm">{estadoEmPalavras(estado, mod.titulo)}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Botao icone={<ArrowLeft size={14} aria-hidden="true" />} onClick={() => void navegar(`/m/${encodeURIComponent(mod.id)}`)}>
              Voltar para {mod.titulo}
            </Botao>
            {ativa && (
              <Botao variante="perigo" icone={<StopCircle size={14} aria-hidden="true" />} onClick={() => setConfirmaParar(true)}>
                Parar
              </Botao>
            )}
          </div>
        </Cartao>
      )}
      {!mod && estado === 'precisa_de_voce' && (
        <div
          role="status"
          className="mb-4 rounded-lg border p-3 text-sm"
          style={{ background: 'var(--color-attention-subtle)', borderColor: 'color-mix(in srgb, var(--color-attention) 40%, transparent)' }}
        >
          <p className="font-medium">A sessão está esperando uma resposta sua.</p>
          <p className="text-[var(--color-text-secondary)]">Clique em “Abrir no terminal” para ver a pergunta e responder.</p>
        </div>
      )}
      {mod ? (
        <details className="mb-4 text-sm">
          <summary className="cursor-pointer text-[var(--color-text-secondary)]">Detalhes técnicos</summary>
          <div className="mt-2">{controles}</div>
        </details>
      ) : (
        controles
      )}
      {eventos.isPending ? (
        <EsqueletoPagina cartoes={2} />
      ) : eventos.isError ? (
        <Erro erro={eventos.error} aoTentar={() => void eventos.refetch()} />
      ) : (
        <LinhaDoTempo
          eventos={eventos.data.eventos}
          vazio={ativa ? 'A sessão ainda não escreveu nada. Isso é normal no começo.' : 'Esta sessão não deixou mensagens para mostrar.'}
        />
      )}
      <Dialogo aberto={confirmaParar} perigo titulo="Parar esta execução?" textoConfirmar="Parar" enviando={parar.isPending} aoFechar={() => setConfirmaParar(false)} aoConfirmar={confirmarParar}>
        <p>A sessão do Claude vai ser interrompida. O que ela já fez continua nos arquivos.</p>
      </Dialogo>
    </Pagina>
  );
}
