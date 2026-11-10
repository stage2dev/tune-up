# Painel tune-up (v2)

Página local para acompanhar as fases do tune-up, as sessões e sub-agentes do Claude Code que estão rodando e as listas de trabalho, e para **rodar ações numa sessão do Claude Code em segundo plano** (um botão = um `claude --bg`).

O núcleo (esta pasta) é genérico e serve a qualquer projeto. O que é de um projeto mora fora dele:

- `<raiz>/.tune-up/painel.json`: configuração (tudo opcional);
- `<raiz>/.tune-up/<pacote>/` (padrão `painel-projeto`): ações extras, telas extras (módulos) e dados.

Sem `painel.json` e sem pacote o painel sobe do mesmo jeito, com as telas Início, Agentes, Fases, Execuções e Acompanhamento e avisos dizendo o que falta.

## Rodar

```sh
python3 <painel>/painel.py                       # http://127.0.0.1:8787/
python3 <painel>/painel.py --projeto /meu/projeto --port 8790 --plans-dir /meu/projeto/.planning
```

Raiz do projeto, nesta ordem: `--projeto`, a variável `TUNEUP_PAINEL_PROJETO`, a primeira pasta com `.tune-up/` subindo a partir do cwd, ou dois níveis acima da pasta do painel (quando ele mora em `<raiz>/.tune-up/painel`).

Testes: `python3 -B -m unittest` (nesta pasta). Python 3.9, só biblioteca padrão.

A tela em React mora em `web/` (`npm run build` gera `web/dist`). Sem `web/dist`, a raiz mostra só um aviso pedindo a build.
Em modo dev (Vite em 5173 com proxy para 8787), ponha `"origens_extras": ["http://127.0.0.1:5173"]` no `painel.json`, senão os POST dão 403.

## `painel.json`

Tipos em `contrato/api.d.ts` (`PainelJson`). Caminho relativo vale a partir da raiz. Valor ruim vira aviso e cai no padrão.

| campo | padrão |
|---|---|
| `nome` | nome da pasta raiz |
| `repo` | a raiz, se tiver `.git`; senão a 1ª subpasta com `.git` |
| `plans_dir` | `<repo>/.planning` (se tiver `phases/`), senão `<raiz>/.planning` |
| `claude_bin` | `claude` |
| `max_execucoes` | 3 (1 a 10) |
| `pular_permissoes` | `false`. Com `true`, toda sessão sai com `--dangerously-skip-permissions`: os pedidos comuns de permissão somem, mas as regras de negar e o gancho de cada ação continuam valendo (medido no CLI 2.1.322). Uma regra que "pergunta" ainda para a sessão em "precisa de você". |
| `porta` | 8787 |
| `guarda` | `guarda.py` do plugin tune-up achado em `~/.claude/plugins/installed_plugins.json`; sem plugin, segue com aviso |
| `origens_extras` | nenhuma |
| `pacote` | `painel-projeto` (nome simples de pasta dentro de `.tune-up`; atalho para fora é ignorado) |
| `modulos` | `[]` (ids de telas extras do pacote que ficam ligadas) |
| `modulos_de_plugins` | `[]` (telas extras de plugins instalados, no formato `plugin@marketplace:modulo`; ver Módulos) |
| `areas_acompanhamento` | nenhuma: toda lista cai em "geral" |
| `projeto_mem` / `claude_mem_db` | nome da pasta raiz / `~/.claude-mem/claude-mem.db` |

Exemplo:

```json
{
  "nome": "Minha Loja",
  "pacote": "painel-projeto",
  "modulos": ["vendas"],
  "areas_acompanhamento": [
    {"id": "vendas", "titulo": "Vendas", "regex": "^(vendas-|crm-)"},
    {"id": "dev", "titulo": "Desenvolvimento", "regex": ".*"}
  ]
}
```

Chave que o núcleo não conhece é ignorada, mas chega aos módulos em `ctx["config"]`.

## Pacote do projeto

```
.tune-up/<pacote>/
  acoes/*.json            ações extras (mesmo formato de acoes/dev.json, com "grupo")
  modulos/<id>/modulo.py  telas extras declarativas
  dados/                  arquivos gravados pelas ações; também o registro das execuções
```

