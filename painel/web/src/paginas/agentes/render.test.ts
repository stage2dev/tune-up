// Render da arvore com dados de exemplo (sem navegador: renderToStaticMarkup).
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { RespostaAgentes, SessaoClaude } from '../../api/agentes';
import { VisaoAgentes } from './VisaoAgentes';
import type { Recolhimento } from './CartaoSessao';
import { agente } from './exemplo';

const AGORA = Date.parse('2026-11-10T10:05:00Z');

const sessao = (id: string, extra: Partial<SessaoClaude>): SessaoClaude => ({
  id, sessao_id: `${id}-uuid`, nome: `Sessão ${id}`, tipo: 'interativa', estado: 'rodando', modelo: 'opus', esforco: 'high',
  iniciado_em: '2026-11-10T10:00:00Z', ultima_atividade: '2026-11-10T10:04:00Z', execucao_id: null,
  agentes_ativos: 0, agentes_total: 0, grupos: [], ...extra,
});

const DADOS: RespostaAgentes = {
  gerado_em: '2026-11-10T10:05:00Z',
  avisos: ['Cortei 3 agentes antigos.'],
  sessoes: [
    sessao('vazia', { estado: 'ocioso', tipo: 'segundo_plano', execucao_id: 'exec-1' }),
    sessao('cheia', {
      agentes_ativos: 3, agentes_total: 4,
      grupos: [
        {
          tipo: 'direto', id: 'diretos', nome: '', fases: [],
          agentes: [
            agente('pai', { descricao: 'Revisor principal', modelo: 'opus', esforco: 'high' }),
            agente('filho', { descricao: 'Ajudante aninhado', pai_id: 'pai', profundidade: 2, modelo: 'haiku', esforco: null, estado: 'terminou', duracao_s: 42 }),
          ],
        },
        {
          tipo: 'workflow', id: 'wf1', nome: 'Revisão em ondas', fases: ['Ler', 'Julgar'],
          agentes: [agente('w1', { fase: 'Ler', descricao: 'Leitor A' }), agente('w2', { fase: 'Julgar', descricao: 'Juiz B', modelo: 'claude-modelo-novo' })],
        },
      ],
    }),
  ],
};

const rec: Recolhimento = { recolhido: () => false, alternar: () => {} };
const desenhar = (dados: RespostaAgentes, recolhimento: Recolhimento = rec, todos = false) =>
  renderToStaticMarkup(createElement(MemoryRouter, null, createElement(VisaoAgentes, { dados, agora: AGORA, rec: recolhimento, todos })));

describe('VisaoAgentes', () => {
  const html = desenhar(DADOS);

  it('sessao sem agentes aparece com aviso e link da conversa', () => {
    expect(html).toContain('Sessão vazia');
    expect(html).toContain('Sem sub-agentes por enquanto.');
    expect(html).toContain('href="/execucoes/exec-1"');
    expect(html).toContain('Ociosa');
  });

  it('workflow com 2 fases vira 2 colunas na ordem', () => {
    expect(html).toContain('Revisão em ondas');
    expect(html).toContain('aria-label="Fase Ler"');
    expect(html).toContain('aria-label="Fase Julgar"');
    expect(html.indexOf('Leitor A')).toBeLessThan(html.indexOf('Juiz B'));
    expect(html).not.toContain('Sem fase');
  });

  it('agente aninhado fica dentro da lista do pai', () => {
    const sub = html.indexOf('aria-label="Sub-agentes de Revisor principal"');
    expect(sub).toBeGreaterThan(-1);
    expect(html.indexOf('Ajudante aninhado')).toBeGreaterThan(sub);
    expect(html).toContain('durou 42 s');
  });

  it('esforco null mostra "não informado"; modelo novo cai no chip neutro', () => {
    expect(html).toContain('Esforço: não informado');
    expect(html).toContain('data-familia="outro"');
    expect(html).toContain('data-familia="haiku"');
  });

  it('resumo conta sessoes e agentes ativos e mostra os avisos', () => {
    expect(html).toContain('agentes ativos');
    expect(html).toContain('Cortei 3 agentes antigos.');
    expect(html).toContain('3 ativos de 4');
  });

  it('sessao recolhida esconde os grupos', () => {
    const h = desenhar(DADOS, { recolhido: (c: string) => c === 's:cheia', alternar: () => {} });
    expect(h).not.toContain('Revisor principal');
    expect(h).toContain('aria-expanded="false"');
  });

  it('lista vazia explica o que fazer', () => {
    const h = desenhar({ gerado_em: '', avisos: [], sessoes: [] });
    expect(h).toContain('Nenhuma sessão do Claude neste projeto agora');
    expect(h).toContain('escolha &quot;Todos&quot;');
  });
});
