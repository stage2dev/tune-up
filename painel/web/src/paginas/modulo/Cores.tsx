// Bloco "cores": um seletor de cor grande por campo. Mexer muda a previa da aba na hora (rascunho);
// soltar (evento change) manda { campo, valor } ao comando do modulo. Avisa contraste abaixo de 4,5:1.
import { useEffect, useId, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { Botao, Cartao } from '../../componentes';
import { dadosFixos, itens, textoOuNada, type BlocoCru } from './interativos';
import { contraste, CONTRASTE_MINIMO, corHex } from './marca';
import { useRascunho } from './Rascunho';
import { AvisoEnvio, useEnvio } from './useEnvio';

export interface CorLida { chave: string; rotulo: string; uso?: string; valor: string }

export function lerCores(v: unknown): CorLida[] {
  return itens(v)
    .filter((i) => typeof i.chave === 'string' && i.chave)
    .map((i) => ({ chave: String(i.chave), rotulo: textoOuNada(i.rotulo) ?? String(i.chave), uso: textoOuNada(i.uso), valor: corHex(i.valor) ?? '#000000' }));
}

/** Pares com contraste baixo, com a frase do aviso. Par com campo que nao existe no bloco e ignorado. */
export function avisosDeContraste(pares: unknown, valores: Record<string, string>, rotulos: Record<string, string>): string[] {
  const out: string[] = [];
  for (const p of itens(pares)) {
    const a = String(p.a ?? '');
    const b = String(p.b ?? '');
    if (!(a in valores) || !(b in valores)) continue;
    const r = contraste(valores[a], valores[b]);
    if (r === null || r >= CONTRASTE_MINIMO) continue;
    out.push(textoOuNada(p.aviso) ??
      `“${rotulos[a]}” e “${rotulos[b]}” ficam difíceis de ler juntas (contraste ${r.toFixed(1).replace('.', ',')}:1; o mínimo é 4,5:1).`);
  }
  return out;
}

/** Input de cor que avisa o "soltar" (evento change nativo; o onChange do React dispara a cada movimento). */
function EntradaCor({ id, valor, desligado, aoMexer, aoSoltar }: { id: string; valor: string; desligado: boolean; aoMexer: (v: string) => void; aoSoltar: (v: string) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const soltar = useRef(aoSoltar);
  soltar.current = aoSoltar;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const f = () => soltar.current(el.value);
    el.addEventListener('change', f);
    return () => el.removeEventListener('change', f);
  }, []);
  return (
    <input ref={ref} id={id} type="color" value={valor} disabled={desligado} onChange={(e) => aoMexer(e.target.value)}
      className="block w-full h-16 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-1 cursor-pointer disabled:cursor-wait" />
  );
}

export function Cores({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const cores = lerCores(b.itens);
  const acao = textoOuNada(b.acao);
  const { rascunho, por, tirar } = useRascunho();
  const { enviar, enviando, ok, erro } = useEnvio(moduloId);
  const idBase = `cor-${useId()}`;
  const atual = (c: CorLida) => corHex(rascunho[c.chave]?.valor) ?? c.valor;

  // O servidor devolveu outro valor para um campo: o rascunho dele ja cumpriu o papel.
  const vistos = useRef<Record<string, string>>({});
  const assinatura = cores.map((c) => `${c.chave}=${c.valor}`).join('|');
  useEffect(() => {
    for (const c of cores) {
      if (vistos.current[c.chave] !== undefined && vistos.current[c.chave] !== c.valor) tirar(c.chave);
      vistos.current[c.chave] = c.valor;
    }
  }, [assinatura]); // eslint-disable-line react-hooks/exhaustive-deps

  async function salvar(c: CorLida, valor: string) {
    const hex = corHex(valor);
    if (!acao || !hex) return;
    if (hex === c.valor) { tirar(c.chave); return; } // voltou ao que ja estava salvo
    por(c.chave, { valor: hex });
    if (!(await enviar(acao, { campo: c.chave, valor: hex }))) tirar(c.chave); // falhou: volta ao valor do servidor
  }

  const valores = Object.fromEntries(cores.map((c) => [c.chave, atual(c)]));
  const avisos = avisosDeContraste(b.contraste, valores, Object.fromEntries(cores.map((c) => [c.chave, c.rotulo])));
  const botao = b.botao && typeof b.botao === 'object' ? (b.botao as Record<string, unknown>) : null;
  const acaoBotao = botao ? textoOuNada(botao.acao) : undefined;

  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <div className="grid gap-3">
        {textoOuNada(b.descricao) && <p className="text-sm text-[var(--color-text-secondary)] break-words">{textoOuNada(b.descricao)}</p>}
        {acaoBotao && (
          <div><Botao variante="secundario" className="min-h-11" enviando={enviando} textoEnviando="Buscando…"
            onClick={() => void enviar(acaoBotao, dadosFixos(botao?.dados))}>{textoOuNada(botao?.rotulo) ?? 'Sugerir cores'}</Botao></div>
        )}
        {cores.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary)]">{textoOuNada(b.vazio) ?? 'Ainda não há cores para escolher.'}</p>
        ) : (
          <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {cores.map((c) => (
              <li key={c.chave} className="grid gap-1 min-w-0 content-start">
                <EntradaCor id={`${idBase}-${c.chave}`} valor={atual(c)} desligado={enviando || !acao}
                  aoMexer={(v) => { const h = corHex(v); if (h) por(c.chave, { valor: h }); }} aoSoltar={(v) => void salvar(c, v)} />
                <label htmlFor={`${idBase}-${c.chave}`} className="text-sm font-semibold break-words">{c.rotulo}</label>
                {c.uso && <span className="text-xs text-[var(--color-text-secondary)] break-words">{c.uso}</span>}
                <span className="text-xs tabular-nums text-[var(--color-text-secondary)]">{atual(c)}</span>
              </li>
            ))}
          </ul>
        )}
        {avisos.map((t) => (
          <p key={t} role="status" className="rounded-lg border border-[var(--color-attention)] p-3 text-sm text-[var(--color-attention)] break-words">{t}</p>
        ))}
        {!acao && cores.length > 0 && <p role="note" className="text-xs text-[var(--color-text-tertiary)]">Este bloco não diz qual comando salva as cores.</p>}
        {enviando ? (
          <p role="status" className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]"><Loader2 size={14} className="anim-girar" aria-hidden="true" />Salvando…</p>
        ) : <AvisoEnvio ok={ok} erro={erro} />}
      </div>
    </Cartao>
  );
}
