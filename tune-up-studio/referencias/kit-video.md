# Kit: the reel composition

Read by the video skill in the Script step: it writes `peca.json`, draws the hero and runs `montar.py`. The composition's HTML, CSS and motion script are never written by hand.
The reel was built, rendered and looked at frame by frame for a garage, a pet shop and a bakery (round 6), then for a software product and a meal-kit kitchen in two different styles (round 7: `check --strict` clean, the video QA green, two renders byte for byte the same) before it became the kit. The pt-BR lines here are molds from invented businesses: the QA fails a piece that reuses one (`molde`).

## What the kit guarantees
- **Every scene opens whole and then builds.** The title, the hero and the first beat are in place at the cut; a new beat lands about every 0.6 s (a marker draws, a bubble pops, a tick draws, a cursor clicks); every beat arrives whole: no text through a mask or from outside the frame, no price counted up.
- **No sampled frame shows a transition.** Cuts sit off the 0.25 s grid and each wipe is seen for 0.14 s; a sheet with one frame every 0.5 s shows only scenes.
- **One hero for the whole video**, on a light stage, reframed at every cut, pushed in or travelling, its problem parts hovering, its loops running, and transformed in the offer scene.
- **The end card says what to do**: a cursor travels to the contact and presses it.
- **Type that fills the frame**: every title sized from the real font to the 860-880 px column; the price or offer word 220 px or more on the accent band; an end card with the call, the contact in its pulsing ring, the logo with the brand name and the hero at 45-83% of the width.
- The motion is the studio engine (JavaScript, no library, no network), pasted whole by the script.

## Styles (`"estilo"` in `peca.json`: the file name)
The style decides scene 2, the device that builds itself. Take the `Estilo` of the prompt; when it is `a IA escolhe`, pick by this table from the briefing (never the style of the piece before it when you know it). Then Read `${CLAUDE_PLUGIN_ROOT}/referencias/estilos-video/<file>.md`, that one file only: it has the slots of scene 2, the storyboard beat by beat and what never to do.

| `Estilo` of the prompt | file (`estilo`) | scene 2 | pick it when the briefing |
|---|---|---|---|
| produto em destaque | `produto-em-destaque` | `rampa` | sells an object you can show; the default |
| tipografia cinética | `tipografia-cinetica` | `tipografia` | is a rhythm of 2 or 3 short phrases; nothing to show |
| conversa de WhatsApp | `conversa-de-whatsapp` | `conversa` | wants messages or orders by chat; answers a common question |
| lista que se marca sozinha | `lista-que-se-marca-sozinha` | `lista` | lists what is included |
| contador e gráfico | `contador-e-grafico` | `contador` | has a count as its strongest fact (years, customers, items) |
| antes e depois | `antes-e-depois` | `antes_depois` | changes a state and states both sides; not for a patient or a body |
| tela com cursor clicando | `tela-com-cursor-clicando` | `tela` | sells a screen or asks for one click (book, buy, try) |
| cartaz que se monta | `cartaz-que-se-monta` | `cartaz` | announces a date, an opening, a sale |
| passo a passo | `passo-a-passo` | `passos` | must explain how to buy or what happens next |
| mito ou verdade | `mito-ou-verdade` | `mito` | answers a doubt people repeat with a fact |

## Scenes
| scene | field | what the eye sees | slots (words: all of the scene together) |
|---|---|---|---|
| 1 `gancho` | theme | the hook at the top, readable in frame 0; a marker draws under its key words; the hero wide, pushed in; stripes in the corner | `gancho.titulo` + `gancho.destaque`: 40 characters and **6 words** together |
| 2 the style's | dark | see the style file | the style file; **8 words** (7 for `rampa`; 9 at 15 s) |
| 3 at 15 s only | light or theme | `rampa`: the hero in close-up, the title on a band, an accent line drawing, the support line (`rampa.titulo` 36 + `rampa.apoio` 40). For `produto-em-destaque` it is `lista` and for `lista-que-se-marca-sozinha` it is `rampa` | **9 words** |
| `oferta` | theme | the offer's name on a tag; the value giant on the accent band; the proof; the hero changes: `h_antes` fades, `h_depois` pops, `h_traco` draws | `oferta.nome` (28) + `oferta.valor` (16) + `oferta.prova` (36): **7 words** (9 at 15 s) |
| `final` | theme | the call big; the condition on an accent tag; the contact beside the channel icon in a pulsing ring, pressed by a cursor at 1.3 s; logo and brand name; the hero below, still moving | `final.titulo` (40) + `final.condicao` (30) + `final.contato` (34): **9 words** (12 at 15 s) |

