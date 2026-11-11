// Contrato da API do painel tune-up v2 (servidor Python, 127.0.0.1, porta padrão 8787).
// Núcleo genérico (servidor e lançador). Tipos exatos de toda resposta de painel.py.
// O que é de um projeto vem de <raiz>/.tune-up/painel.json e do pacote do projeto
// (<raiz>/.tune-up/<pacote>/acoes/*.json, modulos/<id>/modulo.py, dados/).
// /api/agentes: tipos detalhados em contrato/agentes.d.ts (quando existir) e no resumo abaixo.
//
// Regras gerais
// - Erro é sempre { erro: string } (texto simples, pronto para a tela), às vezes com campos extras
//   citados abaixo. Códigos: 400 pedido inválido, 403 recusado (token/origem/site), 404 não achei,
//   405 método errado, 409 já rodando ou teto, 411/413/415 corpo, 421 Host recusado, 500/503 falha.
// - Todo POST precisa de: X-Painel-Token (de GET /api/sessao), Origin = endereço do próprio painel,
//   Sec-Fetch-Site ausente ou "same-origin", Content-Type: application/json e corpo até 32 KB
//   (corpo vazio vale como {}).
// - GET aceita Sec-Fetch-Site ausente, "same-origin" ou "none"; Host tem de ser 127.0.0.1 ou localhost.

export interface Erro {
  erro: string;
}

// ---------------------------------------------------------------- GET /api/sessao
/** O token nasce a cada subida do servidor: em 403 de token, peça a sessão de novo. */
export interface RespSessao {
  token: string;
  projeto: { nome: string };
  versao: string; // ex. "2.0.0"
}

// ---------------------------------------------------------------- GET /api/estado
export type StatusParte = 'fechada' | 'precisa_de_voce' | 'rodando' | 'pendente';

export interface PR {
  numero: number;
  titulo: string;
  estado: 'OPEN' | 'MERGED' | 'CLOSED' | '?' | string; // '?' = PR só citada no PROGRESS
  branch: string;
  url: string; // '' quando não é https
  atualizada: string;
}

export interface Volta {
  volta: number | null;
  critico: number;
  alto: number;
}

export interface ItemRevisado {
  id: string;
  voltas: Volta[];
  teve_achado: boolean;
}

export interface Parte {
  id: string;
  itens_plano: string | null;
  prerequisito: string | null;
  comando_plano: string | null;
  status: StatusParte;
  origem: string; // texto livre explicando o status; não interprete
  parcial: boolean;
  pr: PR | null;
  itens: ItemRevisado[];
  comando_copiar: string; // 'claude --bg "/tune-up:part N X"'
}

export interface Pergunta {
  linha: number;
  texto: string;
}

export interface Fase {
  numero: string;
  slug: string;
  pasta: string;
  titulo: string | null;
  arquivos: { goal: boolean; progress: boolean; depois: boolean };
  acompanhada: boolean; // false = sem PROGRESS: partes = [] e fica fora dos contadores
  partes: Parte[];
  partes_fonte: string | null;
  depois_abertos: number | null;
  depois_formato: 'caixas' | 'sem_caixas' | 'sem_arquivo' | null;
  perguntas_abertas: Pergunta[];
  precisa: { parte: string | null; linha: number; texto: string }[];
  completa: boolean;
}

/** Sessão do `claude agents` (só as ativas e do workspace). */
export interface SessaoClaude {
  id: string; // id curto do bg (8 letras) ou o sessionId inteiro de uma interativa; nunca cortado
  sessao_id: string; // sessionId completo (UUID); '' se o CLI não deu
  nome: string;
  tipo: 'background' | 'interactive' | string;
  estado: string; // minúsculo: working | blocked | done | busy | idle | waiting | ...
  inicio: string | null; // ISO, minutos
  ativa: boolean;
  rodando: boolean;
}

export interface Pendencia {
  fase: string;
  parte: string | null;
  tipo: 'marcador' | 'pergunta';
  texto: string;
  origem: string;
}

