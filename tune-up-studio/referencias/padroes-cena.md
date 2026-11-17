# Scene patterns (layout, type and transitions)

Read by whoever maintains the reel kit (`scripts/kit_video.py`) or hand-builds a reel: since round 6 the video skill builds from the kit and no longer reads this file.
This file holds the still layout and the CSS transitions; all motion inside a scene comes from motion-js.md. Coordinates are one example, never a template: per piece pick an alignment (left, centered or bottom-right), a scale and positions of your own.

## Rules every scene follows
- A clip has no child elements in the HTML (an `<svg>` device keeps its shapes; the engine may split a text into words at load). Colors only `var(--bg|--surface|--primary|--text|--accent)`; no `rgba`, no `color-mix`; a shape never rests below opacity 1; no `filter` (QA `script_seguro`).
- `font-size` (px) and position (`left`/`top`, never `transform`) live in a rule whose selector is exactly `#<id>` (a comma list of `#ids` is fine). The `l-*` class is a QA marker, never styled. Stacking by `z-index`: blocks 1, the hero 2, text 3, transitions 9.
- A text that moves by `clip-path` keeps `line-height: 1.05; padding: .12em 0 .2em` so accents and the legs of g, j, p, q, y are never cut (QA `legibilidade`).
- Nothing rests outside the canvas (a box wider than 1080 or rotated past the edge fails the check); entries may start outside.
- Forbidden styles: crossfade between scenes, particles, glow, lens flare, camera shake, a "template" gradient, a transition that covers the whole frame for more than 0.15 s, the stock icons of a sector (recursos-visuais.md). One dominant movement per scene.
- Base, once per file (safe box for text: x 90-990, y 269-1536; the last 384 px may hold shapes, never text):

```css
#root { position: relative; width: 1080px; height: 1920px; overflow: hidden; background: var(--bg); color: var(--text); font-size: 44px; text-wrap: balance; }
.clip { position: absolute; margin: 0; z-index: 3; }
```

## Type scale (the only one for the reel; QA floors: `_titulo`/`_destaque` 96 px, other text 44 px)
| role | px | line-height | letter-spacing |
|---|---|---|---|
| `s1_titulo`, end-card `_titulo` (QA `titulo_largura`: 120 px or more, 70% of the width) | 140-200 | 1-1.05 | -0.03em |
| other `_titulo`, `_destaque` | 104-160 | 1.05 | -0.02em |
| the offer word as `_destaque` on its band (QA `oferta_destaque`) | 150-200 | 1.05 | -0.03em |
| number (`l-numero`) | 220-600 | .9 | -0.03em |
| `l-cheia` headline (fills 40% or more of the safe box) | 150-200 | 1.02 | -0.03em |
| `_apoio`, `_item*`, `_selo`, `_marca` | 52-76 | 1.2 | 0 |
| `_contato` (with the channel icon) | 64-80, heading font | 1.2 | 0 |

At most 3 sizes per scene: the headline, one support size, the brand line.

## Arrangements (`l-*` on `s<N>_titulo`)
| `l-*` | measures (1080x1920) | good for |
|---|---|---|
| `l-topo` | headline top, y 290-800, width 900; the device in y 850-1920 | hook, end card |
| `l-base` | headline in the lower third, y 1000-1500, on a band or panel; device above | payoff |
| `l-cheia` | `s<N>_bloco` 1080x1920 in `--primary`; text in its `--pares` pair; the hero over it | turn, on-ramp |
| `l-numero` | number 220-600 px, y 240-1000; its line (52-76 px) under it | proof |
| `l-faixa` | `s<N>_bloco` turned band (`clip-path: polygon(...)`) with the headline on it | quote, objection |
| `l-foto` | `s<N>_foto` 1080x1100 from the top, `object-fit: cover`; `s<N>_bloco` solid below with the text | product, place |
| `l-lista` | headline at y 300; `item1..3` at y 700, 860, 1020 with ticks (recursos-visuais.md) | steps, signs |

