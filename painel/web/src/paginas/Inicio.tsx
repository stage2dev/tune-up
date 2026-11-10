import { Link } from 'react-router';
import { AvisosDoLeitor } from './dev/AvisosDoLeitor';
import { AlertCircle, ArrowRight, CheckCircle2 } from 'lucide-react';
import { useEstado, useExecucoes } from '../api/ganchos';
import { Cartao, Erro, EsqueletoPagina, Pagina } from '../componentes';
import { Metrica } from './dev/Metrica';
import { juntarPrecisa, lerEstado } from './dev/logica';

export default function Inicio() {
  const estado = useEstado();
  const execucoes = useExecucoes();

  if (estado.isPending) return <Pagina titulo="Início"><EsqueletoPagina cartoes={3} /></Pagina>;
  if (estado.isError) return <Pagina titulo="Início"><Erro erro={estado.error} aoTentar={() => void estado.refetch()} /></Pagina>;
  const { estado: e, erro } = lerEstado(estado.data);
  if (!e) return <Pagina titulo="Início"><Erro erro={new Error(erro)} aoTentar={() => void estado.refetch()} /></Pagina>;

  const r = e.resumo;
  const exec = execucoes.data; // pode ainda nao ter chegado: nesse caso nao afirmamos numero
  const rodando = exec?.filter((x) => x.estado === 'rodando').length;
  const precisa = juntarPrecisa(e.precisa_de_voce, exec ?? []);
  const prsAbertas = e.prs.filter((p) => p.estado === 'OPEN');

  return (
    <Pagina titulo="Início" subtitulo="Um resumo do que está acontecendo agora.">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
        <Metrica rotulo="Fases abertas" valor={r.fases_abertas} detalhe={`de ${r.fases_acompanhadas} acompanhadas`} />
        <Metrica rotulo="Partes fechadas" valor={`${r.partes_fechadas}/${r.partes_total}`} />
        <Metrica rotulo="Precisa de você" valor={execucoes.isPending ? '…' : precisa.length} destaque={precisa.length > 0} />
        <Metrica rotulo="Execuções rodando" valor={execucoes.isPending ? '…' : (rodando ?? 0)} />
        <Metrica rotulo="PRs abertas" valor={r.prs_abertas} />
      </div>

      <Cartao
        className="mb-5"
        titulo="Precisa de você"
        icone={precisa.length > 0 ? <AlertCircle size={16} aria-hidden="true" /> : <CheckCircle2 size={16} aria-hidden="true" />}
      >
        {execucoes.isPending ? (
          <EsqueletoPagina cartoes={1} />
        ) : precisa.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary)]">Nada esperando por você agora.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-2">
            {precisa.map((p) => (
              <li key={p.chave}>
                <Link
                  to={p.para ?? '/fases'}
                  className="flex items-start gap-3 rounded-lg border p-3 hover:bg-[var(--color-bg-tertiary)] transition-colors"
                  style={{ borderColor: 'color-mix(in srgb, var(--color-attention) 40%, transparent)', background: 'var(--color-attention-subtle)' }}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium break-words">{p.titulo}</p>
                    <p className="text-sm text-[var(--color-text-secondary)] break-words">{p.texto}</p>
                  </div>
                  <ArrowRight size={16} aria-hidden="true" className="shrink-0 mt-0.5" />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {execucoes.isError && <p className="text-xs text-[var(--color-text-secondary)] mt-2">Não consegui ver as execuções agora; mostrando só o que está nos planos.</p>}
      </Cartao>

      {prsAbertas.length > 0 && (
        <Cartao className="mb-5" titulo={`PRs abertas (${prsAbertas.length})`}>
          <ul className="grid grid-cols-1 gap-1 text-sm">
            {prsAbertas.map((p) => (
              <li key={p.numero} className="break-words">
                {p.url ? (
                  <a className="underline text-[var(--color-accent)]" href={p.url} target="_blank" rel="noreferrer noopener">
                    #{p.numero}
                  </a>
                ) : (
                  <span>#{p.numero}</span>
                )}{' '}
                {p.titulo}
              </li>
            ))}
          </ul>
        </Cartao>
      )}

      <AvisosDoLeitor avisos={e.avisos} />
    </Pagina>
  );
}