export interface Estado {
  gerado_em: string;
  projeto: { nome: string };
  plans_dir: string;
  plans_origem: '--plans-dir' | 'painel.json' | 'guarda.py info' | 'padrão';
  repo: string | null;
  nomes: { goal: string; progress: string; later: string; need_you: string; part_closed: string };
  resumo: {
    fases_total: number;
    fases_acompanhadas: number;
    fases_abertas: number;
    partes_fechadas: number;
    partes_total: number;
    pendencias_dono: number;
    prs_abertas: number;
    sessoes_rodando: number;
    sessoes_ativas: number;
  };
  precisa_de_voce: Pendencia[];
  fases: Fase[];
  prs: PR[];
  sessoes: SessaoClaude[];
  avisos: string[];
}

/** Se a montagem quebrar, o servidor devolve 200 com só estes campos. */
export interface EstadoComErro {
  erro: string;
  projeto: { nome: string };
  avisos: string[];
}

export type RespEstado = Estado | EstadoComErro;

// ---------------------------------------------------------------- GET /api/acoes
/** Grupo da ação: id livre ^[a-z0-9_-]{1,40}$. O núcleo só traz "dev"; o pacote traz os outros. */
export type Grupo = string;
export type Risco = 'leitura' | 'rascunho' | 'codigo' | 'credito';

export interface ParamAcao {
  nome: string; // [a-z_][a-z0-9_]*
  rotulo: string;
  tipo: 'fase' | 'parte' | 'texto' | 'escolha';
  obrigatorio: boolean;
  opcoes?: string[]; // só em 'escolha'
  max?: number; // só em 'texto' (padrão 500, teto 2000; com `linhas`, teto 6000)
  linhas?: boolean; // só em 'texto': true aceita quebra de linha (caixa grande na tela)
  formato?: 'url'; // só em 'texto' sem linhas: o servidor exige https:// sem espaço
  ajuda?: string;
}

export type Esforco = 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export interface Acao {
  id: string;
  grupo: Grupo;
  area: Grupo; // nome antigo de `grupo`, mesmo valor
  titulo: string;
  descricao: string;
  risco: Risco;
  confirmar: boolean; // sempre true quando risco é 'codigo' ou 'credito'
  params: ParamAcao[];
  /** Modelos em ordem de preferência (apelidos do CLI: fable, opus, sonnet, haiku). [] = modelo padrão do CLI.
   *  A sessão sai com o primeiro que a licença tem (GET /api/modelos); o último é a reserva e nunca é sondado. */
  modelos: string[];
  esforco: Esforco | null; // null = esforço padrão do CLI
  /** Teto de tempo (1 a 1440). Passou: o painel roda `claude stop` e marca `falha` na execução. null = sem teto. */
  max_minutos: number | null; // desde que começou ou desde a última resposta
  max_bloqueado_min: number | null; // tempo em precisa_de_voce
  equipe: string; // texto curto para a tela, ex. "1 a 2 agentes"; '' se a ação não disser
}

// ---------------------------------------------------------------- chat (tela inicial)
// O chat não tem rota própria: cada NÍVEL é uma ação do grupo "chat" (acoes/chat.json do núcleo, mais as
// do pacote) com um único parâmetro de texto chamado `pedido` (com `linhas`). Mandar = POST /api/execucoes
// { acao: "chat.simples", params: { pedido } }. A conversa é a execução: GET .../eventos?inteiro=1 e
// POST .../responder. O 1º evento 'usuario' da conversa é o prompt montado pelo servidor (receita do nível
// + pedido): a tela mostra `execucao.params.pedido` no lugar dele.

/** GET /api/modelos — o que a licença tem, para os modelos que aparecem como 1ª opção de alguma ação.
 *  A 1ª chamada dispara a sonda em segundo plano (uns 10 s por modelo; fica guardada por 7 dias). */
export type StatusModelo = 'sim' | 'nao' | 'verificando' | 'nao_sei';
export interface RespModelos {
  modelos: Record<string, StatusModelo>;
}

export interface RespAcoes {
  acoes: Acao[];
  avisos: string[]; // arquivo ou ação do catálogo que foi ignorada
}

