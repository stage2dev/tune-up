// Bloco "envio": zona de arrastar + botao que abre o seletor de arquivo; manda a imagem crua para
// POST /api/modulos/<id>/envio?destino=<chave> (envio.py) com barra de progresso, erro em palavras e aviso de fim.
// Variante "um" (logo: previa da imagem atual) e "grade" (fotos, com remover pelo comando do modulo).
import { useEffect, useRef, useState, type DragEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiEnviarArquivo } from '../../api/cliente';
import { relerModulo } from '../../api/ganchos';
import { Botao, Cartao, Dialogo, useAvisos } from '../../componentes';
import { itens, mensagemDoErro, textoOuNada, tipoDaMidia, urlDoArquivo, type BlocoCru } from './interativos';
import { conferirArquivo, TIPOS_ACEITOS } from './marca';
import { ArquivoDeMidia } from './Midia';
import { AvisoEnvio, useEnvio } from './useEnvio';

export interface ResultadoEnvio { feitos: number; erros: string[]; ultimo: string | null }

/**
 * Manda os arquivos um de cada vez (o servidor trava por destino). Arquivo que falha na conferencia local nem sai;
 * erro de um nao para os outros. `mandar` devolve o `c` da resposta (ou null).
 */
export async function enviarArquivos(arquivos: File[], maxBytes: unknown, mandar: (a: File, i: number) => Promise<string | null>): Promise<ResultadoEnvio> {
  const r: ResultadoEnvio = { feitos: 0, erros: [], ultimo: null };
  for (let i = 0; i < arquivos.length; i++) {
    const a = arquivos[i];
    const problema = conferirArquivo(a, maxBytes);
    if (problema) { r.erros.push(problema); continue; }
    try {
      r.ultimo = (await mandar(a, i)) ?? r.ultimo;
      r.feitos += 1;
    } catch (e) {
      r.erros.push(`“${a.name}”: ${mensagemDoErro(e)}`);
    }
  }
  return r;
}

/** Frase do fim: quantas foram e o que deu errado. */
export function fraseDoFim(r: ResultadoEnvio, grade: boolean): string {
  const feito = r.feitos === 0 ? '' : r.feitos === 1 ? (grade ? '1 foto enviada.' : 'Imagem enviada.') : `${r.feitos} fotos enviadas.`;
  return [feito, ...r.erros].filter(Boolean).join(' ');
}

type Fase = { fase: 'parado' } | { fase: 'enviando'; i: number; n: number; progresso: number } | { fase: 'fim'; ok: boolean; texto: string };

