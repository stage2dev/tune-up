# Kit: post compositions

Read by the post skill in the Copy step: it picks a composition, writes `peca.json` and runs `montar.py`. A frame's HTML is never written by hand.
The three compositions were built, rendered and looked at for a garage, a pet shop and a bakery (round 6) before they became the kit. The pt-BR lines here are molds from invented businesses: the QA fails a piece that reuses one (`molde`).

## What the kit does, so you do not
Brand colors and their text pairs (measured, 4.5:1 or 3:1 for big type), the two brand fonts, the logo copied and placed with the brand name, every size and position: the headline sized from the real font to fill the 920 px column, the offer stack (name + giant value + proof, a price set as a small "R$" and a giant number), a full call band with the channel icon, shapes that run to the real edge, the hero big on a light stage. You write the words and draw the hero (heroi.md).

## Compositions (`"composicao"`)
| name | what the eye sees | pick it when | `layout:` in copy.md |
|---|---|---|---|
| `oferta` | headline on the field; a slanted light stage with the hero on one side; the offer on a card that runs off the other side; ground; call band | the briefing has a price or an offer and the hero is wide (a vehicle, a table, a shelf) | `l-oferta` |
| `palco` | centered headline; the hero big inside a light arch; the offer on a tilted price tag; call band | the hero is tall or has a face (an animal, a product standing up, a basket); or there is no price: then `apoio` replaces the tag | `l-titulo` |
| `numero` | the headline is a giant number of the briefing ("40 min", "6h", "1.240"); its meaning in `apoio`; the hero and the offer card under it | the hook is the proof (archetypes big number, objection) | `l-numero` |

Never the composition of the piece before it when you know it; a carousel never repeats a `layout:` in two frames in a row.

## `peca.json` (one per frame)
| slot | limit | what goes there |
|---|---|---|
| `composicao` | one of the 3 | see the table |
| `titulo` | 40 characters | the chosen hook, one sentence (two short ones are fine); for `numero`, the number and its unit only |
| `realce` | words of `titulo` | the words that take the second color: the situation or the question's end, never the whole title |
| `apoio` | 60 characters | `numero`: what the number means. A frame with no offer: the support line. Left out when the frame has an offer |
| `oferta.nome` | 28 characters | the offer as the briefing names it (the service, the package), never "promoção" |
| `oferta.valor` | 16 characters | the price as the briefing writes it ("R$ 89") or the offer word ("14 dias grátis", "20% off"); left out when the briefing has neither |
| `oferta.prova` | 40 characters | one fact that makes the value believable, not said in the title (how many, how long, for whom) |
| `cta.chamada` | 44 characters | verb + where or a gain not said yet; when the briefing's offer word (grátis, desconto) is not in the value, it goes here; over about 26 characters it takes two lines |
| `cta.condicao` | 60 characters | the contact as the briefing writes it, then the condition and the deadline |
| `cta.canal` | `whatsapp`, `endereco`, `instagram`, `site`, `telefone` | the icon of the channel named in `condicao` |
| `heroi` | `"foto"` | only when `fotos.py` printed `foto1`: the photo takes the hero's place |
| `heroi_topo` | 0-500 | the y of the hero's highest point (heroi.md) |
| `chao` | `estrada` | dashes on the ground, for a vehicle; left out otherwise |
| `estado` | `antes` | shows the hero's problem state (a carousel cover that only raises the question); default is the after |
| `variante` | object | `campo` (`primary`, `text`, `bg`: the field color), `lado` (`direita`, `esquerda`: the hero's side), `textura` (`pontos`, `listras`, `nenhuma`). Left out, the kit picks from the brand name, the same every time |

A single post carries everything: hook, offer stack and call, 30 words at most on the art (the brand name aside). Never the same noun in the title, the proof and the call; never a fact that is not in the briefing.

Mold (a language school, invented): `{"composicao": "palco", "titulo": "Trava no telefone em inglês?", "realce": "em inglês?", "oferta": {"nome": "Aula de conversa", "valor": "R$ 120", "prova": "4 alunos por turma"}, "cta": {"chamada": "Marque a aula experimental", "condicao": "pelo WhatsApp, até sexta", "canal": "whatsapp"}, "heroi_topo": 140}`

## Carousel (`--quadro`)
| `--quadro` | frame | slots it uses |
|---|---|---|
| `capa` | frame 1: the hook, the hero (often `"estado": "antes"`), the swipe cue | `titulo`, `realce`, `apoio`, `arraste` (a cue with the word "arraste", 40 characters; default "arraste para o lado") |
| `ponto` | a middle frame: one point of the arc | `titulo`, `apoio`, or `oferta` for the payoff frame |
| `fecho` | the last frame: offer and call | `titulo`, `oferta`, `cta` |
| `unico` (default) | the single post | all |

Change `composicao` and `variante.campo` from one frame to the next (cover on the light field, payoff on the dark one), keep `lado`; one `heroi.svg` serves every frame.

## Run it
`python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/montar.py --tipo post --peca q<N>/peca.json --heroi heroi.svg --out q<N>/fonte --formato=<R>` (add `--quadro capa|ponto|fecho` in a carousel). It prints the sizes it chose (`titulo: 133 px em 2 linha(s)`, `heroi: 61% da largura`, `oferta: 226 px`) or, with exit 1, the one thing to fix.

## When the look or the QA asks for a change
| what you see | change |
|---|---|
| headline under 110 px or in 3 ragged lines | shorten `titulo` (28 characters fill two lines well); move words to `oferta.prova` |
| the value under 160 px | a shorter `oferta.valor` (the price alone); a shorter `oferta.nome` |
| the hero small, far from the title | set `heroi_topo` to its real top; a wide hero goes to `oferta`, a tall one to `palco` |
| the hero reads as an icon | redraw it by heroi.md: the briefing's detail bigger, a second tone, the after state |
| the hero small beside the card (`oferta` keeps the card off the drawing) | a tall or square hero goes to `palco`; `oferta` is for a wide one |
| `palavras` red | cut `oferta.prova` first, then `cta.condicao` down to the contact and the deadline |
| `oferta_destaque` red | the briefing's offer word goes in `titulo`, `oferta.valor` or `cta.chamada` |
| a color pair that reads badly on this brand | another `variante.campo` |