// ---------------------------------------------------------------- execuções
export type EstadoExecucao = 'rodando' | 'precisa_de_voce' | 'terminou' | 'parada' | 'sumiu';

export interface Execucao {
  id: string; // id curto do `claude --bg` (hex)
  sessao_id: string; // UUID completo; '' até a sessão aparecer em `claude agents`
  nome: string; // nome da sessão; Parte = "Fase N Parte X"
  acao: string;
  grupo: Grupo;
  area: Grupo; // nome antigo de `grupo`, mesmo valor
  titulo: string;
  params: Record<string, string>;
  iniciada_em: string; // ISO com fuso
  estado: EstadoExecucao;
  comando_attach: string; // "claude attach <id>"
  fase?: string;
  parte?: string;
  modelo: string; // apelido com que a sessão saiu; '' = padrão do CLI
  esforco: string; // '' = padrão do CLI
  falha?: 'max_minutos' | 'max_bloqueado_min'; // parada pelo painel ao passar do teto (estado 'parada')
  /** true quando dá para mandar outra mensagem sem interromper nada: estado terminou ou parada, e também
   *  precisa_de_voce quando a vez acabou com uma pergunta escrita (o Claude perguntou e espera o texto).
   *  Vence `pode_interromper` quando os dois vêm true. */
  pode_responder: boolean;
  /** true quando a sessão trabalha ou espera (rodando / precisa_de_voce) e dá para mandar mensagem com
   *  `interromper: true`: a vez dela para (como um Esc) e a mensagem entra na mesma conversa. */
  pode_interromper: boolean;
  /** Pergunta de múltipla escolha que a sessão quis fazer. Nos níveis do chat o AskUserQuestion é barrado
   *  (a sessão não fica presa no terminal): ela escreve a pergunta como texto e termina a vez, e o painel
   *  guarda as opções aqui (texto mascarado como o resto; vale só para a vez atual). Só vem quando `pode_responder` (o estado costuma ser precisa_de_voce); some quando
   *  o dono responde. A resposta é texto
   *  livre em /responder (a tela pode montar o texto a partir dos botões, ex. "Azul"). */
  pergunta?: PerguntaChat;
  /** true quando a espera é um pedido preso no terminal (permissão): `precisa_de_voce` sem `pode_responder`.
   *  Mandar mensagem com `interromper` CANCELA o pedido (não o aprova); aprovar é só no terminal (/abrir). */
  espera_terminal: boolean;
  /** Nomes das skills escolhidas no pedido inicial (servidor antigo nao manda). */
  habilidades?: string[];
}

export interface PerguntaChat {
  perguntas: {
    pergunta: string;
    cabecalho: string; // '' se não veio
    multipla: boolean; // true = pode marcar mais de uma
    opcoes: { rotulo: string; descricao: string }[]; // até 6; pode vir vazia
  }[]; // 1 a 4
}

/** POST /api/execucoes/{id}/responder — continua a MESMA sessão (mesmo id, mesmas travas, modelo e esforço).
 *  200 { execucao }. 400 texto vazio/ruim (até 6000 letras, aceita quebra de linha); 404; 409 se a sessão
 *  ainda trabalha ou espera e o pedido veio sem `interromper`, ou se a sessão ainda está subindo; 500 se o CLI falhar. */
export interface PedidoResposta {
  texto: string;
  /** true = vale também com a sessão rodando ou em precisa_de_voce (`pode_interromper`): interrompe e manda.
   *  Sem isso, nesses estados dá 409. */
  interromper?: boolean;
  /** ids de GET /api/habilidades (até 6; só no chat); o servidor põe o bloco das skills no fim do texto. 400 se inválido. */
  habilidades?: string[];
}
export interface RespResposta {
  execucao: Execucao;
}