export function Envio({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const destino = textoOuNada(b.destino);
  const grade = b.variante === 'grade';
  const atual = typeof b.atual === 'string' && tipoDaMidia(b.atual) === 'imagem' ? b.atual : null;
  const fotos = itens(b.itens).filter((i) => tipoDaMidia(i.arquivo) === 'imagem');
  const remover = b.remover && typeof b.remover === 'object' ? (b.remover as Record<string, unknown>) : null;
  const acaoRemover = remover ? textoOuNada(remover.acao) : undefined;
  const qc = useQueryClient();
  const { avisar } = useAvisos();
  const [fase, setFase] = useState<Fase>({ fase: 'parado' });
  const [recente, setRecente] = useState<string | null>(null); // a imagem que acabou de subir, ate o modulo devolver a nova
  const [arrastando, setArrastando] = useState(false);
  const [apagar, setApagar] = useState<string | null>(null);
  const emVoo = useRef(false);
  const entrada = useRef<HTMLInputElement>(null);
  const rem = useEnvio(moduloId);
  useEffect(() => setRecente(null), [atual]);
  const enviando = fase.fase === 'enviando';

  async function mandarTodos(lista: File[]) {
    if (emVoo.current || !destino || !moduloId || lista.length === 0) return;
    emVoo.current = true;
    const arquivos = grade ? lista : lista.slice(0, 1);
    const caminho = `/api/modulos/${encodeURIComponent(moduloId)}/envio?destino=${encodeURIComponent(destino)}`;
    setFase({ fase: 'enviando', i: 0, n: arquivos.length, progresso: 0 });
    try {
      const r = await enviarArquivos(arquivos, b.max_bytes, async (a, i) => {
        setFase({ fase: 'enviando', i, n: arquivos.length, progresso: 0 });
        const resp = await apiEnviarArquivo<{ c?: unknown }>(caminho, a, (p) => setFase({ fase: 'enviando', i, n: arquivos.length, progresso: p }));
        return typeof resp?.c === 'string' ? resp.c : null;
      });
      if (r.feitos > 0) relerModulo(qc, moduloId);
      if (!grade && r.ultimo) setRecente(r.ultimo);
      const texto = fraseDoFim(r, grade);
      const ok = r.erros.length === 0;
      setFase({ fase: 'fim', ok, texto });
      avisar(ok ? { tipo: 'sucesso', titulo: 'Envio terminado', texto } : { tipo: 'erro', titulo: r.feitos ? 'Parte não foi enviada' : 'Não deu para enviar', texto });
    } finally {
      emVoo.current = false;
      if (entrada.current) entrada.current.value = ''; // o mesmo arquivo pode ser escolhido de novo
    }
  }

  function soltar(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setArrastando(false);
    if (!enviando) void mandarTodos(Array.from(e.dataTransfer.files));
  }

  const mostrada = recente ?? atual;
  const pronto = !!destino && !!moduloId;
  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <div className="grid gap-3">
        {textoOuNada(b.descricao) && <p className="text-sm text-[var(--color-text-secondary)] break-words">{textoOuNada(b.descricao)}</p>}
        {!grade && moduloId && (mostrada ? (
          <div className="grid place-items-center h-32 w-32 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] overflow-hidden">
            <ArquivoDeMidia key={mostrada} tipo="imagem" url={urlDoArquivo(moduloId, mostrada)} rotulo={textoOuNada(b.alt) ?? 'Imagem atual'} classe="max-h-full max-w-full object-contain" />
          </div>
        ) : <p className="text-sm text-[var(--color-text-secondary)]">{textoOuNada(b.vazio) ?? 'Ainda não há imagem.'}</p>)}
        {grade && moduloId && (fotos.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary)]">{textoOuNada(b.vazio) ?? 'Ainda não há fotos.'}</p>
        ) : (
          <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {fotos.map((f, k) => {
              const arq = String(f.arquivo);
              const rotulo = textoOuNada(f.rotulo) ?? `Foto ${k + 1}`;
              return (
                <li key={arq} className="grid gap-1 min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] overflow-hidden">
                  <ArquivoDeMidia key={arq} tipo="imagem" url={urlDoArquivo(moduloId, arq)} rotulo={rotulo} miniatura classe="w-full aspect-square object-cover" />
                  <div className="grid gap-1 p-2 min-w-0">
                    <span className="text-xs break-words">{rotulo}</span>
                    {acaoRemover && <Botao variante="secundario" className="min-h-11" disabled={rem.enviando || enviando} aria-label={`Remover ${rotulo}`} onClick={() => setApagar(arq)}>Remover</Botao>}
                  </div>
                </li>
              );
            })}
          </ul>
        ))}
        <div onDragOver={(e) => { e.preventDefault(); if (!enviando) setArrastando(true); }} onDragLeave={() => setArrastando(false)} onDrop={soltar}
          className={`grid gap-2 justify-items-center rounded-xl border-2 border-dashed p-4 text-center ${arrastando ? 'border-[var(--color-accent)] bg-[var(--color-bg-tertiary)]' : 'border-[var(--color-border)]'}`}>
          <p className="m-0 text-sm text-[var(--color-text-secondary)]">{grade ? 'Arraste as fotos para cá ou' : 'Arraste a imagem para cá ou'}</p>
          <input ref={entrada} type="file" accept={TIPOS_ACEITOS.join(',')} multiple={grade} className="sr-only" tabIndex={-1} aria-hidden="true"
            onChange={(e) => void mandarTodos(Array.from(e.target.files ?? []))} />
          <Botao className="min-h-11" enviando={enviando} disabled={!pronto} textoEnviando={enviando && fase.n > 1 ? `Enviando ${fase.i + 1} de ${fase.n}…` : 'Enviando…'}
            onClick={() => entrada.current?.click()}>
            {textoOuNada(b.botao) ?? (grade ? 'Escolher fotos' : mostrada ? 'Trocar a imagem' : 'Escolher imagem')}
          </Botao>
          <p className="m-0 text-xs text-[var(--color-text-tertiary)]">PNG, JPG ou WebP.</p>
        </div>
        {enviando && (
          <div role="progressbar" aria-label="Enviando" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(fase.progresso * 100)}
            className="h-2 w-full rounded-full bg-[var(--color-bg-tertiary)] overflow-hidden">
            <div className="h-full bg-[var(--color-accent)] transition-[width]" style={{ width: `${Math.round(fase.progresso * 100)}%` }} />
          </div>
        )}
        {!pronto && <p role="note" className="text-xs text-[var(--color-text-tertiary)]">Este bloco não diz para onde mandar o arquivo.</p>}
        {fase.fase === 'fim' && <AvisoEnvio ok={fase.ok ? fase.texto : false} erro={fase.ok ? null : fase.texto} />}
        <AvisoEnvio ok={rem.ok} erro={rem.erro} />
      </div>
      <Dialogo aberto={apagar !== null} titulo="Remover esta foto?" textoConfirmar="Remover" perigo enviando={rem.enviando}
        aoConfirmar={() => { const arq = apagar; if (arq && acaoRemover) void rem.enviar(acaoRemover, { destino, arquivo: arq }).then(() => setApagar(null)); }}
        aoFechar={() => setApagar(null)}>
        <p className="break-words">{textoOuNada(remover?.confirmar) ?? 'A foto sai desta lista.'}</p>
      </Dialogo>
    </Cartao>
  );
}
