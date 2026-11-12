# CHANGELOG - tune-up

Every new rule goes in through `/tune-up:learn`: memory + a change here + a test/eval + a version.

## 2.10.0

Module screens get an inbox block and refresh faster; a module action that says it failed now shows as an error, and another plugin joins the marketplace.

- New block `caixa` (inbox): a list of conversations (title, one-line preview, relative time, unread badge, status seal, the open one highlighted, text search in the browser) next to the open conversation. Clicking a row posts `{acao: abrir.acao, dados: {...abrir.dados_fixos, conversa_id}}` through the module action route; the row shows "abrindo…" until the fresh reload lands, and a failed action shows the server message. Up to 768 px wide it shows one pane at a time with a back button. Rows are buttons with a visible focus ring. The server drops a `caixa` without `conversas` or `abrir.acao`, and rows without `id`/`titulo`, with a warning.
- Conversation messages may carry `tipo` (`texto`, `audio`, `imagem`, `documento`, `outro`): anything but text shows as a labelled chip ("Áudio – ouça no celular") instead of a raw `[audio]`. Balloons use the chat's look, with the time in each balloon and a separator per day. Enter sends and Shift+Enter breaks the line (same as the chat box). The list follows new messages only when you are already at the bottom.
- A module response may carry `atualizar_em` (seconds, clamped to 2..60 by the server and the screen; 15 without it). The screen reloads at that pace and stops while the browser tab is hidden. Text being typed is never overwritten.
- A tab may carry `alerta` (integer >= 1), shown as a small badge next to its title.
- `POST /api/modulos/<id>/acao`: when the module's `agir` returns `{ok: false, mensagem}`, the panel answers 422 with that message, so the screen shows an error and never "Feito.".
- New plugin `tune-up-vendas` 0.1.0 in `vendas/` (own marketplace entry, own README, CHANGELOG and tests; CI step "Sales module tests"). It is off until a project lists it in `modulos_de_plugins`. Nothing in the core imports it.
- Merged with 2.9.0 (studio Brand tab): the new blocks `cores`, `envio`, `previa`, `opcoes` and the `caixa` block live side by side; the upload route and the 422 on `{ok: false}` both apply.
- To keep `painel/modulos.py` under 450 lines after the merge, the response shape check (`conferir`, `ErroModulo`) moved to `painel/modulos_forma.py`; `modulos.conferir` and `modulos.ErroModulo` still work.
- Conversation media: a message may carry `midia` (`ref`, `tipo` audio/imagem/documento, `nome`, `tamanho`, `duracao`, `estado` pronta/pendente/falhou/expirada, `aviso`, `acao`) and `transcricao`. The screen shows a native audio player (`preload="none"`) with the duration and the transcription under it, an image thumbnail that opens a lightbox (Esc closes) with a download link, or a document row with name, size and "Baixar"; "baixando…" while pending, and the warning plus "Tentar de novo" (through the module action route) when it failed or expired. The URL is built only from the page's module id and the `ref`, never from a URL sent by the module. The server drops a malformed `midia` or `transcricao` with a warning. Without `midia` the `tipo` chip stays.
- `GET /api/modulos/<id>/arquivo?ref=<ref>` (same route as the media folder's `?c=`): serves the bytes returned by the module's optional `arquivo(ctx, ref)`. Requires `Sec-Fetch-Site: same-origin` (403 otherwise, also when the header is missing); `ref` up to 200 chars of `[A-Za-z0-9._:-]`, no `..`, no leading dot (400 before the module is called); mime allowlist (415), 25 MB cap (413), 20 s limit in a thread (504), at most 4 calls at once (503). Responses carry `nosniff`, `Cache-Control: private, max-age=300`, `Content-Security-Policy: default-src 'none'; sandbox`, and an attachment `Content-Disposition` (sanitized ASCII name + RFC 5987 `filename*`) for PDF, octet-stream or `baixar: true`. One `Range` gives 206. Nothing is written to disk and the `ref` value is masked in the request log.
- Screen type mirror (`web/src/api/tipos.ts`) gains `BlocoCaixa` and `MensagemConversa.tipo`, matching `contrato/blocos.d.ts`.
- `painel/web/dist` rebuilt.

## 2.9.0

Studio plan, Part 10: a friendly Brand tab, `tune-up-studio` 0.3.0.

- Panel core: `POST /api/modulos/{id}/envio?destino=<key>` takes one raw image per request for modules that declare `INFO["envios"]`. Same token and origin checks as the other POST routes, `Content-Length` required and checked before reading, 8 MB ceiling, type decided by the bytes (PNG, JPEG, WebP; dimensions read from the header and capped), file name chosen by the server, atomic write without following links. **SVG is refused**: no strict validator was written.
- Panel screen: four new blocks, `cores` (color pickers with a low-contrast warning), `envio` (drag or pick a file, progress, errors in plain words), `previa` (a sample post that follows the edits right away) and `opcoes` (cards and on/off chips).
- Studio: the Brand tab is now logo, business photos (up to 8), five colors in plain words, font pairs shown already written, the business in a few words, a live preview and one confirm button. Any change (color, font, logo, photo, text) drops the approval. "Take the colors from the logo" works for PNG and SVG logos only.
- Studio: posts, videos and ads may use up to two business photos, copied by `scripts/fotos.py`; text always sits on a brand-color block. QA accepts images only from `assets/` inside the piece source.
- Proven by clicking through the screen with one real Opus session: upload a logo and two photos, change a color and a font, confirm the brand, ask for a post that uses the photo, approve it.
- Not proven: the Brand tab after the last review fixes was not looked at in a browser; video and ad with a photo in a real session; Safari; Linux and Windows for the studio (CI does not run `tune-up-studio/tests`).

## 2.8.0

Studio plan, Parts 1 to 9, and the new plugin `tune-up-studio` 0.2.0: posts, carousels, short videos and ads made from the project's brand, rendered locally and checked by scripts, run from the panel.

Part 1, mechanisms in the panel core (proven with real background sessions):

- Actions can declare a `sandbox` block, a work folder (`{trabalho}`, created by the server before launch; the session runs with that folder as cwd), a long text parameter saved to a file, `env`, and time limits (`max_minutos`, `max_bloqueado_min`: the panel stops the session and frees the slot).
- Guard hook: relative paths in Bash are resolved against the session cwd; `dados/../` no longer escapes; backslash escapes (`.cla\ude`) are read the way a POSIX shell reads them; the owner approval file and `aprovados/` are never writable by a session.
- Measured on CLI 2.1.32x with a fixture action, `pular_permissoes` on and off: network (curl, ffmpeg over https, WebFetch, MCP) denied; writes outside the work folder denied by Bash and by Write; `.env` unreadable; one write inside the work folder accepted; headless Chrome renders a frame inside the sandbox with no extra flag; model and effort reach the session.
- `claude --bg` refuses a folder that is not trusted, and inside a git repository trust is checked at the git root. The launch error now shows the cause.
- `tune-up-studio/node/`: HyperFrames pinned to 0.9.6 with a lockfile (newest stable release at least 7 days old on 2026-11-10); install with `npm ci --ignore-scripts`, then `npm audit signatures`. Known: `npm audit` reports undici 7.25.0 (pinned by HyperFrames, also in its latest release).
- Not proven: the effect of `worktree.bgIsolation` inside a git project.

Part 2, a real post and a real video from a neutral example project, without GSAP:

- `tune-up-studio/exemplos/forno-miudo/`: fictional bakery with a brand answer key, a 4:5 post (1080x1350) and a 10 s 9:16 video (1080x1920), both plain HTML and CSS keyframes. HyperFrames 0.9.6 seeks CSS-only animation frame by frame (measured), so GSAP is not needed and HyperFrames stays as the engine.
- `tune-up-studio/scripts/`: `qa_imagem.py` and `qa_video.py` (stdlib + ffprobe). They catch the planted defects (text overflow, one black second, layout-silencing attributes, a runtime-built external fetch) and, after review, truncated PNG/MP4 files and a check report that belongs to another piece. `reserva_slides.py` builds an FFmpeg slide video when HyperFrames is unavailable.
- `tune-up-studio/regras/bash-estudio.json`: positive list of commands for studio sessions (HyperFrames subcommands, ffmpeg with `-protocol_whitelist file,pipe`, the studio scripts), as hook rules.
- Sandbox: `"sandbox": {"rede_local": true}` turns on `sandbox.network.allowLocalBinding`. HyperFrames `render` needs it (it listens on 127.0.0.1); `snapshot` does not. **Measured risk on macOS: with it on, the page being rendered can reach any service on localhost and on the machine's own LAN address; the outside network stays closed.** Off by default.
- Measured (provisional): render of the 10 s video about 5 s and 460 MB; a background session that renders it about 21 s and 175k tokens (mostly cache).
- Guard hook on Windows: the allowed `dados` folder is recognised with mixed separators (simulated; CI is the proof).

Parts 3 to 9, the studio:

- Actions from installed plugins, opt-in per project in `painel.json` (`acoes_de_plugins`), pinned by version and sha256; a changed plugin is refused until `--aceitar-extensao` (`painel/extensoes.py`). Plugins with bytecode in `painel/` are refused.
- Module commands take a schema. The owner's approval is written only by the server (`painel/dono.py`); an action with `requer` runs only after that approval and only with `sandbox`. Brand approval is bound to the sha256 of `marca.json`: a brand changed after approval answers 409 again.
- Guard hook: denies writes that name the owner files anywhere; sandboxed sessions cannot Write/Edit HyperFrames reports in `.hyperframes/`, and only the pinned hyperframes may cite that folder in Bash (paths are NFKC-folded first).
- `rede_local` needs `so_com`: an action with it exists only in a project that turns on the named key. `estudio.video-motion` (HyperFrames render) needs `"estudio": {"video_rede_local": true}` in `painel.json`; without it video goes through the FFmpeg slide reserve, which opens no local port.
- `tune-up-studio` plugin: environment checker and a deterministic "Preparar estudio" script, `formatos.json` v1 (sizes, text limits, safe zones), brand discovery (`marca.json`, `MARCA.md`, logo copy, a no-brand mode) and local font stacks.
- Skills and actions: `marca` / `marca-ler`, `post` (`estudio.post`, post and carousel), `video` (`estudio.video` by slide reserve, `estudio.video-motion` by render) and `anuncio` (`estudio.anuncio`: one piece per platform ratio, texts checked by script, `export/google-ads-editor.csv` generated by script with every row `Paused`, Google images clean for Search, the 9:16 safe zone checked by machine; the Meta sheet is marked experimental).
- QA scripts judge what HyperFrames saved on disk, not what the session reports; a stale MP4, a failed font, a stopped or short piece stays red. A session's QA result can only lower the seal; the server recomputes it.
- Panel: media route `GET /api/modulos/{id}/arquivo?c=` with Range (206/416), realpath and `O_NOFOLLOW`, CSP `media-src`; new blocks `galeria` and `midia`; the `formulario` block can start a catalog action, with confirmation. `.csv` downloads only from `aprovados/`, as an attachment.
- Studio screen (module `estudio`): tabs Ambiente, Marca, Novo, Fila, Galeria, Aprovação, with a step-by-step guide; piece approval writes `manifesto.json` with the server's sha256; plain-language texts; the module run page is in words, with "Voltar para".
- Merge with 2.6.0/2.7.0 (chat without the terminal, skills list): the chat skills block survives the prompt rebuilt with the work folder; a sandboxed session cannot be answered or interrupted from the chat (`--resume` does not carry the `--settings` with the sandbox block). To keep files under 450 lines, `registro.py` and `pergunta.py` came out of `lancador.py` and `travas_validar.py` out of `travas.py`.
- Measured in real opus sessions: post 4:5 57 s; carousel of 5 139 s; 15 s reel by reserve 129 s; 10 s reel by render 144 s; Google ad set 2 of 2 in 369 s. Each piece cost about 0.7 to 1.4 million tokens, almost all of it cache reads. The screen flow was driven by clicks in headless Chrome: environment, brand approval, post, queue, approval, video playing in the gallery.
- Measured risks: `rede_local` on macOS lets the rendered page reach localhost and the machine's LAN address (off by default; on Linux the key has no effect). A session WITHOUT sandbox in the same project can still write the approval file by indirect paths; accepted and documented (such a session already has the owner's whole disk), and every studio action with `requer` must run with sandbox. `npm audit` reports undici 7.25.0, pinned by hyperframes 0.9.6.
- Not proven: Safari (video playback and the screen); Linux; Windows only through CI; the Meta sheet without a real session after the final skill; importing the CSV into Google Ads Editor (an owner test; a CSV without BOM may break accents there); the effect of `worktree.bgIsolation` inside a git project.
- `painel/web/dist` rebuilt.

