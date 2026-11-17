# Post archetypes and arrangements

Read by the post skill in Strategy and Copy (archetype, carousel arc) and in the HTML step (arrangements); anuncio reads only *Arrangements* for the Meta image.
pt-BR lines are molds from invented businesses: swap every fact for one from the briefing.

## Archetypes
An archetype that needs proof the briefing does not have is **not** used. Pick another one.

| archetype | structure | needs (proof) | default `l-*` | words on art |
|---|---|---|---|---|
| big number | one huge number + the line saying what it means + small source | a real number | `l-numero` | 6-12 |
| before/after | two halves, short labels, the difference as a number | 2 real photos or 2 real facts | `l-antes-depois` | 8-14 |
| customer quote | the customer's sentence in big quotes + name/neighborhood small | a quote in the briefing | `l-citacao` | 10-20 |
| reader's situation | headline = the reader's situation or its pain as a question; the offer named as the briefing names it, with its price (offer stack) | an audience or situation in the briefing | `l-titulo` | 6-14 |
| named pain | headline = the pain in the customer's words; support = how it ends | the pain stated by customers | `l-titulo` | 8-14 |
| how it works | 3 numbered steps, verb + result each | a real process | `l-lista` | 12-20 |
| list / educational | cover promises N, one idea per frame, exactly N delivered | owner's know-how | `l-lista` | cover ≤ 10 |
| myth vs truth | "dizem" vs "na real", the fact that settles it | verifiable knowledge | `l-antes-depois` | 10-18 |
| offer | offer name, what it includes, real condition, real deadline | a defined offer | `l-oferta` | 10-20 |
| objection | headline = the customer's doubt; the answer as a giant number or a sticker | the doubt and its answer in the briefing | `l-numero` | 6-14 |
| novelty / collection | the new product or thing big (photo or silhouette) + "chegou" or what changed; condition and deadline in the CTA | something new in the briefing | `l-foto` / `l-cheia` | 8-16 |
| behind the scenes | real photo of the process + one curious fact | a process photo | `l-foto` | 6-12 |
| who it is for | "Para você se..." 2-3 items | a clear audience | `l-lista` | 10-18 |
| old way vs ours | the status quo vs the service, two columns | facts on both sides | `l-antes-depois` | 10-18 |
| guarantee as headline | the guarantee big, at most 2 conditions | a real policy | `l-cheia` | 8-16 |
| owner's opinion | one opinion someone could disagree with | a real stance of the owner | `l-titulo` | 8-16 |
| owner's story | why it exists + owner photo + the customer's gain | a real story | `l-foto` | 10-20 |

A short briefing (3 facts or fewer) uses `reader's situation`: one frame, or a carousel of 2-3.

Molds:
- reader's situation (escola de idiomas): "Trava no telefone em inglês?" / sticker "aula de conversa".
- objection (loja de roupas): "Tem o meu número?" / giant "36-54" / "8 modelos novos". novelty (oficina): the car part drawn big / "Chegou: alinhamento a laser".
- big number (pet shop): "1.240 banhos este ano" / "sem pressa na secagem".
- customer quote (escola de idiomas): "Fiz a entrevista em inglês sem travar." / Ana, Centro.
- myth vs truth (contador): "Dizem: MEI não declara nada. Na real: tem a declaração anual até [data]."
- owner's opinion (barbearia): "Degradê a cada 15 dias é exagero. Aqui indicamos 21."

## Arrangements
Measures for 1080x1350 (4:5). For 1080x1080 multiply every height by 0.8. Margin **80 px** on all sides (the only margin: `#root` padding 80); the logo sits 96-120 px wide in the **same corner in every frame** (top-left at 80/80 unless the arrangement says otherwise), never in front of the headline, on a round `--bg` plate when the color behind it is its own. Every arrangement keeps room for the frame's device (recursos-visuais.md).

