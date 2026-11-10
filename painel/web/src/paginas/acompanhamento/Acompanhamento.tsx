// Tela de Acompanhamento: as listas de trabalho, separadas pelas areas que o servidor informa.
import { useState, type ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import { useAcompanhamento } from '../../api/ganchos';
import type { ItemLista, ListaAcompanhamento } from '../../api/tipos';
import { Botao, Cartao, Erro, EsqueletoPagina, EstadoVazio, Pagina, Selo } from '../../componentes';
import { atualizadoHa, cortar, linkSeguro } from '../modulo/formato';
import { areasDe, contarPorArea, filtrarListas, ordenarItens, resumoItens, TODAS } from './listas';

const POR_VEZ = 20;
function Notas({ texto }: { texto: string }) {
  if (!texto.trim()) return null;
  if (texto.length <= 220) return <p className="text-xs text-[var(--color-text-secondary)] mt-1 break-words whitespace-pre-line">{texto}</p>;
  return (
    <details className="mt-1 text-xs text-[var(--color-text-secondary)]">
      <summary className="cursor-pointer break-words">{cortar(texto, 220)}</summary>
      <p className="mt-1 break-words whitespace-pre-line">{texto}</p>
    </details>
  );
}

function Produtos({ produtos }: { produtos: ItemLista['produtos'] }) {
  if (produtos.length === 0) return null;
  return (
    <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs">
      {produtos.map((p, i) => {
        const url = linkSeguro(p.url);
        const nome = p.titulo || p.url;
        return (
          <li key={`${p.url}-${i}`} className="min-w-0 max-w-full">
            {url ? (
              <a href={url} target="_blank" rel="noopener noreferrer" className="text-[var(--color-accent)] inline-flex items-center gap-1 break-all">
                {cortar(nome, 60)} <ExternalLink size={12} aria-hidden="true" />
              </a>
            ) : (
              <span className="text-[var(--color-text-secondary)] break-all" title="Arquivo no seu computador">{cortar(nome, 60)}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Item({ i }: { i: ItemLista }) {
  return (
    <li className="py-2.5 border-b border-[var(--color-border-subtle)] last:border-0 min-w-0">
      <div className="flex flex-wrap items-start gap-x-2 gap-y-1">
        <Selo estado={i.status} />
        <span className="text-sm min-w-0 flex-1 basis-56 break-words">{i.tarefa}</span>
        <span className="text-xs text-[var(--color-text-tertiary)]">{atualizadoHa(i.atualizado_em)}</span>
      </div>
      <Notas texto={i.notas} />
      <Produtos produtos={i.produtos} />
    </li>
  );
}

function Lista({ l, rotuloArea }: { l: ListaAcompanhamento; rotuloArea: string }) {
  const r = resumoItens(l.itens);
  const estado = Object.entries(l.estado ?? {});
  return (
    <Cartao
      titulo={l.nome}
      acao={<Selo estado={l.aberta ? 'doing' : 'done'} rotulo={l.aberta ? 'Aberta' : 'Fechada'} tom={l.aberta ? 'destaque' : 'neutro'} />}
    >
      <p className="text-xs text-[var(--color-text-secondary)] mb-1">
        {rotuloArea} · {r.total === 0 ? 'sem itens' : `${r.feitos} de ${r.total} feitos`}
        {r.fazendo > 0 && ` · ${r.fazendo} fazendo`} · {atualizadoHa(l.atualizado_em)}
      </p>
      {l.itens.length > 0 && <ul>{ordenarItens(l.itens).map((i, k) => <Item key={`${i.tarefa}-${k}`} i={i} />)}</ul>}
      {estado.length > 0 && (
        <details className="mt-2 text-xs text-[var(--color-text-secondary)]">
          <summary className="cursor-pointer">Anotações da lista ({estado.length})</summary>
          <dl className="mt-1 grid gap-1">
            {estado.map(([k, v]) => (
              <div key={k} className="min-w-0">
                <dt className="font-medium break-words">{k}</dt>
                <dd className="break-words">{cortar(String(v), 400)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </Cartao>
  );
}

export default function Acompanhamento() {
  const q = useAcompanhamento();
  const [area, setArea] = useState<string>(TODAS);
  const [fechadas, setFechadas] = useState(false);
  const [limite, setLimite] = useState(POR_VEZ);

  const moldura = (corpo: ReactNode) => (
    <Pagina titulo="Acompanhamento" subtitulo="As listas de trabalho em andamento: o que falta fazer e o que já foi feito.">{corpo}</Pagina>
  );

  if (q.isPending) return moldura(<EsqueletoPagina cartoes={3} />);
  if (q.isError) return moldura(<Erro erro={q.error} aoTentar={() => void q.refetch()} />);

  const todas = q.data.listas;
  const areas = areasDe(todas, q.data.areas);
  const titulos = new Map(areas.map((a) => [a.id, a.titulo]));
  const filtros = [{ id: TODAS, titulo: 'Todas' }, ...(areas.length > 1 ? areas : [])];
  const contagem = contarPorArea(todas, fechadas);
  const listas = filtrarListas(todas, area, fechadas, areas);
  const mostradas = listas.slice(0, limite);

  return moldura(
    <div className="grid gap-3 grid-cols-[minmax(0,1fr)]">
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Filtrar por área" className="flex flex-wrap gap-1.5">
          {filtros.map((f) => (
            <Botao key={f.id} variante={area === f.id ? 'primario' : 'secundario'} aria-pressed={area === f.id} onClick={() => { setArea(f.id); setLimite(POR_VEZ); }}>
              {f.titulo} ({contagem[f.id] ?? 0})
            </Botao>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm ml-auto">
          <input type="checkbox" checked={fechadas} onChange={(e) => { setFechadas(e.target.checked); setLimite(POR_VEZ); }} />
          Mostrar fechadas
        </label>
      </div>
      {q.data.avisos.length > 0 && (
        <Cartao titulo="Avisos">
          <ul className="list-disc pl-4 text-xs text-[var(--color-text-secondary)] grid gap-0.5">
            {q.data.avisos.map((a) => <li key={a} className="break-words">{a}</li>)}
          </ul>
        </Cartao>
      )}
      {listas.length === 0 ? (
        <Cartao>
          <EstadoVazio titulo={fechadas ? 'Nenhuma lista aqui' : 'Nenhuma lista aberta aqui'} texto={fechadas ? 'Troque o filtro de área para ver outras.' : 'Marque "Mostrar fechadas" para ver as que já terminaram.'} />
        </Cartao>
      ) : (
        <>
          {mostradas.map((l) => <Lista key={l.nome} l={l} rotuloArea={titulos.get(l.area || 'geral') ?? 'Geral'} />)}
          {listas.length > limite && (
            <Botao variante="secundario" onClick={() => setLimite((n) => n + POR_VEZ)}>
              Mostrar mais ({listas.length - limite} listas)
            </Botao>
          )}
        </>
      )}
    </div>,
  );
}