## 2.7.0

The panel chat has a list of skills to pick from.

- The left column of the chat has two views, "Conversas" and "Skills". The skills list has a search box and groups by theme (marketing, sales, design and UX, code, review and security, database, research and documents, video and media, others) or by plugin. Click a skill or drag it into the message box; it becomes a tag above the text (up to 6 per message). The request balloon shows the skills that went with it.
- `GET /api/habilidades` lists skills from installed plugins, the user's skills, the project's skills and optional extra folders (`habilidades_pastas` in `painel.json`). Skills of a disabled plugin or of an extra folder are marked "off the list": the session reads their `SKILL.md` by path instead of calling the Skill tool. Skills of `tune-up` and `tune-up-*` plugins show as always on and cannot be picked. Theme rules live in `painel/habilidades.json` (the skill and plugin name are matched before the description); the project package can add `habilidades.json` with its own rules and a plugin-to-group map.
- `POST /api/execucoes` and `POST .../responder` take `habilidades` (ids from the list, chat levels only). The server, never the screen, appends a short block to the prompt naming the chosen skills and saying the tune-up flow always applies; the block is stripped from the transcript and the event carries `habilidades`. A message that already contains one of the block's marker lines is refused.
- Skill files are untrusted: read without blocking, regular files only, 8 KB cap, names and folder names checked, descriptions masked, no file path sent to the screen. A plugin registry or settings file that cannot be read becomes a warning in the list.
- Picking skills tells the session which ones to use; it does not unload the others. Measured on CLI 2.1.322: `--settings` with `enabledPlugins` does start a session with fewer plugins, but the option is lost when the session is resumed, so the panel does not use it.
- `painel/web/dist` rebuilt.

