// Pecas pequenas da tela Agentes: chip de modelo, medidor de esforco, ponto de estado, botao de recolher.
import { ChevronDown, ChevronRight } from 'lucide-react';
import { corModelo, degrauEsforco, familiaModelo, rotuloEsforco, rotuloModelo } from './logica';

export function ChipModelo({ modelo, modeloId }: { modelo: string | null; modeloId?: string | null }) {
  const cor = corModelo(modelo ?? modeloId);
  const texto = rotuloModelo(modelo ?? modeloId);
  return (
    <span
      title={modeloId || modelo || 'Modelo não informado'}
      data-familia={familiaModelo(modelo ?? modeloId)}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold whitespace-nowrap border"
      style={{
        color: cor,
        background: `color-mix(in srgb, ${cor} 12%, transparent)`,
        borderColor: `color-mix(in srgb, ${cor} 35%, transparent)`,
      }}
    >
      <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full" style={{ background: cor }} />
      <span className="sr-only">Modelo: </span>
      {texto}
    </span>
  );
}

/** 5 barrinhas crescentes (low..max) + rotulo. */
export function MedidorEsforco({ esforco, compacto = false }: { esforco: string | null; compacto?: boolean }) {
  const d = degrauEsforco(esforco);
  const rotulo = rotuloEsforco(esforco);
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap" role="img" aria-label={`Esforço: ${rotulo}`} title={esforco ? `Esforço ${esforco}` : 'Esforço não informado'}>
      <span className="inline-flex items-end gap-[2px] h-3.5" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className="w-[4px] rounded-sm"
            style={{
              height: `${30 + i * 14}%`,
              background: i <= d ? 'var(--color-text)' : 'var(--color-bg-tertiary)',
              opacity: i <= d ? 0.45 + i * 0.11 : 1,
            }}
          />
        ))}
      </span>
      {!compacto && <span className={`text-xs ${d ? 'text-[var(--color-text-secondary)]' : 'text-[var(--color-text-tertiary)]'}`}>{rotulo}</span>}
    </span>
  );
}

export function PontoAgente({ rodando }: { rodando: boolean }) {
  const cor = rodando ? 'var(--color-accent)' : 'var(--color-success)';
  return (
    <span
      aria-hidden="true"
      className={`ag-ponto ${rodando ? 'ag-vivo' : ''}`}
      style={{ background: rodando ? cor : `color-mix(in srgb, ${cor} 55%, transparent)`, color: cor }}
    />
  );
}

export function BotaoRecolher({ aberto, aoAlternar, rotulo, controla }: { aberto: boolean; aoAlternar: () => void; rotulo: string; controla: string }) {
  const Icone = aberto ? ChevronDown : ChevronRight;
  return (
    <button
      type="button"
      onClick={aoAlternar}
      aria-expanded={aberto}
      aria-controls={controla}
      aria-label={`${aberto ? 'Recolher' : 'Expandir'} ${rotulo}`}
      className="inline-flex items-center justify-center w-7 h-7 rounded-md shrink-0 text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text)]"
    >
      <Icone size={16} aria-hidden="true" />
    </button>
  );
}
