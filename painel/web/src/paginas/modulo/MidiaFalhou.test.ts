import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { MidiaDaMensagem } from './MidiaMensagem';

// "Tentar de novo" ja respondeu: a tela mostra a mensagem de sucesso do modulo (antes ok ia fixo em false).
vi.mock('./useEnvio', async (original) => ({
  ...(await original<typeof import('./useEnvio')>()),
  useEnvio: () => ({ enviar: async () => true, enviando: false, ok: 'Pedi o arquivo de novo.', erro: null }),
}));

describe('midia que falhou', () => {
  it('Tentar de novo mostra a mensagem de sucesso do modulo', () => {
    const m = { ref: 'p1', tipo: 'audio', estado: 'falhou', acao: { acao: 'baixar', dados: {} } } as const;
    const h = renderToStaticMarkup(createElement(MidiaDaMensagem, { m, moduloId: 'vendas' }));
    expect(h).toContain('Tentar de novo');
    expect(h).toContain('Pedi o arquivo de novo.');
  });
});