## 2.6.0

The panel chat no longer needs the terminal.

- One screen: `/` and `/conversa/:id` draw the same chat (conversation list, conversation, box at the bottom) with a "who is working" side panel that shows the main session and its sub-agents live.
- Questions come to the chat. In chat levels (and actions with `"perguntas_no_chat": true`) the guard hook denies `AskUserQuestion`, stores the options and tells the session to ask in text and end its turn; the run then carries `pergunta` and `pode_responder`. Option buttons only fill the box; the person sends. Measured on CLI 2.1.322: a session blocked on `AskUserQuestion` has not written the question to the transcript yet, and a turn that ends with a written question shows as `blocked` + `idle`.
- Send a message while the session works or waits: `POST .../responder {texto, interromper: true}` (`pode_interromper`) stops its turn and wakes the same session with the message. On a permission prompt stuck in the terminal (`espera_terminal`) this cancels the prompt; the screen says so and keeps "open in terminal". The refusal for changed module rules covers this path too.
- The stored question is untrusted: read without blocking, regular files only, 64 KB cap, masked like everything else shown from a session, and dropped when it is older than the current turn or the session moved on.
- "Working" after a reply now ends as soon as the session has answered, not after a fixed wait. The CLI's automatic "No response requested." line is hidden.
- `painel/web/dist` rebuilt.