/** POST /api/execucoes */
export interface PedidoExecucao {
  acao: string;
  params: Record<string, string>;
  /** ids de GET /api/habilidades (até 6; só no chat); o servidor põe o bloco das skills no fim do pedido. 400 se inválido. */
  habilidades?: string[];
}
export interface RespExecucaoCriada {
  execucao: Execucao; // 201
}
/** 409: mesma ação com os mesmos params rodando, ou teto de execuções simultâneas. */
export interface Erro409 extends Erro {
  execucao_id: string;
}

/** GET /api/execucoes (mais novas primeiro) */
export interface RespExecucoes {
  execucoes: Execucao[];
}

export type TipoEvento = 'usuario' | 'assistente' | 'ferramenta' | 'resultado' | 'subagente' | 'sistema';

export interface Evento {
  n: number; // único e crescente dentro da execução
  ts: string; // ISO (UTC) da linha da conversa; '' se não houver
  tipo: TipoEvento;
  texto: string; // até 600 letras, segredos mascarados com ***
  ferramenta?: string; // em 'ferramenta' e 'subagente'
  erro?: boolean; // true em 'resultado' (só resultados com erro aparecem) e em 'sistema'
  /** Nomes das skills escolhidas nesta fala do dono (evento 'usuario'). */
  habilidades?: string[];
}

/** GET /api/habilidades — skills do chat (cache de 60 s no servidor; nunca manda caminho de arquivo). */
export interface Habilidade {
  id: string; nome: string; titulo: string; descricao: string; grupo: string; origem: string;
  listada: boolean; // false = plugin desligado ou pasta extra: o Claude le o arquivo so quando a pessoa escolhe
  fixa: boolean; // true = tune-up: sempre ligado, nao da para escolher
}
export interface GrupoHabilidade { id: string; titulo: string }
export interface RespHabilidades { grupos: GrupoHabilidade[]; habilidades: Habilidade[]; avisos?: string[] }

/** GET /api/execucoes/{id}/eventos?desde=N[&inteiro=1] — comece com desde=0 e mande `proximo` na próxima.
 *  Com inteiro=1 as falas ('usuario' e 'assistente') vêm com até 12000 letras (chat); o resto segue em 600. */
export interface RespEventos {
  eventos: Evento[];
  proximo: number; // cursor (posição em bytes): igual a `desde` quando não há nada novo
  estado: EstadoExecucao;
}

/** POST /api/execucoes/{id}/parar */
export interface RespParar {
  ok: true;
}

/** POST /api/execucoes/{id}/abrir — ok=false fora do macOS: mostre o comando para copiar. */
export interface RespAbrir {
  ok: boolean;
  comando: string;
}

// ---------------------------------------------------------------- GET /api/acompanhamento
export type StatusItem = 'todo' | 'doing' | 'done' | 'dropped';

export interface ItemLista {
  tarefa: string;
  status: StatusItem;
  notas: string;
  produtos: { titulo: string; url: string }[];
  atualizado_em: string;
}

export interface ListaAcompanhamento {
  nome: string;
  area: string; // id de uma das `areas` (a 1ª regex de painel.json que casa) ou "geral"
  atualizado_em: string;
  aberta: boolean;
  itens: ItemLista[];
  estado: Record<string, string>;
}

export interface AreaAcompanhamento {
  id: string;
  titulo: string;
}

export interface RespAcompanhamento {
  areas: AreaAcompanhamento[]; // as de painel.json, na ordem, mais "geral" quando alguma lista caiu nela
  listas: ListaAcompanhamento[];
  avisos: string[];
}

// ---------------------------------------------------------------- GET /api/agentes[?sessao=<id>&todos=1]
// Montado por agentes.montar(cfg, sessao, todos) (módulo do núcleo). 503 { erro, avisos } se faltar;
// 400 se `sessao` não casar ^[A-Za-z0-9_-]{1,64}$.
export interface AgenteFilho {
  id: string;
  tipo_agente: string;
  descricao: string;
  fase: string | null;
  modelo: string; // curto: opus | sonnet | haiku | ...
  modelo_id: string;
  esforco: 'low' | 'medium' | 'high' | 'xhigh' | 'max' | null;
  estado: 'rodando' | 'terminou';
  profundidade: number;
  pai_id: string | null;
  iniciado_em: string | null;
  ultima_atividade: string | null;
  duracao_s: number | null;
  ferramentas: number;
  ultima_acao: string; // só nome da ferramenta + nome de arquivo, até 120 letras
}

