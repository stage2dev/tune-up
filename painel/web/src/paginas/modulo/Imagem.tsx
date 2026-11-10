// Bloco "imagem": mostra uma imagem embutida (ex.: QR code). So png e jpeg; o resto vira o aviso de bloco desconhecido.
import type { Bloco } from '../../api/tipos';
import { Cartao } from '../../componentes';
import { imagemSegura, textoOuNada } from './interativos';

export function Imagem({ b, desconhecido }: { b: Bloco; desconhecido: () => React.ReactNode }) {
  if (!imagemSegura(b.data_uri)) return <>{desconhecido()}</>;
  const legenda = textoOuNada(b.legenda);
  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <figure className="grid justify-items-center gap-2 m-0">
        <img src={b.data_uri} alt={typeof b.alt === 'string' ? b.alt : ''} className="max-w-full h-auto bg-white rounded-lg p-2" style={{ imageRendering: 'pixelated' }} />
        {legenda && <figcaption className="text-xs text-[var(--color-text-secondary)] break-words text-center">{legenda}</figcaption>}
      </figure>
    </Cartao>
  );
}