### Módulos (telas extras)

`modulo.py` expõe `INFO = {"id", "titulo", "icone"}` e `montar(ctx) -> dict`, com `ctx = {"raiz", "pacote", "dados", "config", "hoje"}`. A resposta tem `alertas` (`{nivel: info|atencao|critico, texto}`) e `abas` (`{id, titulo, blocos}`); cada bloco tem um `tipo`: `kpis`, `tabela`, `lista`, `serie`, `texto` ou `acoes` (botões das ações de um grupo). Tipos exatos em `contrato/api.d.ts`.

- Só carrega ids listados em `modulos` (`^[a-z0-9_-]{1,40}$`), e só se o arquivo real fica dentro de `<pacote>/modulos/<id>/` (atalho para fora é recusado).
- Módulos de plugin (opt-in): `"modulos_de_plugins": ["plugin@marketplace:vendas"]` carrega `<installPath>/painel/modulos/vendas/modulo.py` do plugin instalado (`installed_plugins.json`; com várias versões vale a de `lastUpdated` mais recente). Rotas, menu e API usam só o id curto (`vendas`). Mesma checagem de caminho real (dentro de `painel/modulos/<id>/`) e mesmo `ctx`. Entrada malformada, plugin não instalado, arquivo ausente, atalho para fora, id repetido ou igual a um módulo de `modulos` é recusada com aviso e o painel segue. **Segurança:** ligar um módulo de plugin roda o código Python desse plugin dentro do processo do painel; por isso só vale se o projeto nomeia o plugin e o marketplace exatos.
- O módulo pode importar arquivos irmãos (`import util`). O import é isolado: cada módulo vê os seus irmãos, mesmo com nome igual a um arquivo do núcleo (`config.py`) ou de outro módulo, e nada fica no `sys.path` do servidor. Faça esses imports no topo do arquivo; import dentro de função não acha os irmãos.
- `montar()` roda com tempo limite de 20 s; exceção ou demora vira 500 só daquele módulo. Resultado fica 30 s em cache. `GET /api/modulos/{id}?fresco=1` monta de novo sem olhar o cache.
- Ações do módulo (opcional): `INFO["acoes"]` lista os nomes aceitos e `agir(ctx, acao, dados) -> dict` faz a ação; a tela chama `POST /api/modulos/{id}/acao` com `{"acao": texto, "dados": objeto}` e recebe `{"ok": true, "resultado": {...}}`. `dados` chega intacto ao módulo (pode levar um código de uso único digitado na tela) e o painel nunca registra nem devolve esse conteúdo. Respostas: 400 se `acao` não está em `INFO["acoes"]`, falta ou `dados` não é objeto; 404 se o módulo não existe, não está ligado ou não tem `agir`; 500 se `agir` quebra ou não devolve objeto (sem o texto da exceção, só o tipo); 503 se passa de 20 s; 409 se outra ação do mesmo módulo ainda roda. A trava das ações é separada da de `montar()` (uma tela montando não barra uma ação). Ação que dá certo apaga o cache da tela.
- Regras de negar do módulo (opcional): `INFO["negar"]` é uma lista de textos no formato do `negar` de uma ação (regra de permissão, ex. `"mcp__servico__apagar"`). O núcleo junta as regras de todos os módulos ligados no `permissions.deny` de **toda** sessão que o painel dispara. Só o `INFO` é lido (`montar()` não roda). Forma errada ou módulo que não carrega: as regras dele não valem e sai aviso em `GET /api/acoes`.
- O servidor confere a forma mínima (alerta fora do formato, aba sem `id`/`blocos` e bloco sem `tipo` saem com aviso); o resto do bloco passa como veio.

## Botões (ações)

O catálogo é `acoes/dev.json` do núcleo (grupo `dev`: Rodar Parte, Planejar fase, Investigar, Status) mais `<pacote>/acoes/*.json`. Id repetido é ignorado com aviso. Cada ação tem `grupo` (`^[a-z0-9_-]{1,40}$`; `area` ainda vale como nome antigo), `risco` (`leitura`, `rascunho`, `codigo`, `credito`) e um modelo de prompt com `{param}`.

