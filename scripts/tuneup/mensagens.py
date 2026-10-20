"""tune-up: catalog of every message the user or the model reads (en and pt-BR).

`msg(key, *args)` picks the language (trusted project > user.json > en), fills `{owner}`
from user.json and then applies `%` with `args`. Logs (erros.log) stay in English, outside
this catalog.
"""
from .usuario import idioma_efetivo, ler_usuario

CATALOG = {
    "en": {
        # bash
        "stash_u": "git stash with untracked files deletes files in this flow; use `git worktree add` or copy to the scratchpad.",
        "stash": "stash while another session edits has already reverted work; prefer `git worktree add`.",
        "add": "other sessions edit the same repo; add files by name (`git add path`).",
        "commit_a": "other sessions edit the same repo; add files by name and run `git commit` without -a.",
        "commit_main": "direct commit on %s; create a branch from `origin/%s` first (`git switch -c <name> origin/%s`).",
        "force_main": "never force push to the main branch (%s); open a PR from a new branch.",
        "push_merged": "PR #%s already merged = dead branch (%s); create a new branch from origin/main, cherry-pick and open a new PR.",
        "gh_falhou": "could not check whether the branch's PR was already merged; check with gh pr view.",
        "gh_prazo": "could not check in time whether the branch's PR was already merged; check with gh pr view.",
        "push_main": "push to the main branch = merge; open a PR (target %s).",
        "merge_local": "git merge on the main branch (%s) = merge; that belongs to {owner} — open a PR.",
        "branch_ilegivel": "could not read the branch in %s; check with git branch --show-current.",
        "merge": "merging belongs to {owner}; leave the PR body ready and ask for the merge.",
        "empilhada": "never a stacked PR (base %s); wait for the merge and cut the branch from the main branch.",
        "perigoso": "may delete another session's work (%s); confirm or use an alternative that does not discard files.",
        "prod": "prod write without your request this turn (%s). Confirm or say \"apply the migration\".",
        "prod_cli": "command touches a remote database/project (%s); confirm first — an authorization phrase does not unlock it.",
        "pesquisa": "research mode on (%s); confirm or say \"go ahead\" to leave it.",
        "ps_ilegivel": "could not read this PowerShell command (%s); confirm it.",
        "prot_settings_bash": "the command writes to Claude's permissions and hooks (settings*.json); confirm.",
        "prot_perfil_bash": "the command writes to the tune-up profile/plugin/trust list; "
                            "confirm, or say \"new rule\" or run /tune-up:profile this turn.",
        "regra_projeto": "project rule",
        # sql_prod
        "prod_mcp": "prod write through MCP (%s); confirm first — an authorization phrase does not unlock this tool.",
        # escrita
        "prot_settings_escrita": "%s touches Claude's permissions and hooks; confirm.",
        "prot_perfil_escrita": "%s is the tune-up profile/plugin/trust list; "
                               "confirm, or say \"new rule\" or run /tune-up:profile this turn.",
        "pesquisa_escrita": "research mode on: confirm editing %s?",
        # agent
        "fable": "subagents never run on Fable ({owner}'s rule). Use haiku (map/check), "
                 "sonnet (document/simple item) or opus (database/risky/review).",
        "fable_sessao": "the session is on Fable and the subagent would inherit it; declare model "
                        "(haiku, sonnet or opus).",
        "modelo_nao_lido": "tune-up: could not read the session model; declare model in the Agent call.",
        "revisor_opus": "tune-up: reviewers run on opus high; switch model to opus.",
        "regra_revisor": "reviewers run on opus high",
        "regra_esforco": "default effort",
        "preenchido": "tune-up: filled %s (%s)",
        # prompt
        "pesquisa_liga": "tune-up: RESEARCH MODE — do not change code, data or anything external; "
                         "save findings only in the scratchpad/plans folder and end with numbered "
                         "questions (recommended first). Leave with \"go ahead\".",
        "pesquisa_desliga": "tune-up: research mode off.",
        "auth_detectada": "tune-up: authorization phrase detected (\"%s\"). Valid only for the prod target named "
                          "this turn; confirm the target before writing.",
        "segredo": "tune-up: a secret was pasted in this prompt — never repeat it, never save it in a "
                   "file, memory or PR; remind {owner} to rotate it at the end.",
        "regra_nova": "tune-up: looks like a new rule — record it with /tune-up:learn (memory + plugin).",
        # pos_bash
        "pr_aberta": "tune-up: PR opened — in the body: SQL→merge→deploy order at the top, what did NOT run "
                     "(CI/tests) and what {owner} tests; update PROGRESS; merging belongs to {owner}.",
        # sessao
        "inicio_projeto": "tune-up: project %s — profile at %s (read it before plan, part, investigate, "
                          "ship, migration). Merge: %s.",
        "inicio_compact": "tune-up: context compacted — before continuing check git status, "
                          "origin/main, gh pr and the Part's PROGRESS; do not trust the summary alone.",
        "inicio_linha": "tune-up: language %s, owner %s, reply style %s.",
        "inicio_setup": "tune-up: no user profile yet — run /tune-up:setup.",
        "cfg_invalido": "tune-up: project config.json invalid: %s; using only the defaults.",
        "cfg_tipos": "tune-up: config with wrong types; discarded: %s (see erros.log).",
        "nao_confiado": "tune-up: profile %s not trusted: run /tune-up:profile",
        "perfil_mudou": "tune-up: profile %s changed since it was trusted; run trust again "
                        "(/tune-up:profile) before its loosening keys count.",
        "confiaveis_sem_hash": "tune-up: %d old line(s) in perfis_confiaveis.txt have no content hash "
                               "and no longer count as trusted; trust those profiles again.",
        "protected_paths_ignorados": "tune-up: user.json protected_paths ignored (not absolute or not "
                                     "text): %s",
        "erros_hooks": "tune-up: %d hook errors since the last session; see %s",
        # confiar / main
        "confiar_falhou": "tune-up: could not trust the profile (%s)",
        "confiar_nao_existe": "tune-up: %s does not exist",
        "confiar_ok": "tune-up: profile trusted: %s",
        "owner_padrao": "the owner",
        # agent (forbidden models from user.json)
        "modelo_proibido": "subagents never run on %s (forbidden_subagent_models in the user profile). "
                           "Declare another model (haiku, sonnet or opus).",
        "modelo_proibido_sessao": "the session is on %s and the subagent would inherit it; declare model "
                                  "(haiku, sonnet or opus).",
        # talk mode (/tune-up:talk)
        "talk_liga": "tune-up: TALK MODE (/tune-up:talk) — conversation only: no code changes; notes go "
                     "to .md in docs/, the plans folder, .tune-up/, memory or the scratchpad. "
                     "Leave with \"let's build\".",
        "talk_desliga": "tune-up: talk mode off.",
        "user_json_invalido": "tune-up: user.json invalid (%s); using the defaults — fix it or run /tune-up:setup.",
        "talk_codigo": "talk mode on (/tune-up:talk): no code changes (%s). Say \"let's build\" to leave it.",
        "talk_pergunta": "talk mode on (/tune-up:talk): confirm writing %s? Say \"let's build\" to leave it.",
        "linhas_nega": "%s would have %s lines (limit %s); split the file or put `tune-up: allow-long <reason>` in the first 5 lines.",
        "linhas_avisa": "%s already had %s lines and grows to %s (limit %s); consider splitting it.",
    },
    "pt-BR": {
        "stash_u": "git stash com não rastreados apaga arquivos neste fluxo; use `git worktree add` ou copie para o scratchpad.",
        "stash": "stash com outra sessão editando já reverteu trabalho; prefira `git worktree add`.",
        "add": "outras sessões editam o mesmo repo; adicione os arquivos pelo nome (`git add caminho`).",
        "commit_a": "outras sessões editam o mesmo repo; adicione os arquivos pelo nome e rode `git commit` sem -a.",
        "commit_main": "commit direto na %s; crie branch da `origin/%s` antes (`git switch -c <nome> origin/%s`).",
        "force_main": "nunca force push na principal (%s); abra PR de uma branch nova.",
        "push_merged": "PR #%s já mergeada = branch morta (%s); crie branch nova da origin/main, cherry-pick e abra PR nova.",
        "gh_falhou": "não consegui checar se a PR da branch já foi mergeada; confira com gh pr view.",
        "gh_prazo": "não consegui checar a tempo se a PR da branch já foi mergeada; confira com gh pr view.",
        "push_main": "push na principal = merge; abra PR (alvo %s).",
        "merge_local": "git merge na principal (%s) = merge; o merge fica com {owner} — abra PR.",
        "branch_ilegivel": "não consegui ler a branch em %s; confira com git branch --show-current.",
        "merge": "o merge fica com {owner}; deixe o corpo da PR pronto e peça o merge.",
        "empilhada": "PR empilhada nunca (base %s); espere o merge e corte a branch da principal.",
        "perigoso": "pode apagar trabalho de outra sessão (%s); confirme ou use uma alternativa que não descarte arquivos.",
        "prod": "escrita em prod sem pedido seu neste turno (%s). Confirme ou diga \"pode aplicar\".",
        "prod_cli": "comando que mexe em banco/projeto remoto (%s); confirme antes — frase de autorização não libera.",
        "pesquisa": "modo pesquisa ativo (%s); confirme ou diga \"pode fazer\" para sair.",
        "ps_ilegivel": "não consegui ler este comando do PowerShell (%s); confirme.",
        "prot_settings_bash": "o comando grava nas permissões e hooks do Claude (settings*.json); confirme.",
        "prot_perfil_bash": "o comando grava no perfil/plugin/lista de confiança do tune-up; "
                            "confirme ou diga \"regra nova\"/\"perfil\" neste turno.",
        "regra_projeto": "regra do projeto",
        "prod_mcp": "escrita em prod pelo MCP (%s); confirme antes — frase de autorização não libera esta ferramenta.",
        "prot_settings_escrita": "%s mexe nas permissões e hooks do Claude; confirme.",
        "prot_perfil_escrita": "%s é perfil/plugin/lista de confiança do tune-up; "
                               "confirme ou diga \"regra nova\"/\"perfil\" neste turno.",
        "pesquisa_escrita": "modo pesquisa ativo: confirma editar %s?",
        "fable": "subagente nunca roda em Fable (regra de {owner}). Use haiku (mapear/conferir), "
                 "sonnet (documento/item simples) ou opus (banco/arriscado/revisão).",
        "fable_sessao": "a sessão está em Fable e o subagente herdaria; declare model "
                        "(haiku, sonnet ou opus).",
        "modelo_nao_lido": "tune-up: não li o modelo da sessão; declare model no Agent.",
        "revisor_opus": "tune-up: revisor roda em opus high; troque model para opus.",
        "regra_revisor": "revisor roda em opus high",
        "regra_esforco": "esforço padrão",
        "preenchido": "tune-up: preenchido %s (%s)",
        "pesquisa_liga": "tune-up: MODO PESQUISA — não altere código, dados nem nada externo; "
                         "salve achados só no scratchpad/pasta de planos e termine com perguntas "
                         "numeradas (recomendada primeiro). Sai com \"pode fazer\".",
        "pesquisa_desliga": "tune-up: modo pesquisa desligado.",
        "auth_detectada": "tune-up: frase de autorização detectada (\"%s\"). Vale só para prod citado "
                          "neste turno; confirme o alvo antes de escrever.",
        "segredo": "tune-up: há segredo colado neste prompt — nunca repita, nunca grave em "
                   "arquivo, memória ou PR; lembre {owner} de rotacionar no fim.",
        "regra_nova": "tune-up: parece regra nova — registre com /tune-up:learn (memória + plugin).",
        "pr_aberta": "tune-up: PR aberta — no corpo: ordem SQL→merge→deploy no topo, o que NÃO rodou "
                     "(CI/testes) e o que {owner} testa; atualize o PROGRESS; o merge fica com {owner}.",
        "inicio_projeto": "tune-up: projeto %s — perfil em %s (leia antes de plan, part, investigate, "
                          "ship, migration). Merge: %s.",
        "inicio_compact": "tune-up: contexto compactado — antes de continuar confira git status, "
                          "origin/main, gh pr e o PROGRESS da Parte; não confie só no resumo.",
        "inicio_linha": "tune-up: idioma %s, dono %s, estilo de resposta %s.",
        "inicio_setup": "tune-up: ainda sem perfil de usuário — rode /tune-up:setup.",
        "cfg_invalido": "tune-up: config.json do projeto inválido: %s; usando só o padrão.",
        "cfg_tipos": "tune-up: config com tipo errado; descartei: %s (veja o erros.log).",
        "nao_confiado": "tune-up: perfil %s não confiado: rode /tune-up:profile",
        "perfil_mudou": "tune-up: o perfil %s mudou desde a confiança; rode trust de novo "
                        "(/tune-up:profile) para as chaves que afrouxam valerem.",
        "confiaveis_sem_hash": "tune-up: %d linha(s) antiga(s) do perfis_confiaveis.txt sem hash do "
                               "conteúdo não contam mais como confiadas; confie esses perfis de novo.",
        "protected_paths_ignorados": "tune-up: protected_paths do user.json ignorado (não absoluto ou "
                                     "não é texto): %s",
        "erros_hooks": "tune-up: %d erros nos hooks desde a última sessão; veja %s",
        "confiar_falhou": "tune-up: não consegui confiar o perfil (%s)",
        "confiar_nao_existe": "tune-up: %s não existe",
        "confiar_ok": "tune-up: perfil confiado: %s",
        "owner_padrao": "o dono",
        "modelo_proibido": "subagente nunca roda em %s (forbidden_subagent_models do perfil). "
                           "Declare outro model (haiku, sonnet ou opus).",
        "modelo_proibido_sessao": "a sessão está em %s e o subagente herdaria; declare model "
                                  "(haiku, sonnet ou opus).",
        "talk_liga": "tune-up: MODO CONVERSA (/tune-up:talk) — só conversa: nada de mudar código; notas "
                     "vão para .md em docs/, na pasta de planos, em .tune-up/, na memória ou no scratchpad. "
                     "Sai com \"pode construir\".",
        "talk_desliga": "tune-up: modo conversa desligado.",
        "user_json_invalido": "tune-up: user.json inválido (%s); usando o padrão — corrija ou rode /tune-up:setup.",
        "talk_codigo": "modo conversa ativo (/tune-up:talk): sem mudar código (%s). Diga \"pode construir\" para sair.",
        "talk_pergunta": "modo conversa ativo (/tune-up:talk): confirma gravar %s? Diga \"pode construir\" para sair.",
        "linhas_nega": "%s ficaria com %s linhas (limite %s); divida o arquivo ou ponha `tune-up: allow-long <motivo>` nas 5 primeiras linhas.",
        "linhas_avisa": "%s já tinha %s linhas e cresce para %s (limite %s); considere dividir.",
    },
}
_ESTADO = {"idioma": None}


def definir_idioma(cfg):
    """Called once per hook run, after the project config is loaded."""
    _ESTADO["idioma"] = idioma_efetivo(cfg)


def idioma():
    lang = _ESTADO["idioma"] or idioma_efetivo(None)
    return lang if lang in CATALOG else "en"


def dono():
    return ler_usuario()[0]["owner"] or CATALOG[idioma()]["owner_padrao"]


def msg(chave, *args):
    """Format with `args` FIRST, then fill `{owner}` (an owner with `%` must not break it).
    Unknown key: log and return the key itself (never raise inside a hook)."""
    tab = CATALOG[idioma()]
    texto = tab.get(chave) or CATALOG["en"].get(chave)
    if texto is None:
        from .sessao import log_erro
        log_erro("msg", "unknown message key %r" % (chave,))
        return chave
    texto = texto % args if args else texto
    if "{owner}" in texto:
        texto = texto.replace("{owner}", dono())
    return texto
