import { ExternalLink, GitPullRequest } from 'lucide-react';
import { Link } from 'react-router';
import { Cartao, Selo } from '../../componentes';
import type { Acao, Execucao } from '../../api/tipos';
import { BotaoRodarParte } from './BotaoRodarParte';
import { contarPartes, itemTemAchado, parteAberta, SELO_PARTE, textoVolta } from './logica';
import type { Fase, Parte } from './tipos';

function PR({ pr }: { pr: NonNullable<Parte['pr']> }) {
  const rotulo = `PR #${pr.numero} · ${pr.estado === 'MERGED' ? 'mergeada' : pr.estado === 'OPEN' ? 'aberta' : pr.estado === 'CLOSED' ? 'fechada' : 'citada'}`;
  const cls = 'inline-flex items-center gap-1 text-xs text-[var(--color-accent)]';
  return pr.url ? (
    <a className={`${cls} underline`} href={pr.url} target="_blank" rel="noreferrer noopener">
      <GitPullRequest size={12} aria-hidden="true" />
      {rotulo}
      <ExternalLink size={10} aria-hidden="true" />
    </a>
  ) : (
    <span className={cls}>
      <GitPullRequest size={12} aria-hidden="true" />
      {rotulo}
    </span>
  );
}

function LinhaParte({ fase, parte, acao, execucao }: { fase: Fase; parte: Parte; acao?: Acao; execucao?: Execucao }) {
  const selo = SELO_PARTE[parte.status] ?? SELO_PARTE.pendente;
  const achados = parte.itens.filter(itemTemAchado);
  return (
    <li className="rounded-lg border border-[var(--color-border)] p-3 grid grid-cols-1 gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">Parte {parte.id}</span>
        <Selo estado={parte.status} rotulo={selo.rotulo} tom={selo.tom} />
        {parte.parcial && <Selo estado="parcial" rotulo="Só uma parte feita" tom="atencao" />}
        {parte.itens_plano && <span className="text-xs text-[var(--color-text-secondary)]">itens {parte.itens_plano}</span>}
        <span className="flex-1" />
        {execucao && (
          <Link className="text-xs underline text-[var(--color-accent)]" to={`/execucoes/${encodeURIComponent(execucao.id)}`}>
            Ver execução
          </Link>
        )}
        {parteAberta(parte) && <BotaoRodarParte fase={fase.numero} parte={parte.id} acao={acao} />}
      </div>
      {parte.pr && <PR pr={parte.pr} />}
      {achados.length > 0 && (
        <ul className="grid grid-cols-1 gap-1 text-xs text-[var(--color-text-secondary)]" aria-label={`Achados da Parte ${parte.id}`}>
          {achados.map((i) => (
            <li key={i.id}>
              <span className="font-medium text-[var(--color-text)]">{i.id}</span> · {i.voltas.map(textoVolta).join(' → ')}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

interface Props {
  fase: Fase;
  acaoRodar?: Acao;
  execucoes: Execucao[];
}

export function FaseCartao({ fase, acaoRodar, execucoes }: Props) {
  const { fechadas, total } = contarPartes(fase);
  const ativa = (p: Parte) => execucoes.find((e) => e.fase === fase.numero && e.parte === p.id && (e.estado === 'rodando' || e.estado === 'precisa_de_voce'));
  return (
    <Cartao
      como="article"
      titulo={fase.titulo ?? `Fase ${fase.numero}`}
      acao={
        fase.acompanhada ? (
          <span className="text-xs text-[var(--color-text-secondary)] whitespace-nowrap">
            {fechadas}/{total} Partes
          </span>
        ) : undefined
      }
    >
      {!fase.acompanhada ? (
        <p className="text-sm text-[var(--color-text-secondary)]">Esta fase não tem arquivo de progresso.</p>
      ) : (
        <>
          {total > 0 && (
            <div className="h-1.5 rounded-full bg-[var(--color-bg-tertiary)] mb-3" role="img" aria-label={`${fechadas} de ${total} Partes fechadas`}>
              <div className="h-full rounded-full bg-[var(--color-success)]" style={{ width: `${(fechadas / total) * 100}%` }} />
            </div>
          )}
          {fase.partes.length === 0 ? (
            <p className="text-sm text-[var(--color-text-secondary)]">Nenhuma Parte listada ainda.</p>
          ) : (
            <ul className="grid grid-cols-1 gap-2">
              {fase.partes.map((p) => (
                <LinhaParte key={p.id} fase={fase} parte={p} acao={acaoRodar} execucao={ativa(p)} />
              ))}
            </ul>
          )}
          {fase.precisa.length > 0 && (
            <ul className="mt-3 grid grid-cols-1 gap-1 text-xs">
              {fase.precisa.map((q) => (
                <li key={q.linha} className="text-[var(--color-attention)] break-words">
                  Precisa de você{q.parte ? ` (Parte ${q.parte})` : ''}: <span className="text-[var(--color-text)]">{q.texto}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Cartao>
  );
}
