// Cartao-raiz de uma sessao do Claude, com os grupos (diretos e workflows) pendurados abaixo.
import { Link } from 'react-router';
import { Bot, ExternalLink, GitBranch, Terminal, Workflow } from 'lucide-react';
import type { GrupoAgentes, SessaoClaude } from '../../api/agentes';
import { Selo } from '../../componentes';
import { contarAtivos, montarArvore, porFase, seloSessao, tempoDesde, TIPO_SESSAO } from './logica';
import { NoAgente } from './NoAgente';
import { BotaoRecolher, ChipModelo, MedidorEsforco } from './pecas';

export interface Recolhimento {
  recolhido: (chave: string) => boolean;
  alternar: (chave: string) => void;
}

const idDom = (t: string) => `ag-${t.replace(/[^a-zA-Z0-9_-]/g, '_')}`;

function Arvore({ agentes, agora, rotulo }: { agentes: GrupoAgentes['agentes']; agora: number; rotulo: string }) {
  if (agentes.length === 0) return <p className="text-xs text-[var(--color-text-tertiary)] pl-5 pt-2">Nenhum agente aqui.</p>;
  return (
    <ul className="ag-arvore" aria-label={rotulo}>
      {montarArvore(agentes).map((no) => <NoAgente key={no.agente.id} no={no} agora={agora} />)}
    </ul>
  );
}

function Grupo({ g, chave, agora, rec }: { g: GrupoAgentes; chave: string; agora: number; rec: Recolhimento }) {
  const aberto = !rec.recolhido(chave);
  const ativos = contarAtivos(g.agentes);
  const nome = g.tipo === 'direto' ? 'Agentes diretos' : g.nome || 'Workflow';
  const corpo = idDom(chave);
  return (
    <li className="ag-ramo pt-3" data-grupo={g.id}>
      <div className="flex items-center gap-2 min-w-0">
        <BotaoRecolher aberto={aberto} aoAlternar={() => rec.alternar(chave)} rotulo={nome} controla={corpo} />
        <span className="text-[var(--color-text-tertiary)] shrink-0" aria-hidden="true">
          {g.tipo === 'workflow' ? <Workflow size={14} /> : <GitBranch size={14} />}
        </span>
        <h4 className="text-sm font-semibold truncate">{nome}</h4>
        {g.tipo === 'workflow' && g.fases.length > 0 && (
          <span className="text-xs text-[var(--color-text-tertiary)] shrink-0">{g.fases.length === 1 ? '1 fase' : `${g.fases.length} fases`}</span>
        )}
        <span className="ml-auto text-xs tabular-nums text-[var(--color-text-secondary)] shrink-0">
          {ativos} de {g.agentes.length} {ativos === 1 ? 'ativo' : 'ativos'}
        </span>
      </div>
      {aberto && (
        <div id={corpo}>
          {g.tipo === 'workflow' && g.fases.length > 0 ? (
            <div className="ag-colunas mt-2 pb-1">
              {porFase(g).map((col, i) => (
                <section key={col.fase} className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-secondary)] p-2 min-w-0" aria-label={`Fase ${col.fase}`}>
                  <header className="flex items-center gap-2 px-1">
                    <span className="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-semibold bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] shrink-0">
                      {col.fase === 'Sem fase' ? '–' : i + 1}
                    </span>
                    <span className="text-xs font-semibold truncate flex-1">{col.fase}</span>
                    <span className="text-xs tabular-nums text-[var(--color-text-tertiary)]">{contarAtivos(col.agentes)}/{col.agentes.length}</span>
                  </header>
                  <Arvore agentes={col.agentes} agora={agora} rotulo={`Agentes da fase ${col.fase}`} />
                </section>
              ))}
            </div>
          ) : (
            <Arvore agentes={g.agentes} agora={agora} rotulo={`Agentes de ${nome}`} />
          )}
        </div>
      )}
    </li>
  );
}

export function CartaoSessao({ s, agora, rec }: { s: SessaoClaude; agora: number; rec: Recolhimento }) {
  const chave = `s:${s.id}`;
  const aberto = !rec.recolhido(chave);
  const corpo = idDom(chave);
  const nome = s.nome || `Sessão ${s.sessao_id.slice(0, 8)}`;
  const temAgentes = s.grupos.some((g) => g.agentes.length > 0);
  const TipoIcone = s.tipo === 'segundo_plano' ? Bot : Terminal;
  return (
    <article className="hud-panel p-3 md:p-4" data-sessao={s.id} aria-label={`Sessão ${nome}`}>
      <header className="flex items-start gap-2">
        <BotaoRecolher aberto={aberto} aoAlternar={() => rec.alternar(chave)} rotulo={`sessão ${nome}`} controla={corpo} />
        <div className="flex-1 min-w-0 grid gap-1.5">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
            <h3 className="text-base font-semibold truncate max-w-full">{nome}</h3>
            <Selo estado={s.estado} {...seloSessao(s.estado)} />
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-[var(--color-text-secondary)]">
            <span className="inline-flex items-center gap-1">
              <TipoIcone size={12} aria-hidden="true" />
              {TIPO_SESSAO[s.tipo] ?? s.tipo}
            </span>
            <ChipModelo modelo={s.modelo} />
            <MedidorEsforco esforco={s.esforco} />
            <span className="tabular-nums" title="Tempo desde o início">começou há {tempoDesde(s.iniciado_em, agora)}</span>
            <span className="tabular-nums font-medium text-[var(--color-text)]">
              {s.agentes_ativos} {s.agentes_ativos === 1 ? 'ativo' : 'ativos'} de {s.agentes_total}
            </span>
            {s.execucao_id && (
              <Link to={`/execucoes/${encodeURIComponent(s.execucao_id)}`} className="inline-flex items-center gap-1 text-[var(--color-accent)] hover:underline">
                ver conversa <ExternalLink size={12} aria-hidden="true" />
              </Link>
            )}
          </div>
        </div>
      </header>
      {aberto && (
        <div id={corpo} className="pl-2">
          {temAgentes ? (
            <ul className="ag-arvore" aria-label={`Grupos de agentes da sessão ${nome}`}>
              {s.grupos.filter((g) => g.agentes.length > 0).map((g) => (
                <Grupo key={g.id} g={g} chave={`${chave}|g:${g.id}`} agora={agora} rec={rec} />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-[var(--color-text-tertiary)] pl-7 pt-2">Sem sub-agentes por enquanto.</p>
          )}
        </div>
      )}
    </article>
  );
}