## 2.5.0

The panel closes the token door, masks what it shows and lets modules act.

- `GET /api/sessao` (the token) now answers only with `Sec-Fetch-Site: same-origin`. curl, other local programs and browsers that do not send `Sec-Fetch-Site` (Safari before 16.4) get 403 and can no longer run actions.
- Phones, e-mails and keys are masked in everything the panel shows from a session: transcript events (`cortar()` in `transcricao.py` is the single funnel, rules in `painel/mascara.py`), agents, tracking, and the request text and names of executions (the chat list and the first balloon). The registry still keeps the raw text.
- Module actions: `POST /api/modulos/{id}/acao` runs `agir` of an enabled module behind the same defenses as every POST; `dados` never goes to the log or to an error reply. `GET /api/modulos/{id}?fresco=1` skips the cache. A module's `INFO["negar"]` joins the deny rules of every session the panel starts, chat levels included. Fail-closed: an enabled module that does not load (or has an invalid `negar`) blocks every panel action with 409 until it is fixed or disabled in `painel.json`. Replies (`responder`) resume the session with the rules it was started with, so each session records the module deny rules it started with (`negar_modulos`) and a reply is refused with 409 before anything is stopped or resumed when an enabled module does not load or when the current module rules are not all among the recorded ones (a module enabled or changed after the session started); `pode_responder` is false in those cases (rules read with a 2 s limit, false on error). Entries recorded before this have no rules, so they can still be answered only while no module has deny rules. Session names are built from masked values (`-n`, registry) and `GET /api/estado` masks `sessoes[].nome`.
- `modulos_de_plugins` in `painel.json`: extra screens from installed plugins, as `plugin@marketplace:modulo`.
- New module blocks: `formulario`, `conversa` and `imagem`.
- `painel/web/dist` rebuilt from these sources.

