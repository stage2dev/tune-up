# Video style: contador e gráfico

Read by the video skill only when this is the piece's style (`"estilo": "contador-e-grafico"` in `peca.json`); no other style file is read.
Distilled from the counter and chart beats of the collection credited in NOTICE (a number that runs up to a real figure and lands sharp, a line or ring that draws with it). Rebuilt for the studio engine (one hero, no library, no network, no 3D, no sound), rendered and looked at frame by frame in round 7. The pt-BR lines are molds of an invented optician: never reuse one (QA `molde`).

## Use it when
The strongest fact of the briefing is a count: years in business, customers served, items checked, units in the package. The number is the proof and the eye follows it running.

## Slots of scene 2 (`contador`, 8 words; 9 at 15 s)
| slot | limit | what goes there |
|---|---|---|
| `contador.numero` | digits only, up to 7 characters | the count as the briefing writes it ("12", "1.240"); never a price, a percentage or a grade: the kit refuses them |
| `contador.rotulo` | 28 characters | what is counted, 2 to 4 words ("anos no bairro") |
| `contador.apoio` | 32 characters | optional: one more fact about it ("armações de 40 marcas") |

## Storyboard, 10 s
Cuts at 1.625, 4.375 and 6.875 s. Times inside scene 2 count from its cut.
| time | scene | what the eye sees |
|---|---|---|
| 0-1.625 | 1 `gancho` | the hook at the top, a marker drawing under its key words at 0.4 s; the hero wide, pushed in |
| 1.625-4.375 | 2 `contador` | a ring in the middle of the frame and the label under it, whole at the cut; from 0.15 to 1.1 s the number runs from 0 to the count while the accent ring closes around it; at 1.15 s the number pulses and a tick badge pops on the ring; the support line rises at 1.3 s; a second pulse at 1.95 s; the hero small below |
| 4.375-6.875 | 3 `oferta` | the offer's name on a tag, the price or offer word giant on the accent band, the proof; the hero changes (`h_antes` fades, `h_depois` pops, `h_traco` draws) |
| 6.875-10 | 4 `final` | the call big, the condition on its tag, the contact beside the channel icon; a cursor travels to the contact and presses it at 1.3 s; logo and brand name; the hero 45% wide or more |

## 15 s
Cuts at 1.875, 4.875, 7.875 and 10.875 s. Scene 2 is the same, 3 s long. Then scene 3 is `rampa` (the hero in close-up over one more fact: `rampa.titulo` 36 characters + `rampa.apoio` 40, 9 words), then `oferta` (9 words) and `final` (12 words).

## Where the method enters
A hook that is the number itself goes to scene 1 with `"numero": true` and this style is then the wrong one (the number would appear twice): pick it when the hook is the reader's situation and the count answers it. The price never counts up: it is stamped in scene 3. The contact on the end card.

## Never
- A number that is not in the briefing, or rounded up.
- A chart of results (sales rising, weight falling): that is a promise of results. The ring only closes on the count.
- A count under 5: the run is over before the eye sees it; use `lista-que-se-marca-sozinha`.