The class is a marker: what the eye sees must change at each cut too. Move the title (top, bottom, beside the number), change the background (bg, a full `--primary` block, an accent band) and reframe the hero (wide, close-up, beside the text; motion-js.md). Two scenes with the title top-left over the hero in the middle read as a template.

## Shapes that carry a scene
- Panel or band: `s<N>_bloco` behind the text of `l-base`/`l-faixa`, solid brand color, cut by `clip-path: polygon(0 10%, 100% 0, 100% 100%, 0 100%)` for a slant; it enters with `entra(..., "painel")`.
- Offer band: `s<N>_barra` (accent, at least 900x180) under the offer word; it opens with `mascara(..., "esquerda")` and the word lands on it with `entra(..., "carimbo")`.
- Sticker: `s<N>_bloco2` (a circle) and `s<N>_selo` (its text, in the square inscribed in the circle, 70% of its diameter); at most 2 words of up to 9 characters; it lands at 50-60% of the scene with `entra(..., "gira")`. A sticker may be round; a CTA never is.
- Ring behind the channel icon: `s<N>_pulso`, `border-radius: 50%`, 170-210 px, in `--bg` on the primary band (in `--primary` on a light ground); `pulso` keeps the end card alive.

## Transitions (the only CSS animation left; hyperframes engine only)
`tr<N>` lasts 0.44 s centered on its cut (`data-start` = cut - 0.22) but its wipe is seen only from 34% to 66% of it (0.14 s), and the cuts sit off the 0.25 s grid (1.875 s, 4.375 s...): a contact sheet with one frame every 0.5 s never catches it (QA `folha_limpa`). Placed last in the HTML, `z-index: 9`, in the **background color of the next scene**, never the same kind twice in a row. At the cut (46-54%) it covers at least 70% of the frame, and it ends gone. A full-frame cover lasts at most 0.15 s (QA `transicoes`).
```css
#tr1, #tr2, #tr3 { left: 0; top: 0; width: 1080px; height: 1920px; z-index: 9; }
#tr1 { background: var(--primary); clip-path: polygon(0 10%, 100% 0, 100% 90%, 0 100%); animation: tr_faixa .44s linear 0s 1 both; }
#tr2 { background: var(--bg); animation: tr_cortina .44s linear 0s 1 both; }
#tr3 { background: var(--surface); animation: tr_sobe .44s linear 0s 1 both; }
@keyframes tr_faixa { 0%, 34% { transform: translateY(1920px); } 46%, 54% { transform: translateY(0); } 66%, 100% { transform: translateY(-1920px); } }
@keyframes tr_cortina { 0%, 34% { clip-path: inset(0 100% 0 0); } 46%, 54% { clip-path: inset(0 0 0 0); } 66%, 100% { clip-path: inset(0 0 0 100%); } }
@keyframes tr_sobe { 0%, 34% { clip-path: inset(100% 0 0 0); } 46%, 54% { clip-path: inset(0 0 0 0); } 66%, 100% { clip-path: inset(0 0 100% 0); } }
```

## End card (both engines)
Top to bottom: `s<N>_titulo` (verb + a gain not said yet, 160-200 px, 70% of the width or more); the logo on its `--bg` plate with `s<N>_marca` (56-64 px) beside it; the hero, 45% of the width or more, still moving; `s<N>_apoio` (the briefing's condition and deadline, on an accent `s<N>_bloco2` band when it is the accent of the scene); `s<N>_icone` (the channel icon, 120-160 px) over `s<N>_pulso` beside `s<N>_contato`, all on a dark ground (a `s<N>_barra` 200-240 px tall from the left edge, or a slanted `s<N>_bloco` under the lower half): the contact in its light pair, `white-space: nowrap`, sized to fit one line (a heavy heading font takes about 0.62 em per character). The contact lands by cut + 0.8 s and stays 2 s or more; nothing exits; the ring pulses to the end. No round corners or background on the text clips (a device behind them is its own clip).

## Reserve engine
The slides are snapshots of this same composition in the middle of each scene (`reserva_slides.py --tempos <lengths>`, the pattern's list; the engine seeks there too): entries done by 40% so each scene works as a still photo; motion and transitions never reach it.
