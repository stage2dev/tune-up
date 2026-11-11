// Renderizador dos blocos do contrato de modulo (kpis, tabela, lista, serie, texto, acoes, formulario, conversa, imagem, galeria, midia,
// cores, envio, previa, opcoes).
// Cada bloco chega de um pacote de projeto e pode vir incompleto: tudo aqui e lido com cuidado.
import type { ReactNode } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Bloco } from '../../api/tipos';
import { Botao, Cartao, EstadoVazio, Selo } from '../../componentes';
import type { Tom } from '../../componentes/Selo';
import { BotoesDoGrupo } from './BotaoAcao';
import { Conversa } from './Conversa';
import { Cores } from './Cores';
import { Envio } from './Envio';
import { Formulario } from './Formulario';
import { Imagem } from './Imagem';
import { Galeria, Midia } from './Midia';
import { numero, SEM_DADO } from './formato';
import { Opcoes } from './Opcoes';
import { Previa } from './Previa';
import { ProvedorRascunho } from './Rascunho';
import { chavesDosBlocos, type BlocoCru } from './interativos';
import { montarSeries, type SerieEntrada } from './series';

const COR_TOM: Record<string, string> = {
  bom: 'var(--color-success)',
  atencao: 'var(--color-attention)',
  ruim: 'var(--color-error)',
};
const TOM_SELO: Record<string, Tom> = { neutro: 'neutro', bom: 'ok', atencao: 'atencao', ruim: 'erro' };
const CORES_LINHA = ['var(--color-accent)', 'var(--color-purple)', 'var(--color-success)', 'var(--color-attention)', 'var(--color-error)'];

const lista = (v: unknown): Record<string, unknown>[] =>
  Array.isArray(v) ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object') : [];
const texto = (v: unknown): string | undefined => (typeof v === 'string' && v.trim() ? v : undefined);

/** Valor de celula/numero: nulo ou ausente vira "sem dado", nunca zero. */
export function mostrarValor(v: unknown): string {
  if (v === null || v === undefined || v === '') return SEM_DADO;
  if (typeof v === 'number') return Number.isFinite(v) ? numero(v, Number.isInteger(v) ? 0 : 2) : SEM_DADO;
  if (typeof v === 'string') return v;
  return SEM_DADO;
}

function Moldura({ b, children }: { b: BlocoCru; children: ReactNode }) {
  return <Cartao titulo={texto(b.titulo)}>{children}</Cartao>;
}

function Vazio({ texto: t }: { texto?: string }) {
  return <EstadoVazio titulo="Nada para mostrar" texto={t ?? 'Este bloco ainda não tem dados.'} />;
}

