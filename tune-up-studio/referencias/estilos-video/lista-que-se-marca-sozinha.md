# Video style: lista que se marca sozinha

Read by the video skill only when this is the piece's style (`"estilo": "lista-que-se-marca-sozinha"` in `peca.json`); no other style file is read.
Distilled from the checklist endings of the collection credited in NOTICE (each promise gets a ring and a tick that draw themselves, one per beat). Rebuilt for the studio engine (one hero, no library, no network, no 3D, no sound), rendered and looked at frame by frame in round 7. The pt-BR lines are molds of an invented driving school: never reuse one (QA `molde`).

## Use it when
The briefing lists what is included (items of a package, what the service covers, requirements already met). The ticks are the proof: 2 or 3 things the reader gets, not adjectives.

## Slots of scene 2 (`lista`, 8 words; 9 at 15 s)
| slot | limit | what goes there |
|---|---|---|
| `lista.titulo` | 30 characters | what the list is, in 1 to 3 words ("No pacote") |
| `lista.itens` | 2 or 3 items, 26 characters each | one thing per item, a noun with its number when the briefing has it ("20 aulas práticas", "Simulado incluso"); 2 words each |

## Storyboard, 10 s
Cuts at 1.625, 4.375 and 6.875 s. Times inside scene 2 count from its cut.
| time | scene | what the eye sees |
|---|---|---|
| 0-1.625 | 1 `gancho` | the hook at the top, a marker drawing under its key words at 0.4 s; the hero wide, pushed in |
| 1.625-4.375 | 2 `lista` | the title and every item whole at the cut, each beside an accent disc; the ticks draw themselves at 0.5, 1.1 and 1.7 s while their item waves, then the whole list pulses in a wave; the hero on its stage below |
| 4.375-6.875 | 3 `oferta` | the offer's name on a tag, the price or offer word giant on the accent band, the proof; the hero changes (`h_antes` fades, `h_depois` pops, `h_traco` draws) |
| 6.875-10 | 4 `final` | the call big, the condition on its tag, the contact beside the channel icon; a cursor travels to the contact and presses it at 1.3 s; logo and brand name; the hero 45% wide or more |

## 15 s
Cuts at 1.875, 4.875, 7.875 and 10.875 s. Scene 2 is the same, 3 s long. Then scene 3 is `rampa` (the hero in close-up over one more fact: `rampa.titulo` 36 characters + `rampa.apoio` 40, 9 words), then `oferta` (9 words) and `final` (12 words).

## Where the method enters
The hook is scene 1. The list is the proof, so `oferta.prova` brings a fact the list did not show. The offer word (`grátis`, a discount) may be one item, but the price is only `oferta.valor`. The contact on the end card.

## Never
- Items that are adjectives ("qualidade", "confiança") or that repeat each other.
- A fourth item, or an item of 4 words: it does not fit the 2.75 s.
- A tick on something the briefing does not include.