- O navegador só manda `{acao, params}`. **O prompt é montado no servidor**; o cliente nunca manda comando.
- Validação: a ação existe; fase e Parte existem no estado atual e a Parte não está fechada; texto sem caractere de controle (nem quebra de linha), até o limite, e nunca começando com `-`; escolha só entre as opções; campo desconhecido é recusado.
- Disparo: `claude --bg -n "NOME" --settings <travas> "PROMPT"` com lista de argumentos, sem shell, `cwd` = raiz e **sem modo que pula permissão**. Rodar Parte usa o nome `Fase N Parte X`, que o leitor liga à Parte.
- Regras-objeto de `negar`/`permitir` aceitam regex de até 1000 caracteres (no JSON; dá para escrever lista do que pode com lookahead negativo, ex. `mcp__servidor__(?!(get_\\w+|list_\\w+)$).*`).
- Ação de risco `codigo` ou `credito` sempre pede confirmação na tela.
- A mesma ação com os mesmos campos rodando dá 409; passar do teto (`max_execucoes`, contando "rodando" e "precisa de você") também dá 409.
- Registro em `<pacote>/dados/execucoes.json` (pasta 0700, arquivo 0600, escrita atômica, trava de arquivo). Na subida, se só existir o registro da versão antiga (`<painel>/dados/execucoes.json`, do mesmo projeto), ele é copiado uma vez, com aviso em `/api/estado`.

### Travas da sessão (`travas.py`)

As travas vêm do JSON da própria ação, nunca de código do núcleo:

- `"negar"` / `"permitir"`: listas (até 200 cada). **Texto** vira regra de permissão do Claude Code (`permissions.deny` / `permissions.allow`), ex. `"mcp__servico__apagar"`, `"Bash(publicar *)"`. **Objeto** vira regra do gancho `PreToolUse`, que olha o conteúdo da chamada: `{"ferramenta": regex do nome inteiro, "campo"?: campo da entrada, "entrada"?: regex nesse campo (ou na entrada inteira em JSON), "decisao"?: "deny"|"ask", "motivo"?: texto}`. Regra de `permitir` que casa cala o gancho antes das de `negar`.
- Proteção fixa em toda ação: mexer em `.claude/settings*.json`, `.claude/hooks/`, `painel.json`, no núcleo ou no pacote (menos `<pacote>/dados/`) nega em `leitura`/`rascunho` e pergunta em `codigo`/`credito`. Se o gancho falhar, nega em `leitura`/`rascunho` e pergunta no resto.

### Estado de cada execução

Cruza o registro com `claude agents --json --all` (cache de 3 s). Medido no CLI 2.1.322:

| CLI | painel |
|---|---|
| `state: working` (status vazio ou `busy`) | rodando |
| `state: blocked`, `status: waiting` (pergunta ou permissão pendente) | precisa_de_voce |
| `state: done` (com `status: idle` enquanto o processo vive) | terminou |
| `state: stopped` | parada |
| some da lista nos primeiros 45 s | rodando (ainda subindo) |
| some depois (`claude rm`) | sumiu (ou terminou/parada, se já era) |

"Parar" roda `claude stop <id>`. "Abrir" abre o Terminal do macOS em `claude attach <id>`: o AppleScript é fixo e o comando vai como argumento, com o id validado. Fora do macOS só devolve o comando.

### Conversa da execução

`GET /api/execucoes/{id}/eventos?desde=N` lê `~/.claude/projects/<cwd com não-letras trocadas por ->/<sessionId>.jsonl` aos pedaços (`desde` = posição em bytes). Mostra fala do usuário, fala do assistente, ferramenta usada (com um resumo do alvo), resultado com erro e subagente disparado. Textos são cortados em 600 letras e o que parece segredo (Bearer, chave, token, senha=..., JWT, URL com senha) vira `***`.

## Segurança