export interface GrupoAgentes {
  tipo: 'direto' | 'workflow';
  id: string;
  nome: string;
  fases: string[];
  agentes: AgenteFilho[];
}

export interface SessaoAgentes {
  id: string;
  sessao_id: string;
  nome: string;
  tipo: 'interativa' | 'segundo_plano';
  estado: 'rodando' | 'precisa_de_voce' | 'ocioso' | 'terminou' | 'parada';
  modelo: string;
  esforco: string | null;
  iniciado_em: string | null;
  ultima_atividade: string | null;
  execucao_id: string | null; // quando foi o painel que disparou
  agentes_ativos: number;
  agentes_total: number;
  grupos: GrupoAgentes[];
}

export interface RespAgentes {
  gerado_em: string;
  sessoes: SessaoAgentes[];
  avisos: string[];
}

// ---------------------------------------------------------------- GET /api/modulos e /api/modulos/<id>
// Telas extras do pacote: <pacote>/modulos/<id>/modulo.py com INFO = {id, titulo, icone} e montar(ctx).
// Só ids listados em painel.json "modulos" (^[a-z0-9_-]{1,40}$). montar() tem 20 s; resultado fica 30 s em cache.
export interface ResumoModulo {
  id: string;
  titulo: string;
  icone: string;
  alertas: number;
}

export interface RespModulos {
  modulos: ResumoModulo[];
  avisos: string[];
}

import type { Bloco } from './blocos';
export type { Tom, Bloco, CampoFormulario, BlocoFormulario, MensagemConversa, BlocoConversa, BlocoImagem, BlocoGaleria, BlocoMidia, ReqAcaoModulo, RespAcaoModulo } from './blocos';

/** 200. 404 { erro, avisos? } se o id não está habilitado; 500 { erro, avisos } se montar() quebra ou demora;
 *  503 { erro } se uma montagem anterior ainda está rodando. O servidor confere só a forma mínima
 *  (alertas com nivel/texto, abas com id e blocos com tipo); o resto do bloco passa como veio. */
export interface RespModulo {
  id: string;
  titulo: string;
  gerado_em: string;
  alertas: { nivel: 'info' | 'atencao' | 'critico'; texto: string }[];
  abas: { id: string; titulo: string; blocos: Bloco[] }[];
  avisos: string[];
}

/** POST /api/modulos/<id>/envio?destino=<chave> — corpo = bytes crus da imagem (não é JSON nem multipart).
 *  Só para chave declarada em INFO["envios"] = { chave: { pasta (relativa a <dados>), tipos: ('png'|'jpeg'|'webp')[],
 *  max_bytes (teto 8 MB), max_arquivos (teto 500), gancho?: boolean } }. Mesmas defesas de todo POST (token, Origin,
 *  Sec-Fetch-Site, Host), sem exigir Content-Type. Content-Length obrigatório (411) e conferido antes de ler (413).
 *  Tipo pelos bytes; SVG, GIF, outro tipo, cabeçalho mentiroso ou mais de 8192 px de lado / 40 Mpx: 415.
 *  404 módulo ou chave fora da declaração; 409 pasta com atalho, limite de arquivos; 500 declaração inválida.
 *  201 arquivo novo; 200 o mesmo conteúdo já estava lá (repetido: true, nada duplicado, gancho não roda de novo). */
export interface RespEnvioModulo {
  ok: true;
  caminho: string; // relativo a <dados>: "<pasta>/<sha256 curto>.png|.jpg|.webp"
  c: string | null; // para GET /api/modulos/<id>/arquivo?c=; null se a pasta não está em INFO["midia"]
  tipo: 'png' | 'jpeg' | 'webp';
  largura: number;
  altura: number;
  repetido: boolean;
  avisos: string[]; // gancho que falhou (o arquivo já foi guardado)
}