function Kpis({ b }: { b: BlocoCru }) {
  const itens = lista(b.itens);
  return (
    <Moldura b={b}>
      {itens.length === 0 ? (
        <Vazio />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {itens.map((i, k) => {
            const cor = COR_TOM[String(i.tom)];
            return (
              <div key={k} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-3 min-w-0">
                <div className="text-xs text-[var(--color-text-secondary)] break-words">{mostrarValor(i.rotulo)}</div>
                <div className="mt-1 text-lg font-semibold break-words" style={cor ? { color: cor } : undefined}>
                  {mostrarValor(i.valor)}
                </div>
                {texto(i.detalhe) && <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5 break-words">{texto(i.detalhe)}</div>}
              </div>
            );
          })}
        </div>
      )}
    </Moldura>
  );
}

// Coluna 'secundaria' some no celular (menos de 640 px): a tabela cabe sem rolagem lateral.
const SO_TELA_LARGA = 'hidden sm:table-cell';

function Tabela({ b }: { b: BlocoCru }) {
  const colunas = lista(b.colunas).filter((c) => typeof c.id === 'string');
  const linhas = lista(b.linhas);
  return (
    <Moldura b={b}>
      {colunas.length === 0 || linhas.length === 0 ? (
        <Vazio texto={texto(b.vazio)} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-[var(--color-text-secondary)]">
                {colunas.map((c) => (
                  <th key={String(c.id)} scope="col" className={`py-1.5 px-2 font-medium ${c.alinhar === 'dir' ? 'text-right' : ''} ${c.secundaria === true ? SO_TELA_LARGA : ''}`}>
                    {mostrarValor(c.rotulo ?? c.id)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {linhas.map((l, k) => (
                <tr key={k} className="border-t border-[var(--color-border-subtle)]">
                  {colunas.map((c) => (
                    <td key={String(c.id)} className={`py-1.5 px-2 break-words ${c.alinhar === 'dir' ? 'text-right tabular-nums' : ''} ${c.secundaria === true ? SO_TELA_LARGA : ''}`}>
                      {mostrarValor(l[String(c.id)])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Moldura>
  );
}

function Itens({ b }: { b: BlocoCru }) {
  const itens = lista(b.itens);
  return (
    <Moldura b={b}>
      {itens.length === 0 ? (
        <Vazio texto={texto(b.vazio)} />
      ) : (
        <ul>
          {itens.map((i, k) => {
            const selo = i.selo && typeof i.selo === 'object' ? (i.selo as Record<string, unknown>) : null;
            const seloTexto = selo ? texto(selo.texto) : undefined;
            return (
              <li key={k} className="py-2 border-b border-[var(--color-border-subtle)] last:border-0 min-w-0">
                <div className="flex flex-wrap items-start gap-x-2 gap-y-1">
                  <span className="text-sm min-w-0 flex-1 basis-56 break-words">{mostrarValor(i.titulo)}</span>
                  {seloTexto && <Selo estado={seloTexto} rotulo={seloTexto} tom={TOM_SELO[String(selo?.tom)] ?? 'neutro'} />}
                </div>
                {texto(i.detalhe) && <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 break-words">{texto(i.detalhe)}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </Moldura>
  );
}

function Serie({ b }: { b: BlocoCru }) {
  const m = montarSeries(lista(b.series) as unknown as SerieEntrada[]);
  const unidade = texto(b.unidade);
  const formatar = (v: number) => (unidade ? `${numero(v, Number.isInteger(v) ? 0 : 2)} ${unidade}` : numero(v, Number.isInteger(v) ? 0 : 2));
  return (
    <Moldura b={b}>
      {m.comDado < 2 ? (
        <EstadoVazio titulo="Ainda poucos dias" texto={texto(b.vazio) ?? 'O gráfico aparece quando houver pelo menos 2 dias com número.'} />
      ) : (
        <div role="img" aria-label={`Gráfico de linha: ${texto(b.titulo) ?? 'série'}`} className="h-56 w-full min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={m.linhas} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
              <XAxis dataKey="rotulo" tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} stroke="var(--color-border)" minTickGap={24} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} stroke="var(--color-border)" width={52} tickFormatter={(v: number) => formatar(v)} />
              <Tooltip
                formatter={(v) => (typeof v === 'number' ? formatar(v) : SEM_DADO)}
                contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: 12, color: 'var(--color-text)' }}
              />
              {m.campos.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
              {m.campos.map((c, i) => (
                <Line key={c.campo} type="monotone" dataKey={c.campo} name={c.nome} stroke={CORES_LINHA[i % CORES_LINHA.length]} strokeWidth={2} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Moldura>
  );
}

function Texto({ b, aoIrAba }: { b: BlocoCru; aoIrAba?: (aba: string) => void }) {
  const t = texto(b.texto);
  const ir = b.ir_para && typeof b.ir_para === 'object' ? (b.ir_para as Record<string, unknown>) : null;
  const aba = ir ? texto(ir.aba) : undefined;
  return (
    <Moldura b={b}>
      {t ? <p className="text-sm whitespace-pre-line break-words">{t}</p> : <Vazio />}
      {aba && aoIrAba && <Botao className="mt-3" onClick={() => aoIrAba(aba)}>{texto(ir?.rotulo) ?? 'Abrir'}</Botao>}
    </Moldura>
  );
}

function Acoes({ b }: { b: BlocoCru }) {
  const grupo = texto(b.grupo);
  return (
    <Moldura b={b}>
      {grupo ? (
        <BotoesDoGrupo grupo={grupo} vazio={<Vazio texto="Este grupo não tem ações cadastradas." />} />
      ) : (
        <Vazio texto="Este bloco não diz de qual grupo são as ações." />
      )}
    </Moldura>
  );
}

function Desconhecido({ tipo }: { tipo: string }) {
  return (
    <p role="note" className="text-xs text-[var(--color-text-tertiary)] px-1">
      Um bloco do tipo “{tipo || 'sem tipo'}” não é reconhecido por esta versão do painel e foi ignorado.
    </p>
  );
}

export function RenderBloco({ bloco, moduloId, aoIrAba }: { bloco: Bloco; moduloId?: string; aoIrAba?: (aba: string) => void }) {
  const b = bloco as BlocoCru; // vem de um pacote de projeto: cada bloco le os campos com cuidado
  switch (b?.tipo) {
    case 'kpis':
      return <Kpis b={b} />;
    case 'tabela':
      return <Tabela b={b} />;
    case 'lista':
      return <Itens b={b} />;
    case 'serie':
      return <Serie b={b} />;
    case 'texto':
      return <Texto b={b} aoIrAba={aoIrAba} />;
    case 'acoes':
      return <Acoes b={b} />;
    case 'formulario':
      return <Formulario b={b} moduloId={moduloId} />;
    case 'conversa':
      return <Conversa b={b} moduloId={moduloId} />;
    case 'imagem':
      return <Imagem b={b} desconhecido={() => <Desconhecido tipo="imagem" />} />;
    case 'galeria':
      return <Galeria b={b} moduloId={moduloId} />;
    case 'midia':
      return <Midia b={b} moduloId={moduloId} />;
    case 'cores':
      return <Cores b={b} moduloId={moduloId} />;
    case 'envio':
      return <Envio b={b} moduloId={moduloId} />;
    case 'previa':
      return <Previa b={b} moduloId={moduloId} />;
    case 'opcoes':
      return <Opcoes b={b} moduloId={moduloId} />;
    default:
      return <Desconhecido tipo={String(b?.tipo ?? '')} />;
  }
}

export function Blocos({ blocos, moduloId, aoIrAba }: { blocos: Bloco[]; moduloId?: string; aoIrAba?: (aba: string) => void }) {
  if (!Array.isArray(blocos) || blocos.length === 0) {
    return <Cartao><EstadoVazio titulo="Esta aba está vazia" texto="O módulo ainda não trouxe nada para mostrar aqui." /></Cartao>;
  }
  const chaves = chavesDosBlocos(blocos as BlocoCru[]);
  return (
    <ProvedorRascunho>
      <div className="grid gap-3 grid-cols-[minmax(0,1fr)]">
        {blocos.map((b, i) => <RenderBloco key={chaves[i]} bloco={b} moduloId={moduloId} aoIrAba={aoIrAba} />)}
      </div>
    </ProvedorRascunho>
  );
}
