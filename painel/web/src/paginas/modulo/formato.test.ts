import { describe, expect, it } from 'vitest';
import { atualizadoHa, caminhoCurto, cortar, dataCurta, diasDesde, ha, linkSeguro, numero, porcento, reais, SEM_DADO } from './formato';

const agora = new Date(2026, 10, 10, 15, 0, 0); // 10/11/2026 15:00 local

describe('datas', () => {
  it('conta dias de calendario', () => {
    expect(diasDesde('2026-11-10', agora)).toBe(0);
    expect(diasDesde('2026-11-09', agora)).toBe(1);
    expect(diasDesde('2026-11-03T23:59:00', agora)).toBe(7);
    expect(diasDesde('2026-12-01', agora)).toBe(0); // futuro nao fica negativo
  });
  it('data ruim ou ausente vira sem dado, nunca zero', () => {
    expect(diasDesde(null, agora)).toBeNull();
    expect(diasDesde('lixo', agora)).toBeNull();
    expect(ha(null, agora)).toBe(SEM_DADO);
  });
  it('textos em portugues', () => {
    expect(ha('2026-11-10', agora)).toBe('hoje');
    expect(ha('2026-11-09', agora)).toBe('ontem');
    expect(ha('2026-11-05', agora)).toBe('há 5 dias');
    expect(atualizadoHa('2026-11-05', agora)).toBe('atualizado há 5 dias');
    expect(atualizadoHa('', agora)).toBe('atualização sem data');
  });
  it('data curta', () => {
    expect(dataCurta('2026-11-09')).toBe('09/11');
    expect(dataCurta('2026-11-09', true)).toBe('09/11/2026');
    expect(dataCurta(null)).toBe(SEM_DADO);
  });
});

describe('numeros', () => {
  it('nulo e sem dado, zero e zero', () => {
    expect(numero(null)).toBe(SEM_DADO);
    expect(numero(undefined)).toBe(SEM_DADO);
    expect(numero(0)).toBe('0');
    expect(porcento(null)).toBe(SEM_DADO);
    expect(porcento(12.5, 1)).toBe('12,5%');
    expect(reais(null)).toBe(SEM_DADO);
  });
  it('reais em pt-BR', () => {
    expect(reais(34).replace(/\s/g, ' ')).toBe('R$ 34,00');
    expect(reais(0).replace(/\s/g, ' ')).toBe('R$ 0,00');
  });
});

describe('texto', () => {
  it('so link http e https vira link', () => {
    expect(linkSeguro('https://github.com/x/pull/1')).toBe('https://github.com/x/pull/1');
    expect(linkSeguro('javascript:alert(1)')).toBeNull();
    expect(linkSeguro('/home/pessoa/arquivo.md')).toBeNull();
    expect(linkSeguro('')).toBeNull();
  });
  it('caminho curto e cortar', () => {
    expect(caminhoCurto('/a/b/c/d.md')).toBe('c/d.md');
    expect(cortar('abcdef', 4)).toBe('abc…');
    expect(cortar('abc', 4)).toBe('abc');
  });
});
