# Visual devices

Read by the post, video and anuncio skills when choosing each frame's or scene's device (Copy or Script step) and in the HTML step, to paste its recipe.
No piece is a text-only poster. Every post frame, the Meta ad image, and reel scene 1, the payoff scene and the end card carry **one device that is not text**; the QA check `recurso_visual` fails a frame or key scene without one.

## What the QA counts
A business photo `<img>` printed by `fotos.py` (the logo never counts); an inline `<svg>`, or an empty element (no text) with a brand `background`, in `px` or `%`, covering 2% to 85% of the frame (one 90% as wide or tall as the frame only when rotated, round or cut by `clip-path`: a plain band behind text is background); a text of 200 px or more (the number of `l-numero`, the one giant word of the hook); a highlighter (a `<span>` in the `<h1>` with its own brand background).

## Choose by the hook, never in a fixed order
| the chosen hook or archetype has | device | or |
|---|---|---|
| a business photo (`fotos.py` printed one) | the photo, big (`l-foto`) | always first |
| a product or collection, no photo | product silhouette, big | giant number (sizes, count) |
| a number, hour, price or deadline of the briefing | giant number | progress bar |
| the reader's situation or pain | situation figure | giant word |
| a customer's question or objection | chat bubble | sticker with the answer |
| steps, a list, signs, how it works | checklist with ticks | giant number (the count) |
| before/after, old vs new, myth vs truth | the same figure in two states | progress bar |
| an offer, a novelty, a guarantee | sticker | diagonal block |
| none of these (short briefing) | big shape + highlighter | situation figure |

- The device shows the product, the person in the situation or the moment of use; abstract shapes alone (a circle, a block) only frame it. A product sold without a photo is drawn as its silhouette, never left out.
- Carousel and reel: never the same device in two frames or scenes in a row, except the same drawing **transforming** (the bent figure stands up, the empty basket fills, the bar completes): that counts as a new device and is the strongest payoff. Write it per frame in `copy.md` (`recurso:`) and per scene in `roteiro.md`.
- The device takes the biggest empty part of the arrangement (QA `ocupacao` measures the pixels: no void above 15% of a post's safe area or 18% of a reel scene's), in one brand color; `accent` stays on one element per frame.
- Figures and silhouettes are yours: 6 to 15 basic shapes (`rect`, `circle`, `ellipse`, `line`, `polyline`, a simple `path`), at least 45% of the frame width, never `<text>`. Never the stock icon of a sector: bakery wheat or chef hat, clinic stethoscope, tech rocket or a browser window with a cursor, fashion hanger, scissors or tape measure, beauty hair dryer or comb, pet bone or paw, food cutlery, garage wrench or a bare car in profile. The figure carries one detail of this briefing that a competitor's would not: what the reader takes along (luggage for a trip), the number it proves (ticks for the items checked), the moment (the queue, the clock).
- Nothing leaves the frame: HyperFrames `check --strict` fails a text outside its box and a painted shape outside the canvas. Only text keeps the 80 px margin: a disc, ground or band that touches a side runs to the real edge (x 0 or 1080, y 0 or the bottom) and is drawn as its visible part inside the canvas; a shape that stops between x 900 and 1079 looks like a wrong crop. A word is never cut by the edge.
- Reel: the element is a clip `s<N>_<role>` (`forma`, `icone`, `selo`, `bolha`, `barra`) with the scene's timing, or the hero `deco1` that lives the whole video; its motion comes from motion-js.md (the engine moves the `<g>` parts inside an `<svg>` clip, so the drawing itself transforms).

## Recipes
Post coordinates for 1080x1350 inside `#root { position: relative }`: move them to the empty area of your arrangement. Colors only `var(--...)`; text pairs only from `--pares`. pt-BR text is a mold.