## 2.4.3

Panel on Windows, from the first real CI run of the panel tests there (24 of 160 failed).

- Guard hook (`painel/travas.py`): the fixed protection of settings, the panel and the project package only understood `/`. Paths now go through one normaliser (backslash to slash, `.` and `..` resolved with `posixpath`, drive prefix, case-insensitive when the path looks like Windows or the system is Windows) on both sides of the comparison, added to the old checks, never replacing them. The allowed `dados` folder only counts when followed by a separator: `dadosx/` and `dados.json` are denied. Not yet proven on a real Windows session.
- Dates: `agora_iso` and `iso_local` build timezone-aware datetimes; the naive form raised `OSError 22` on Windows for small timestamps. Same ISO text as before in 7 time zones.

## 2.4.2

- Tests: `test_pitfall_skills_limite` hung on Windows, it was never slow. The test waited for `info` to exit before reading its stdout from a pipe; with 200 skills the answer is larger than a Windows pipe buffer (about 4 KB), so the child blocked on write and the wait timed out at any limit. stdout now goes to a temp file and the limit is back to 5 s. 2.4.1 raised the limit to 30 s on a wrong guess.

## 2.4.1

Panel groundwork (Part 0 of the studio plan).

- Panel on Windows: the run-registry lock moved to `painel/trava.py` and uses `msvcrt.locking` there (`fcntl.flock` elsewhere), same interface. Reading and replacing `execucoes.json` retry on `PermissionError` (Windows refuses to replace a file another thread has open); a persistent read error now raises instead of looking like an empty list. Panel tests run on all three systems in CI. Not yet proven on a real Windows machine: CI is the proof.
- CI: new `panel-web` job (Ubuntu) installs, tests and rebuilds the screens from an empty `dist` and fails when the committed build is stale. A rebuild must start from an empty `dist` (the CSS scanner reads the old bundle otherwise); `painel/README.md` says so.
- `info`: `pitfall_skills` does one `realpath` per plugin instead of one per file. `test_pitfall_skills_limite` went past 5 s on Windows runners; the cause was not measured, so the test now prints the time and waits up to 30 s (other tests keep 5 s).

## 2.4.0

The panel's home screen is now a chat.

