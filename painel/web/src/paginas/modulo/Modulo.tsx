// Tela generica de um modulo (/m/:id): alertas, abas e blocos vindos do servidor.
import { useState } from 'react';
import { useParams } from 'react-router';
import { AlertTriangle, Info, OctagonAlert } from 'lucide-react';
import { useModulo } from '../../api/ganchos';
import { Abas, Erro, EsqueletoPagina, EstadoVazio, Pagina, Cartao } from '../../componentes';
import type { AlertaModulo, NivelAlerta } from '../../api/tipos';
import { dataHora } from './formato';
import { Blocos } from './Blocos';
import { alertaDaAba } from './entrada';

const ESTILO: Record<NivelAlerta, { cor: string; Icone: typeof Info }> = {
  info: { cor: 'var(--color-accent)', Icone: Info },
  atencao: { cor: 'var(--color-attention)', Icone: AlertTriangle },
  critico: { cor: 'var(--color-error)', Icone: OctagonAlert },
};

function Alertas({ alertas }: { alertas: AlertaModulo[] }) {
  if (!Array.isArray(alertas) || alertas.length === 0) return null;
  return (
    <ul className="grid gap-2 mb-4" aria-label="Alertas">
      {alertas.map((a, i) => {
        const { cor, Icone } = ESTILO[a.nivel] ?? ESTILO.info;
        return (
          <li
            key={i}
            className="flex items-start gap-2 rounded-lg border p-3 text-sm"
            style={{ borderColor: `color-mix(in srgb, ${cor} 40%, transparent)`, background: `color-mix(in srgb, ${cor} 8%, transparent)` }}
          >
            <Icone size={16} aria-hidden="true" className="shrink-0 mt-0.5" style={{ color: cor }} />
            <span className="break-words min-w-0">{a.texto}</span>
          </li>
        );
      })}
    </ul>
  );
}

export default function Modulo() {
  const { id } = useParams();
  const q = useModulo(id);
  const [escolhida, setEscolhida] = useState<string | null>(null);

  if (q.isPending) return <Pagina titulo="Carregando…"><EsqueletoPagina cartoes={3} /></Pagina>;
  if (q.isError && !q.data) return <Pagina titulo="Módulo"><Erro erro={q.error} aoTentar={() => void q.refetch()} /></Pagina>;

  const m = q.data;
  if (!m) return null; // so alcancavel sem dados e sem erro (consulta desligada)
  const abas = Array.isArray(m.abas) ? m.abas : [];
  const ativa = abas.find((a) => a.id === escolhida) ?? abas[0];
  const avisos = Array.isArray(m.avisos) ? m.avisos : [];

  return (
    <Pagina titulo={m.titulo} subtitulo={m.gerado_em ? `Atualizado em ${dataHora(m.gerado_em)}.` : undefined}>
      {q.isError && (
        <p role="status" className="mb-3 text-xs text-[var(--color-attention)]">
          Não foi possível atualizar. Mostrando o que já estava na tela.{' '}
          <button type="button" className="underline" onClick={() => void q.refetch()}>Tentar de novo</button>
        </p>
      )}
      <Alertas alertas={m.alertas} />
      {avisos.length > 0 && (
        <Cartao titulo="Avisos" className="mb-4">
          <ul className="list-disc pl-4 text-xs text-[var(--color-text-secondary)] grid gap-0.5">
            {avisos.map((a) => <li key={a} className="break-words">{a}</li>)}
          </ul>
        </Cartao>
      )}
      {!ativa ? (
        <Cartao><EstadoVazio titulo="Este módulo não tem abas" texto="Ele está habilitado, mas ainda não trouxe nenhuma aba para mostrar." /></Cartao>
      ) : (
        <Abas abas={abas.map((a) => ({ id: a.id, rotulo: a.titulo, alerta: alertaDaAba(a.alerta) }))} ativa={ativa.id} aoTrocar={setEscolhida}>
          <Blocos key={`${id}:${ativa.id}`} blocos={ativa.blocos} moduloId={id} />
        </Abas>
      )}
    </Pagina>
  );
}