### Giant number or word (`l-numero`, or the strongest word of the hook as the `<h1>`, the rest in the support line; the reel: recipe 5 of padroes-cena.md)
```html
<h1 class="num">6h</h1><style>.num { font-size: 320px; line-height: .9; letter-spacing: -0.03em; }</style>
<h1 class="palavra">Chiado?</h1><style>.palavra { font-size: 220px; line-height: 1; letter-spacing: -0.03em; }</style>
```
### Highlighter (the key words of the `<h1>`; text and background a pair from `--pares`)
```html
<h1>Banho <span class="mt">sem sair de&nbsp;casa</span></h1><style>.mt { background: var(--accent); color: var(--bg); padding: 0 .12em; box-decoration-break: clone; }</style>
```
### Offer stack (the briefing's offer name, its price as the second level on an accent band that bleeds off the left edge, the proof under it; the price is `#oferta`, 96-140 px, the h1 1.1x bigger; never the price alone in a sticker)
```html
<p class="rotulo">Cesta de&nbsp;domingo</p><div class="faixa-preco"></div><p id="oferta">R$&nbsp;39</p>
<style>.rotulo { position: absolute; left: 80px; top: 600px; margin: 0; font-family: "Brand Heading"; font-size: 48px; color: var(--primary); } .faixa-preco { position: absolute; left: 0; top: 664px; width: 520px; height: 168px; background: var(--accent); clip-path: polygon(0 0, 100% 6%, 96% 100%, 0 100%); } #oferta { position: absolute; left: 80px; top: 664px; margin: 0; font-family: "Brand Heading"; font-size: 136px; line-height: 1.2; color: var(--text); }</style>
```
### Sticker (up to 2 lines of at most 9 characters; the text box is the square inscribed in the circle, 70% of its diameter, same center and rotation, so the text stays inside and the contrast check reads the circle)
```html
<div class="selo"></div><p class="selo-txt">fornada<br>pequena</p>
<style>.selo { position: absolute; right: 80px; top: 200px; width: 300px; height: 300px; border-radius: 50%; background: var(--accent); transform: rotate(-10deg); } .selo-txt { position: absolute; right: 125px; top: 245px; width: 210px; height: 210px; margin: 0; display: flex; align-items: center; justify-content: center; text-align: center; font-size: 40px; line-height: 1.1; color: var(--bg); transform: rotate(-10deg); }</style>
```
### Chat bubble or notification (the customer's question, as the briefing writes it)
```html
<div class="bolha"></div><p class="bolha-txt">Atende sábado?</p>
<style>.bolha { position: absolute; left: 80px; top: 760px; width: 720px; height: 180px; border-radius: 44px 44px 44px 8px; background: var(--surface); } .bolha-txt { position: absolute; left: 124px; top: 812px; width: 640px; margin: 0; font-size: 48px; line-height: 1.2; color: var(--text); }</style>
```
### Checklist with ticks (one tick per item row; the items are text at x 200)
```html
<svg class="ticks" viewBox="0 0 40 220" aria-hidden="true"><polyline points="6,20 16,30 34,8"/><polyline points="6,110 16,120 34,98"/><polyline points="6,200 16,210 34,188"/></svg>
<style>.ticks { position: absolute; left: 80px; top: 520px; width: 96px; height: 528px; fill: none; stroke: var(--accent); stroke-width: 6; stroke-linecap: round; }</style>
```
### Progress bar (before/after, a deadline, steps done; labels are text)
```html
<div class="trilho"></div><div class="cheio"></div>
<style>.trilho, .cheio { position: absolute; left: 80px; top: 980px; height: 72px; } .trilho { width: 920px; background: var(--surface); } .cheio { width: 600px; background: var(--primary); }</style>
```
### Diagonal block or big shape (a slanted band that text may sit on with a `--pares` pair; a quarter disc in a corner)
```html
<div class="diagonal"></div><style>.diagonal { position: absolute; left: 0; top: 760px; width: 1080px; height: 560px; background: var(--primary); clip-path: polygon(0 18%, 100% 0, 100% 82%, 0 100%); }</style>
<div class="forma"></div><style>.forma { position: absolute; right: 0; top: 0; width: 440px; height: 440px; border-radius: 0 0 0 100%; background: var(--accent); }</style>
```
### Situation figure (the reader's moment as a metaphor, never a pictogram at a desk: the part the service is about, big and in its problem state, such as segments slumping along a curve, a pile of unanswered bubbles, the empty container; each part is a `<g>` placed and turned on the curve, a `--text` twin 8-12 px behind it gives depth, and a `--surface` disc cut by the frame edge sits behind; leave 40 px between the drawing and the headline; the mold shows 3 of its parts)
```html
<svg class="cena" viewBox="480 200 600 900" aria-hidden="true"><path class="disco" d="M1080 294 A350 350 0 1 0 1080 906 Z"/><g transform="translate(813 515) rotate(-53)"><rect class="sombra" x="-52" y="-24" width="104" height="48" rx="22"/></g><g transform="translate(805 505) rotate(-53)"><rect class="peca" x="-52" y="-24" width="104" height="48" rx="22"/></g><g transform="translate(922 715) rotate(-5)"><rect class="sombra" x="-60" y="-24" width="120" height="48" rx="22"/></g><g transform="translate(914 705) rotate(-5)"><rect class="peca" x="-60" y="-24" width="120" height="48" rx="22"/></g><g transform="translate(858 985) rotate(25)"><rect class="sombra" x="-67" y="-24" width="134" height="48" rx="22"/></g><g transform="translate(850 975) rotate(25)"><rect class="peca" x="-67" y="-24" width="134" height="48" rx="22"/></g><rect class="peca" x="1002" y="600" width="30" height="430" rx="15"/></svg>
<style>.cena { position: absolute; left: 480px; top: 200px; width: 600px; height: 900px; } .cena .disco { fill: var(--surface); } .cena .sombra { fill: var(--text); } .cena .peca { fill: var(--primary); }</style>
```
The `<svg>` box covers only the drawing (the QA counts a device of 2% to 85% of the frame; the `viewBox` keeps the frame coordinates). A disc bigger than its corner is drawn as its visible part (`path` with an arc, as above): a `circle` crossing the `<svg>` edge fails `container_overflow`, a `div` crossing the frame fails `panel_out_of_canvas`.
### Product silhouette (a shirt here; draw the product sold: dress, bag, bread, plate, part; thin lines in `--bg` give the material's texture)
```html
<svg class="produto" viewBox="0 0 100 100" aria-hidden="true"><path d="M30 8 L42 4 Q50 12 58 4 L70 8 L90 26 L79 39 L70 31 L70 96 L30 96 L30 31 L21 39 L10 26 Z"/><line class="trama" x1="36" y1="44" x2="64" y2="44"/><line class="trama" x1="36" y1="58" x2="64" y2="58"/><line class="trama" x1="36" y1="72" x2="64" y2="72"/><line class="trama" x1="36" y1="86" x2="64" y2="86"/></svg>
<style>.produto { position: absolute; right: 60px; top: 360px; width: 560px; height: 560px; fill: var(--primary); } .produto .trama { stroke: var(--bg); stroke-width: 1.5; }</style>
```
### CTA band with the channel icon (the last frame: verb + where on line 1, condition and deadline on line 2; the icon is a chat bubble, an envelope or a pin of your own, never a brand logo; when the figure stands on a ground (road, counter, floor), that ground runs down to the bottom edge as the band, flat, in `--text`)
```html
<div class="faixa-cta"></div><svg class="canal" viewBox="0 0 100 100" aria-hidden="true"><path d="M50 10 C74 10 90 26 90 46 C90 66 74 80 50 80 L28 92 L32 74 C18 68 10 58 10 46 C10 26 26 10 50 10 Z"/><circle class="ponto" cx="34" cy="46" r="6"/><circle class="ponto" cx="50" cy="46" r="6"/><circle class="ponto" cx="66" cy="46" r="6"/></svg><p id="cta">Chame no WhatsApp<br>e escolha o horário</p>
<style>.faixa-cta { position: absolute; left: 0; top: 1060px; width: 1080px; height: 290px; background: var(--primary); clip-path: polygon(0 16%, 100% 0, 100% 100%, 0 100%); } .canal { position: absolute; left: 80px; top: 1150px; width: 104px; height: 104px; fill: var(--bg); } .canal .ponto { fill: var(--primary); } #cta { position: absolute; left: 212px; top: 1130px; width: 788px; margin: 0; font-size: 56px; font-weight: 700; line-height: 1.12; color: var(--bg); }</style>
```