- Home (`/`) is a chat: write the request, pick a level. The old home moved to `/resumo`. Each level is an action of group `chat` in `painel/acoes/chat.json`: ask only (sonnet, read-only), simple fix (opus, 1 reviewer, PR), moderate fix (opus high, executors + up to 2 reviewers, one PR), full change (fable, falling back to opus; `/tune-up:plan` with 2 Opus plan reviewers; no code), marketing (opus, drafts only).
- Any action may now set `modelos` (one alias or a preference list), `esforco` and `equipe`. The session starts with the first model the license has; the last one is the fallback. The panel probes the license once with a minimal `claude -p` (about 900 tokens), cached 7 days in the project's `dados/modelos.json`; `modelos_disponiveis` in `painel.json` overrides it.
- Reply in the same conversation: `POST /api/execucoes/{id}/responder`. It stops the idle process, waits for it to exit and runs `claude --bg --resume <sessionId> "text"` with no other option, which wakes the same session with its saved options, tool rules included (measured on CLI 2.1.322). If the CLI starts a copy instead, the copy is stopped and removed.
- The read-only level is enforced by rules, not only by the prompt: Edit/Write denied, and in Bash file writes, state-changing git, PRs and outbound data. The full-change level denies commit, push, PR and merge.
- A project package can replace a core level with the same id and `"substitui": true`, or add levels.
- Text parameters accept line breaks with `"linhas": true` (up to 6000 chars). POST body limit is 32 KB. `eventos?inteiro=1` returns full messages for the chat.
- `painel/web/dist` rebuilt from these sources.

## 2.3.1

- Panel: `painel/web/dist` (the prebuilt screens) is now in the repo. 2.3.0 said it was and it was not: an ignore rule left it out, so a fresh install only showed "run npm run build". CI now fails if the build is missing.

## 2.3.0

The panel: a local dashboard to follow and run the work.

- New `painel/` (Python stdlib server on 127.0.0.1 + prebuilt React screens) and `/tune-up:panel` to start it. Generic: it finds the project from the folder, works with no configuration, and holds no project names.
- Screens: phases and Parts read from the plans folder; Claude sessions with their sub-agents and workflows (model, effort, time, tools); live runs; follow-up lists.
- Buttons launch `claude --bg` from a closed list of actions; tool rules (deny / allow / hook) come from each action's JSON. `pular_permissoes` in `.tune-up/painel.json` (default off) adds `--dangerously-skip-permissions`; measured on CLI 2.1.322, deny rules and hook deny/ask still apply.
- A project adds screens (declarative blocks) and actions in `.tune-up/painel-projeto/`.
- UI and panel README are in Portuguese. macOS and Linux only for now. Panel tests run in CI on those two.

## 2.2.0

Fewer HIGH findings on the first pass, more work in parallel. From an audit of 10 measured Parts.

- `info`: new `pitfall_skills` (name, absolute SKILL.md path, `paths`) from installed modules. `part` always lists the matching ones under "Skills to read" and hands the same paths to the reviewers; no catalog needed.
- `part`: independent agents go in ONE message, in background (all mappers, all reviewers of an item, one checker per touched side). Read-only production aggregates (never personal values) go into the order as REAL DATA for items that read, filter or delete existing data. All CRITICAL/HIGH of all reviewers become ONE fix round that carries the original order and the cumulative diff; the re-review marks each previous finding closed or reopened. Progress is filled from the handoff json.
- Work order: new REAL DATA and UI STATES sections; TESTS asks for lint, types and related tests of the touched files plus the profile's sentinel tests.
- Executors: "Before handoff" self-check of failure paths, red -> green test per finding on a fix round, json block at the end. Reviewers: read the pitfalls after their own pass, json block before `Verdict:`.
- Guard (`agent`): a Workflow script is no longer denied for prose (3+ words) that mentions a forbidden model; short string literals and `model:` values still deny. `scriptPath` is now checked like `script` (unreadable or over 512 KB denies when the session model is forbidden). An Agent without `model` uses the `model:` of its definition file before being denied.
- Config: `plans_dir` accepts single spaces inside a segment.

## 2.1.2

Planning always lives in the local folder.

- `part`: goal, progress, later, research and handoff are read and written in the local `plans_dir` (main checkout), never only in the worktree. At close they are copied into the Part branch, so the PR carries them; the local copy stays the source. A sibling Part closed in the local progress counts as done even before its merge.
- `status`: reads the local progress, and cross-checks it with `git grep` over the phase branches. A closed line that exists only on a branch is reported as "local progress behind". A closed Part with no PR becomes "push/PR depends on the owner". An untracked phase folder in the checkout is not reported as odd.

