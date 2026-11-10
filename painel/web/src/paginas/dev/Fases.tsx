import { useState, type ReactNode } from 'react';
import { AvisosDoLeitor } from './AvisosDoLeitor';
import { ChevronDown, ChevronRight, Compass, Search } from 'lucide-react';
import { useAcoes, useEstado, useExecucoes } from '../../api/ganchos';
import { Botao, Erro, EsqueletoPagina, EstadoVazio, Pagina } from '../../componentes';
import { DialogoTexto } from './DialogoTexto';
import { FaseCartao } from './FaseCartao';
import { agrupar, lerEstado } from './logica';
import type { Fase } from './tipos';

function Grupo({ titulo, fases, forcarAberto, renderizar }: { titulo: string; fases: Fase[]; forcarAberto: boolean; renderizar: (f: Fase) => ReactNode }) {
  const [aberto, setAberto] = useState(false);
  if (fases.length === 0) return null;
  const visivel = aberto || forcarAberto;
  const Seta = visivel ? ChevronDown : ChevronRight;
  return (
    <section className="grid grid-cols-1 gap-3">
      <button type="button" aria-expanded={visivel} onClick={() => setAberto(!aberto)} className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-secondary)] text-left">
        <Seta size={16} aria-hidden="true" />
        {titulo} ({fases.length})
      </button>
      {visivel && <div className="grid grid-cols-1 gap-3">{fases.map(renderizar)}</div>}
    </section>
  );
}

export default function Fases() {
  const estado = useEstado();
  const acoes = useAcoes();
  const execucoes = useExecucoes();
  const [busca, setBusca] = useState('');
  const [dialogo, setDialogo] = useState<'planejar' | 'investigar' | null>(null);

  if (estado.isPending) return <Pagina titulo="Fases"><EsqueletoPagina cartoes={4} /></Pagina>;
  if (estado.isError) return <Pagina titulo="Fases"><Erro erro={estado.error} aoTentar={() => void estado.refetch()} /></Pagina>;
  const { estado: e, erro } = lerEstado(estado.data);
  if (!e) return <Pagina titulo="Fases"><Erro erro={new Error(erro)} aoTentar={() => void estado.refetch()} /></Pagina>;

  const lista = acoes.data ?? [];
  const acaoRodar = lista.find((a) => a.id === 'dev.rodar-parte');
  const planejar = lista.find((a) => a.id === 'dev.planejar-fase');
  const investigar = lista.find((a) => a.id === 'dev.investigar');
  const g = agrupar(e.fases, busca);
  const buscando = busca.trim() !== '';
  const nada = g.abertas.length + g.fechadas.length + g.semAcompanhamento.length === 0;
  const exec = execucoes.data ?? [];
  const cartao = (f: Fase) => <FaseCartao key={f.pasta} fase={f} acaoRodar={acaoRodar} execucoes={exec} />;

  return (
    <Pagina
      titulo="Fases"
      subtitulo={`${e.resumo.fases_abertas} abertas · ${e.resumo.partes_fechadas} de ${e.resumo.partes_total} Partes fechadas`}
      acoes={
        <div className="flex gap-2">
          <Botao variante="secundario" disabled={!planejar} onClick={() => setDialogo('planejar')}>
            Planejar fase
          </Botao>
          <Botao variante="secundario" icone={<Compass size={14} aria-hidden="true" />} disabled={!investigar} onClick={() => setDialogo('investigar')}>
            Investigar
          </Botao>
        </div>
      }
    >
      <label className="relative block mb-4">
        <span className="sr-only">Buscar fase por número ou nome</span>
        <Search size={16} aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)]" />
        <input
          type="search"
          value={busca}
          onChange={(ev) => setBusca(ev.target.value)}
          placeholder="Buscar por número ou nome"
          className="w-full h-10 pl-9 pr-3 rounded-lg border border-[var(--color-input-border)] bg-[var(--color-input-bg)] text-sm"
        />
      </label>
      <AvisosDoLeitor avisos={e.avisos} />
      {nada ? (
        <EstadoVazio titulo={buscando ? 'Nenhuma fase encontrada' : 'Ainda não há fases'} texto={buscando ? 'Tente outro número ou outra palavra.' : undefined} />
      ) : (
        <div className="grid grid-cols-1 gap-5">
          <div className="grid grid-cols-1 gap-3">{g.abertas.map(cartao)}</div>
          <Grupo titulo="Fases fechadas" fases={g.fechadas} forcarAberto={buscando} renderizar={cartao} />
          <Grupo titulo="Fases sem arquivo de progresso" fases={g.semAcompanhamento} forcarAberto={buscando} renderizar={cartao} />
        </div>
      )}
      {planejar && (
        <DialogoTexto
          acao={planejar}
          aberto={dialogo === 'planejar'}
          aoFechar={() => setDialogo(null)}
          explicacao="Conte a ideia. Uma sessão do Claude vai montar o plano da fase, em segundo plano, sem mexer no código."
        />
      )}
      {investigar && (
        <DialogoTexto
          acao={investigar}
          aberto={dialogo === 'investigar'}
          aoFechar={() => setDialogo(null)}
          explicacao="Conte o que aconteceu. Uma sessão do Claude vai só olhar e explicar a causa, sem mudar nada."
        />
      )}
    </Pagina>
  );
}
