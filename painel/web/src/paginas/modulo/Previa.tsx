// Bloco "previa": um post de exemplo desenhado aqui mesmo (HTML e CSS) com as cores, letras, nome e logo que o modulo manda.
// Acompanha na hora o rascunho dos blocos "cores" e "opcoes" da mesma aba (campos ligados em `campos`).
import { useState } from 'react';
import { Cartao } from '../../componentes';
import { dadosFixos, textoOuNada, tipoDaMidia, urlDoArquivo, type BlocoCru } from './interativos';
import { vistaDaPrevia } from './marca';
import { useRascunho } from './Rascunho';

function Logo({ url, nome }: { url: string; nome: string }) {
  const [falhou, setFalhou] = useState(false);
  if (falhou) return null; // sem logo, o nome segura o topo
  return <img src={url} alt={`Logo de ${nome}`} className="h-10 w-10 shrink-0 object-contain" onError={() => setFalhou(true)} />;
}

export function Previa({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const { rascunho } = useRascunho();
  const { cores, fontes } = vistaDaPrevia(b, rascunho);
  const t = dadosFixos(b.textos);
  const nome = textoOuNada(b.nome) ?? 'O seu negócio';
  const logo = moduloId && tipoDaMidia(b.logo) === 'imagem' ? urlDoArquivo(moduloId, String(b.logo)) : null;
  const numero = textoOuNada(t.numero);
  return (
    <Cartao titulo={textoOuNada(b.titulo) ?? 'Como vai ficar'}>
      <figure className="m-0 grid gap-3">
        <div data-previa className="mx-auto w-full max-w-[360px] aspect-[4/5] rounded-xl border border-[var(--color-border)] p-5 flex flex-col justify-between gap-3 overflow-hidden"
          style={{ background: cores.fundo, color: cores.texto }}>
          <div className="flex items-center gap-2 min-w-0">
            {logo && <Logo key={logo} url={logo} nome={nome} />}
            <span className="text-base font-semibold break-words min-w-0" style={{ fontFamily: fontes.titulo }}>{nome}</span>
          </div>
          <div className="rounded-xl p-4" style={{ background: cores.principal, color: cores.fundo }}>
            {numero && <p className="m-0 text-4xl leading-none font-bold" style={{ fontFamily: fontes.titulo, color: cores.superficie }}>{numero}</p>}
            <p className="m-0 mt-2 text-xl leading-tight font-bold break-words" style={{ fontFamily: fontes.titulo }}>{textoOuNada(t.chamada) ?? 'Uma frase forte sobre o que vocês fazem'}</p>
          </div>
          <div className="grid gap-2 justify-items-start">
            <p className="m-0 text-sm leading-snug break-words" style={{ fontFamily: fontes.texto }}>{textoOuNada(t.frase) ?? 'Um detalhe que faz a pessoa querer saber mais.'}</p>
            <span className="rounded-full px-4 py-2 text-sm font-semibold break-words" style={{ fontFamily: fontes.texto, background: cores.destaque, color: cores.fundo }}>
              {textoOuNada(t.botao) ?? 'Fale com a gente'}
            </span>
          </div>
        </div>
        <figcaption className="text-xs text-[var(--color-text-secondary)] break-words">
          {textoOuNada(b.legenda) ?? 'Exemplo de post com a sua marca. As peças de verdade seguem estas cores, letras e fotos.'}
        </figcaption>
      </figure>
    </Cartao>
  );
}