- Escuta só em `127.0.0.1`; `Host` precisa ser `127.0.0.1` ou `localhost` (421).
- Todo POST exige: `X-Painel-Token` igual ao token (nasce a cada subida; comparação em tempo constante), `Origin` igual ao próprio endereço, `Sec-Fetch-Site` ausente ou `same-origin`, `Content-Type: application/json` e corpo até 16 KB (413).
- `GET /api/sessao` (que entrega o token) exige `Sec-Fetch-Site: same-origin`: sem o cabeçalho (curl, outro programa local) ou vindo de outro site dá 403. Limite aceito: navegador que não manda `Sec-Fetch-Site` (Safari antes do 16.4) não consegue mais abrir o painel.
- CSP: só `'self'` (estilo inline permitido).
- Arquivos: `/assets/*` com cache longo, `index.html` sem cache, outra rota que não seja `/api` cai no `index.html`. Nada de `..`, ponto inicial, barra invertida, byte nulo ou atalho que saia de `web/dist`.
- O leitor não segue atalho para fora do `plans_dir`, e nome de arquivo vindo do perfil (`goal`, `progress`, `later`) só vale se for nome simples.
- Módulos e ações do pacote: só dentro do pacote, sem atalho para fora.
- `POST /api/modulos/{id}/acao` passa pelas mesmas defesas de todo POST; o corpo e os `dados` nunca vão para o log nem para a resposta de erro.
- Timeout de conexão de 15 s; subprocessos com lista e timeout.

**Modelo de ameaça:** o painel dispara sessões do Claude com as permissões normais do seu usuário e executa o código Python dos módulos do pacote. Quem consegue mandar POST com o token é tratado como você. Um site de fora não consegue (origem, `Sec-Fetch-Site` e token). Um programa local não recebe o token num pedido simples a `/api/sessao`, mas pode forjar o cabeçalho `Sec-Fetch-Site`: a barreira é contra pedido descuidado, não contra outro programa decidido a atacar rodando como você. Quem escreve no pacote escreve código que o painel roda: trate o pacote como parte do projeto.

## Rotas

Tipos exatos em `contrato/api.d.ts`.

| rota | o que faz |
|---|---|
| `GET /api/sessao` | token, nome do projeto, versão |
| `GET /api/estado` | projeto, fases, Partes, PRs, sessões e avisos (inclusive os da configuração) |
| `GET /api/agentes[?sessao=<id>&todos=1]` | sessões do Claude neste projeto e os sub-agentes delas (`agentes.montar`) |
| `GET /api/acoes` | catálogo de botões |
| `POST /api/execucoes` | roda uma ação (201, 400, 409) |
| `GET /api/execucoes` | execuções, mais novas primeiro |
| `GET /api/execucoes/{id}/eventos?desde=N` | conversa aos pedaços |
| `POST /api/execucoes/{id}/parar` | `claude stop` |
| `POST /api/execucoes/{id}/abrir` | Terminal em `claude attach` |
| `GET /api/acompanhamento` | listas do claude-mem separadas por área |
| `GET /api/modulos` | telas extras ligadas e quantos alertas cada uma tem |
| `GET /api/modulos/{id}[?fresco=1]` | conteúdo de uma tela extra (`fresco=1` ignora o cache de 30 s) |
| `POST /api/modulos/{id}/acao` | ação de uma tela extra (`agir`): 200, 400, 404, 409, 500, 503 |

## De onde vêm os dados de `/api/estado`

- `guarda.py info` do plugin tune-up, para os nomes dos marcadores (e a pasta de planejamento, se o `painel.json` não disser). Sem o plugin, usa os nomes padrão.
- `phases/NNN-*/GOAL.md`: a tabela `| Parte | ... |` (ou os títulos `### Parte X`).
- `PROGRESS.md`: `Parte X fechada`, `- **X — FECHADA`, `PRECISO DE VOCÊ:` (ou a variação antiga `PRECISO DO <NOME>:`), `OPEN QUESTIONS` e as linhas de achados por volta.
- `DEPOIS.md`: as caixas `- [ ]` abertas.
- `gh pr list` (cache de 60 s) e `claude agents --json --all` (cache de 10 s).