- **`l-titulo`**: the headline fills 40-60% of the area (box 920 px wide, from y 200 to 900), left-aligned, `text-wrap: balance`; support line under it; the device (figure, sticker, shape) in the biggest free area, or the headline itself as one giant word. With a sticker beside the headline, the h1 box is 920 px minus the sticker width, or the sticker goes under the headline: never a short word alone on a middle line.
- **`l-numero`**: the number is the `<h1>` (200-360 px, at the left margin); the number plus its meaning line (36-48 px, right under it) fill 40-60% of the frame height (540-810 px); the source of the proof small (28-32 px) near the bottom.
- **`l-foto`**: the photo in a fixed box covering ≥ 40% of the area (for example 1080x760 from the top, `object-fit: cover`); a solid brand-color band (≥ 420 px tall) holds the headline and support. Text never sits on the photo itself.
- **`l-lista`**: headline on top (y 160-400), then 3 items, each ≤ 8 words, one per row of ~220 px; ticks or numbers in `accent`, the item text in the body pair.
- **`l-antes-depois`**: two halves split at y 675 (or at x 540), each with a solid brand color, a short label ("Antes", "Depois" / "Dizem", "Na real") at 28-32 px and its content; the difference written as a number in the lower half.
- **`l-citacao`**: an opening quote mark 240-320 px in `accent` (an element holding only the mark, or `h1::before`: punctuation only, so it stays out of the h1's 1.8x rule), the customer's sentence as the `<h1>` (it may use the lower end of the scale, 96-110 px), name and neighborhood at 28-32 px below.
- **`l-oferta`**: offer name as the `<h1>`; a block listing what it includes (2-3 lines); the real condition and real deadline on a solid band near the bottom.
- **`l-cheia`**: the whole background in `primary`, text in the pair that `--pares` approved for it, plus one device (shape, sticker or icon) besides the logo.

## Type scale and color
| level | post (px) | line-height | letter-spacing |
|---|---|---|---|
| headline | 96-160 (number: 200-360) | 0.95-1.08 | -0.01 to -0.03em |
| support | 36-48 | 1.2-1.35 | 0 |
| label, source, seal | 28-32 | 1.2 | 0 to 0.04em |
| CTA (last frame) | 48-64, bold, `Brand Heading` | 1.1-1.2 | 0 |

- At most 3 levels per frame; the headline is at least 1.8x every other text. Uneven weight is good: equal sizes look generated.
- The offer, when the briefing has one, is the second level: its name (the service as the briefing writes it) over its price or key word as `#oferta`, 96-140 px in `Brand Heading` on an accent band that bleeds off the left edge (the text keeps the 80 px margin; *Offer stack* of recursos-visuais.md).
- CTA band (recipe of recursos-visuais.md): the channel icon + line 1 verb and where, line 2 the condition and deadline; no colon joining action and condition. Line 2 has the same size in `Brand Body` bold and a lighter pair (`--surface` on `--primary` when `--pares` prints it): weight and color tell it apart, never a fourth size. In a single post the support line and the CTA never repeat a noun or the offer: the CTA brings a gain not said yet.
- `accent` on **one** element per frame (the offer band, the numbers of a list, or the quote mark); the CTA's condition on its dark band may share it.
- Colors only from the brand kit; text pairs only from the `--pares` table.

## Carousel arcs
The cover only raises the question and ends with a swipe cue containing the word `arraste` ("arraste →", "Arraste para ver os 3"). Frame 2 continues the cover (on-ramp); the second-to-last pays the promise (payoff); the last asks for one action. Inner frames keep the same grid and logo corner but change the dominant element: the `l-*` and the device never repeat the previous frame.

| arc | 3 frames | 5 frames |
|---|---|---|
| problem -> proof -> how it works -> CTA | pain / proof / CTA | pain / why it happens / proof / how it works / CTA |
| named list | promise N / the N items / CTA | promise N / item 1 / item 2 / item 3 / CTA |
| step by step | result / map "3 passos" + steps / CTA | result / map "3 passos" / step 1 / steps 2-3 / CTA |
| myth vs truth | myth / truth with the fact / CTA | myth / why people believe it / the truth / what to do / CTA |

Example `l-*` sequence for 5 frames: `l-titulo`, `l-foto`, `l-numero`, `l-lista`, `l-cheia`.

Cover molds:
- oficina: "3 sinais de que o freio pede revisão" / "arraste →".
- clínica odontológica: "Sangra quando escova? Veja o que isso pode ser" / "arraste →".

## Photo use
- When the brand has photos, the main photo goes in frame 1 or 2, in an `l-foto` box (≥ 40% of the area).
- Never text directly on a photo: always on a solid brand-color block.
- Before/after only with 2 real photos **and** the briefing saying they are before and after. Never in health niches.