## 2.1.1

Pitfalls grow from review findings.

- `part`: progress records per item the pitfall skills read and CRITICAL/HIGH per round (`HIGH 2->0`).
- `part` close: each CRITICAL/HIGH that can repeat becomes a drafted line for the matching pitfall skill (or a sharper existing line); the owner approves in one question and `/tune-up:learn` records it.

## 2.1.0

Windows support (native, with Git for Windows).

- Launcher `scripts/py`: hooks and skills run Python through it. It picks `python3`, `python` or `py -3` (3.9 or newer, the Microsoft Store alias is skipped), remembers the choice in the plugin data folder, sets `PYTHONUTF8=1`. Without Python the hooks fail open and the session start says so.
- `PowerShell` tool goes through the guard (hook matcher `Bash|PowerShell`): git/gh/psql checks, protected files and `bash_rules` apply; in talk and research modes only read-only PowerShell passes. Limits (variables, aliases, `Start-Process`, `-File`, .NET calls) are in the README.
- Git Bash paths (`/c/Users/...`, `/tmp`, `~`) are converted to Windows paths before comparison; the owner/permission checks that used `os.getuid` have a Windows equivalent (ACLs are not read; trusted files must be inside the user profile).
- `setup` checks Git, the launcher and Python first, and gives the `winget` commands to type when something is missing; `reference.md` has a Windows install for each optional tool.
- README: requirements and Windows notes. Docs for synced folders say `chmod u+w` is for macOS/Linux (Windows: `attrib -r`).
- Wrappers `cmd /c`, `powershell "..."`, `iex` and strings piped into `sh`/`bash` are opened one level; `.cmd`/`.bat`/`.ps1`/`.com` shims count as the command they wrap.
- Line limit also works on files with CRLF line endings.
- `terminal-title`: the tab title is now `${sequence}` only, so it no longer repeats the name (`Claude Code - claude`) before the conversation has a topic; `aplicar` updates the old value, `desfazer` removes either.
- README: workaround for the Windows `EPERM` rename error of `marketplace add` (install from a local clone).
- CI runs the test suite on Windows, macOS and Linux.

## 2.0.0

First public version.

- Skills: `setup`, `talk`, `new-project`, `design`, `plan`, `part`, `research`, `investigate`, `ship`, `learn`, `migration`, `status`, `handoff`, `git-clean`, `profile`, `evaluate`, `skills`, `terminal-title`.
- `setup`: guided first run (language, name, reply style, kinds of use) that writes `~/.config/tune-up/user.json`; optional tools (gh, claude-mem, fast-jev-compaction, Caveman, Ponytail, Graphify, ECC) installed only with consent, with the privacy of each one shown first.
- `talk`: interview, brainstorm and persona debate that produce project documents without code; `new-project` and `design` turn the vision into a scaffold and a design-token prototype.
- `terminal-title`: makes the terminal tab of VS Code-family editors show the conversation topic; `undo` reverts it.
- 12 agents with a fixed model and effort per role (`mapper`, `checker`, `persona`, `skill-finder`, `researcher`, `writer`, `executor-sonnet`, `executor-opus`, `plan-reviewer`, `reviewer-failures`, `reviewer-database`, `reviewer-security`).
- Hooks: git guards, production/Supabase guard, research mode, talk mode, forbidden subagent models, self-protection of settings, plugin and profile files, secret and new-rule notices, SessionStart line.
- Line limit: code files may not pass 450 lines (`line_limit`); `tune-up: allow-long <reason>` in the first 5 lines allows an exception.
- Language: messages and names in English and Brazilian Portuguese, set per user (`user.json`) or per project; `names_override` for document names.
- Output style `caveman-summary` (optional, not forced): final answer as a short plain-language block.
- Evals: `learn-fires`, `investigate-fires`, `skills-finder-fires`, `research-no-edit`, `talk-no-code`, `status-summary`.
