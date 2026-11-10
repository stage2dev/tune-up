// Agente de exemplo para os testes.
import type { AgenteVivo } from '../../api/agentes';

export const agente = (id: string, extra: Partial<AgenteVivo> = {}): AgenteVivo => ({
  id, tipo_agente: 'general-purpose', descricao: `Agente ${id}`, fase: null, modelo: 'sonnet', modelo_id: 'claude-sonnet-x',
  esforco: 'medium', estado: 'rodando', profundidade: 1, pai_id: null, iniciado_em: '2026-11-10T10:00:00Z',
  ultima_atividade: '2026-11-10T10:01:00Z', duracao_s: null, ferramentas: 3, ultima_acao: 'Edit painel.py', ...extra,
});