// ---------------------------------------------------------------- módulos do núcleo que faltam ou quebram
/** /api/acompanhamento e /api/agentes quando o módulo falta (503) ou quebra (500). */
export interface ErroModulo extends Erro {
  avisos: string[];
}

// ---------------------------------------------------------------- arquivos de configuração (não são HTTP)
/** <raiz>/.tune-up/painel.json — todos os campos são opcionais. Caminhos relativos = à raiz do projeto.
 *  Raiz: --projeto, senão $TUNEUP_PAINEL_PROJETO, senão a 1ª pasta com .tune-up/ subindo do cwd,
 *  senão dois níveis acima da pasta do painel. Chave desconhecida é ignorada pelo núcleo
 *  (mas chega aos módulos em ctx.config). */
export interface PainelJson {
  nome?: string; // padrão: nome da pasta raiz
  repo?: string;
  plans_dir?: string;
  claude_bin?: string; // padrão "claude"
  max_execucoes?: number; // 1..10, padrão 3
  pular_permissoes?: boolean; // padrão false; true dispara com --dangerously-skip-permissions (as travas da ação continuam valendo)
  porta?: number; // padrão 8787
  guarda?: string; // guarda.py do tune-up (padrão: plugin achado em ~/.claude/plugins/installed_plugins.json)
  origens_extras?: string[]; // ex. "http://127.0.0.1:5173" para o Vite em modo dev
  pacote?: string; // pasta dentro de .tune-up (padrão "painel-projeto"); atalho para fora é ignorado
  modulos?: string[]; // ids habilitados (padrão [])
  modulos_de_plugins?: string[]; // "plugin@marketplace:modulo" de plugin instalado (padrão []); a API usa só o id curto
  acoes_de_plugins?: string[]; // "plugin@marketplace" de plugin instalado (padrão []); soma <installPath>/painel/acoes/*.json
  areas_acompanhamento?: { id: string; titulo?: string; regex: string }[]; // sem isso tudo cai em "geral"
  claude_projects_dir?: string; // padrão ~/.claude/projects
  projeto_mem?: string; // projeto no claude-mem (padrão: nome da pasta raiz)
  claude_mem_db?: string;
}

/** Regra do gancho de trava (objeto dentro de negar/permitir). */
export interface RegraTrava {
  ferramenta: string; // regex que casa o nome inteiro da ferramenta (ex. "mcp__servico__.*", "Bash")
  campo?: string; // campo da entrada da ferramenta (ex. "command", "file_path")
  entrada?: string; // regex procurada no campo (ou na entrada inteira em JSON)
  decisao?: 'deny' | 'ask'; // padrão deny (só em negar)
  motivo?: string;
}

/** acoes/*.json (núcleo) e <pacote>/acoes/*.json — `prompt`, `nome_sessao`, `negar` e `permitir` nunca saem na API. */
export interface ArquivoAcoes {
  acoes: Array<
    Omit<Acao, 'confirmar' | 'params' | 'area'> & {
      confirmar?: boolean;
      prompt: string; // modelo com {param}; aceita também a chave "modelo"; não pode começar com "-"
      nome_sessao?: string; // modelo do nome da sessão; sem ele usa o título
      modelos?: string | string[]; // apelido(s) do CLI em ordem de preferência ("modelo" é o nome antigo de `prompt`)
      esforco?: Esforco;
      equipe?: string; // até 60 letras
      // Só no pacote: true troca a ação do núcleo que tem o mesmo id (ex. chat.marketing com as travas do projeto).
      substitui?: boolean;
      params?: Array<Omit<ParamAcao, 'obrigatorio'> & { obrigatorio?: boolean }>;
      // Travas da sessão (até 200 cada). Texto = regra de permissão do Claude Code (deny/allow);
      // objeto = regra do gancho PreToolUse. Toda ação tem a proteção fixa (.claude/settings, painel.json,
      // núcleo e pacote fora de dados/): nega em leitura/rascunho, pergunta em código/crédito.
      negar?: Array<string | RegraTrava>;
      permitir?: Array<string | RegraTrava>;
    }
  >;
}
