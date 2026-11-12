import { describe, expect, it } from 'vitest';
import { intervaloDeAtualizacao } from '../../api/ganchos';
import { alertaDaAba, conversaAVista, filtrarConversas, fioComDias, horaDaMensagem, legendaDe, lerConversas, pedidoDaLinha, quandoCurto, rotuloDoTipo, voltouDepoisDeAbrir } from './entrada';

const agora = new Date(2026, 10, 11, 15, 0); // 11/11/2026 15:00 local

describe('caixa: linhas', () => {
  it('le com cuidado: sem id ou titulo some; nao_lidas vira inteiro >= 0', () => {
    const l = lerConversas([{ id: 'a', titulo: 'Ana', nao_lidas: 2.9, ativa: true, selo: { texto: 'IA', tom: 'bom' } }, { id: '', titulo: 'x' }, { titulo: 'sem id' }, null, { id: 'b', titulo: 'Bia', nao_lidas: -3 }]);
    expect(l.map((x) => x.id)).toEqual(['a', 'b']);
    expect(l[0]).toMatchObject({ naoLidas: 2, ativa: true, selo: { texto: 'IA', tom: 'bom' } });
    expect(l[1]).toMatchObject({ naoLidas: 0, ativa: false, selo: undefined });
    expect(lerConversas('x')).toEqual([]);
  });
  it('busca no titulo e na previa, sem acento nem maiuscula', () => {
    const l = lerConversas([{ id: 'a', titulo: 'João', detalhe: 'quero orçamento' }, { id: 'b', titulo: 'Bia', detalhe: 'oi' }]);
    expect(filtrarConversas(l, 'joao').map((x) => x.id)).toEqual(['a']);
    expect(filtrarConversas(l, 'ORCAMENTO').map((x) => x.id)).toEqual(['a']);
    expect(filtrarConversas(l, '  ')).toHaveLength(2);
    expect(filtrarConversas(l, 'zzz')).toEqual([]);
  });
  it('clique numa linha: { acao, dados: { ...dados_fixos, conversa_id } }; conversa_id ganha do fixo', () => {
    expect(pedidoDaLinha({ acao: 'abrir', dados_fixos: { canal: 'w', conversa_id: 'velho' } }, 'c9')).toEqual({ acao: 'abrir', dados: { canal: 'w', conversa_id: 'c9' } });
    expect(pedidoDaLinha({ acao: 'abrir' }, 'c1')).toEqual({ acao: 'abrir', dados: { conversa_id: 'c1' } });
    expect(pedidoDaLinha({ acao: '' }, 'c1')).toBeNull();
    expect(pedidoDaLinha(undefined, 'c1')).toBeNull();
  });
  it('tela estreita: abrir B com A aberta deixa a lista (e o erro) a vista ate B chegar; falha nunca volta para A', () => {
    // A aberta, a pessoa voltou para a lista e tocou em B.
    let voltou = true;
    let pendente: string | null = 'B';
    expect(conversaAVista(true, voltou, pendente)).toBe(false); // "abrindo" na lista, A nao reaparece
    // a acao falhou (ex.: 409): a lista com o aviso de erro continua na tela
    voltou = voltouDepoisDeAbrir(voltou, false);
    pendente = null;
    expect(conversaAVista(true, voltou, pendente)).toBe(false);
    // tenta de novo e da certo: so depois da releitura (pendente zera) a conversa toma a tela
    pendente = 'B';
    voltou = voltouDepoisDeAbrir(voltou, true);
    expect(conversaAVista(true, voltou, pendente)).toBe(false);
    pendente = null;
    expect(conversaAVista(true, voltou, pendente)).toBe(true);
    expect(conversaAVista(false, false, null)).toBe(false); // sem conversa aberta a lista fica
  });
  it('hora relativa da linha', () => {
    expect(quandoCurto('2026-11-11T14:59:40', agora)).toBe('agora');
    expect(quandoCurto('2026-11-11T14:55:00', agora)).toBe('5 min');
    expect(quandoCurto('2026-11-11T09:07:00', agora)).toBe('09:07');
    expect(quandoCurto('2026-11-10T22:00:00', agora)).toBe('ontem');
    expect(quandoCurto('2026-11-02T10:00:00', agora)).toBe('02/11');
    expect(quandoCurto('lixo', agora)).toBe('');
    expect(quandoCurto(undefined, agora)).toBe('');
  });
});

describe('conversa: mensagens', () => {
  it('separador antes de cada dia novo; sem data fica no dia anterior', () => {
    const fio = fioComDias([
      { id: '1', quando: '2026-11-09T10:00:00' }, { id: '2', quando: '2026-11-10T08:00:00' }, { id: '3', quando: 'sem' }, { id: '4', quando: '2026-11-11T09:00:00' }, { id: '5', quando: '2026-11-11T10:00:00' },
    ], agora);
    expect(fio.map((x) => ('dia' in x ? `[${x.dia}]` : String(x.mensagem.id)))).toEqual(['[09/11/2026]', '1', '[Ontem]', '2', '3', '[Hoje]', '4', '5']);
  });
  it('hora do balao', () => {
    expect(horaDaMensagem('2026-11-11T08:05:00')).toBe('08:05');
    expect(horaDaMensagem('x')).toBe('');
    expect(horaDaMensagem(3)).toBe('');
  });
  it('tipos nao texto viram etiqueta; texto e desconhecido nao', () => {
    expect(rotuloDoTipo('audio')).toContain('Áudio');
    expect(rotuloDoTipo('imagem')).toContain('Imagem');
    expect(rotuloDoTipo('documento')).toContain('Documento');
    expect(rotuloDoTipo('outro')).toBeTruthy();
    expect(rotuloDoTipo('texto')).toBeUndefined();
    expect(rotuloDoTipo('<b>')).toBeUndefined();
    expect(rotuloDoTipo(undefined)).toBeUndefined();
  });
  it('marcador "[audio]" some; legenda de verdade fica', () => {
    expect(legendaDe('[audio]')).toBeUndefined();
    expect(legendaDe(' [imagem] ')).toBeUndefined();
    expect(legendaDe('foto do produto')).toBe('foto do produto');
  });
});

describe('releitura e aba', () => {
  it('atualizar_em preso em 2..60 s; sem numero, 15 s', () => {
    expect(intervaloDeAtualizacao(5)).toBe(5000);
    expect(intervaloDeAtualizacao(1)).toBe(2000);
    expect(intervaloDeAtualizacao(0)).toBe(2000);
    expect(intervaloDeAtualizacao(-10)).toBe(2000);
    expect(intervaloDeAtualizacao(600)).toBe(60_000);
    expect(intervaloDeAtualizacao(undefined)).toBe(15_000);
    expect(intervaloDeAtualizacao('5')).toBe(15_000);
    expect(intervaloDeAtualizacao(Number.NaN)).toBe(15_000);
    expect(intervaloDeAtualizacao(Number.POSITIVE_INFINITY)).toBe(15_000);
  });
  it('alerta da aba: inteiro >= 1, senao nada', () => {
    expect(alertaDaAba(3)).toBe(3);
    expect(alertaDaAba(2.5)).toBe(2);
    expect(alertaDaAba(0)).toBeUndefined();
    expect(alertaDaAba('2')).toBeUndefined();
  });
});