Jobs of the scenes: `gancho` = the chosen hook as title + its key words as `destaque` (the second color); with `"numero": true` the title is a giant number and `destaque` its line. Scene 2 continues the hook with the mechanism or the proof, never the business description. `oferta` = the offer as the briefing names it + its price or offer word + one fact not shown yet. `final.titulo` = verb + a gain not said yet; `final.condicao` = the briefing's condition and deadline; `final.contato` = the channel exactly as the briefing writes it; `final.canal` = `whatsapp`, `endereco`, `instagram`, `site` or `telefone`. A fact appears once in the whole reel. "R$" and a phone's area code count as words.

## Other slots of `peca.json`
| slot | values | effect |
|---|---|---|
| `heroi_topo` | 0-500 | the y of the hero's highest point (heroi.md): the kit sizes the hero by it |
| `heroi_topo_antes` | 0-500 | only when the problem state is much shorter than the after (loaves, steam or bars pop in above it): the y of its highest point; the hero then fills the hook |
| `heroi_anda` | `direita`, `esquerda` | the hero travels that way (a vehicle, an animal walking) and its wheels turn that way; left out, it stands and bobs |
| `chao` | `estrada` | dashes that scroll on the ground; left out, a plain ground |
| `heroi` | `"foto"` | the main photo printed by `fotos.py` takes the hero's place, framed, with a slow push |
| `variante` | object | `tema`: `noite` (strong color, then light end card), `tinta` (the darkest color first), `dia` (light first, strong end card); `lado`: `direita`, `esquerda` (the hero's side); `palco`: `disco`, `corte` (the stage's shape); `textura`: `pontos`, `listras`, `nenhuma`; `transicao`: `faixa`, `cortina`, `sobe` (the first of the three). Left out, the kit picks from the brand name, the same every time |

Pick the theme by the hook: a question about a problem opens dark (`noite`, `tinta`); a novelty or an invitation opens light (`dia`). Never the variant of the piece before it when you know it.

Mold (a barber shop, invented): `{"estilo": "produto-em-destaque", "gancho": {"titulo": "Barba por fazer", "destaque": "na sexta?"}, "rampa": {"titulo": "Corte e barba juntos", "apoio": "em 50 minutos"}, "oferta": {"nome": "Combo da sexta", "valor": "R$ 70", "prova": "com hora marcada"}, "final": {"titulo": "Garanta seu horário", "condicao": "só às sextas", "contato": "@barbearia.exemplo", "canal": "instagram"}, "heroi_topo": 120}`

## Run it
`python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/montar.py --tipo video --peca peca.json --heroi heroi.svg --out fonte --duracao D`. It prints one line per scene with the sizes it chose and the variant, or, with exit 1, the one thing to fix (a slot too long, too many words in a scene, a hero with no change).

| D | style | `--tempos` (reserve) | slides `--at` (85% of each scene) | look `--at` (0, then 25% and 75% of each scene) |
|---|---|---|---|---|
| 10 | `produto-em-destaque` | `1.875,2.5,2.5,3.125` | `1.59,4,6.5,9.53` | `0,0.47,1.41,2.5,3.75,5,6.25,7.66,9.22` |
| 10 | any other | `1.625,2.75,2.5,3.125` | `1.38,3.96,6.5,9.53` | `0,0.41,1.22,2.31,3.69,5,6.25,7.66,9.22` |
| 15 | all | `1.875,3,3,3,4.125` | `1.59,4.43,7.43,10.43,14.38` | `0,0.47,1.41,2.63,4.13,5.63,7.13,8.63,10.13,11.91,13.97` |

With the reserve engine the slides are these same scenes near their end, every beat landed: the hero's change is on the offer slide, the motion between is not.

## When the look or the QA asks for a change
| what you see | change |
|---|---|
| a title under 120 px or in 4 lines | shorter lines: 12-16 characters per line fill the width; move the break between `titulo` and `destaque` |
| the value small on its band | `oferta.valor` is the price or the offer word alone; the rest goes to `nome` and `prova` |
| the hero small or far from the text (`ocupacao` in scene 1) | `heroi_topo` at its real top; `heroi_topo_antes` when the after state is taller; a hero that should travel gets `heroi_anda` |
| the hero reads as an icon, or its change is weak | redraw by heroi.md: the briefing's detail bigger; 3 or more `h_depois` parts, each 100 px or more in the box |
| two scenes look alike, or scene 2 is thin | another `variante.palco` or `tema`; fill every slot of the style (3 lines, 2 answers, 3 steps) |
| `palavras_cena` or a montar refusal | cut the support line of that scene first; a fact left out goes to the caption |
| `cta_final` red (deadline) | the briefing's deadline in `final.condicao`, as written |
| `oferta_destaque` red | the offer word in the scene 2 title, `oferta.nome`, `oferta.valor` or `final.titulo` |
| `estilo` red | `estilo:` in `estrategia.md` and `"estilo"` in `peca.json` name the same style file |
