# Motion in JavaScript (the studio engine)

Read by whoever maintains the reel kit (`scripts/kit_video.py`, `kit_palco.py`): since round 6 the video skill builds from the kit and no longer reads this file.
Every recipe below was rendered with HyperFrames 0.9.6 and looked at frame by frame (round 5: a 10 s reel of an invented garage; round 6: the kit's reels of a garage, a pet shop and a bakery, green in `check --strict` and `qa_video`). Two renders with `--experimental-fast-capture=false` gave the same MP4 byte for byte. No animation library and no network: the engine is about 125 lines of plain JavaScript.

## Contract (QA `script_seguro`)
- Layout in CSS, motion in JS. One inline script, the last thing in `<body>`: first the whole text of `motor-motion.js`, pasted unchanged (the QA compares it), then the scene part, then `M.pronto();` as the last line.
- The engine registers itself on `window.__hfAnime` (the seek hook HyperFrames documents for any object with `seek`, `pause`, `play`): at every frame HyperFrames gives the time and the engine writes the styles. A frame is a pure function of its time, so the snapshot, the render and the reserve slides agree.
- The scene part uses only: `M.<recipe>(...)` calls, `var` with numbers, strings and arrays, `for` loops with a counter, small `function`s that build strings, `Math.*` (never `random`), `.push`, `.forEach`, `.map`, `.length`. Never `document`, `window`, timers, `Date`, `performance`, `fetch` or any network, `eval`, `innerHTML`, `["..."]` access, template strings, `.animate()`; the QA names each one it finds.
- A clip's CSS never sets `transform` (the engine owns it): place with `left`/`top`. No `filter` (drop-shadow and blur differ between two renders): depth is a second shape, offset, in `--surface` or `--text`.
- Keep the text of every clip plain in the HTML (the QA reads it); `palavras` and `contador` rebuild it at load. Paste these helpers in the `<style>`:

```css
.m-caixa { display: inline-block; padding: .12em 0 .2em; margin: -.12em 0 -.2em; vertical-align: top; }
.m-palavra { display: inline-block; }
```

## Recipes
`atraso` counts from the clip's own `data-start` (so these recipes take clip ids only); `t0`/`t1` in `trilha`, `vaivem`, `onda` and `traco` are absolute seconds, so they also drive an `id` inside an `<svg>` clip. Curves: `sai` (fast then soft, the default), `mola` (overshoot, for landings), `meio` (in-out), `entra` (slow then fast), `reta` (linear, for camera, drift and loops).

| recipe | call | does | use for |
|---|---|---|---|
| stagger | `M.palavras(id, atraso, passo, "sobe", t)` | each word rises 0.4 em while it fades in, `passo` (0.04-0.1 s) apart, in `t` s (default .6); never clipped, so a sampled frame never shows half a word | second lines, items |
| wave | `M.palavras(id, atraso, passo, "onda")` | words stay readable and bob once | the hook (scene 1) |
| counter | `M.contador(id, atraso, t)` | counts from 0 to the written number; add `font-variant-numeric: tabular-nums` | a quantity only (items, years, clients); never a price (QA) |
| line draw | `M.traco(id, t0, t)` | a `path` with `pathLength="1"` and `stroke-dasharray: 1` draws itself | speed lines, underline, arrow, tick |
| camera push | `M.camera([ids], de, ate, cx, cy)` | the clips scale together around (cx, cy) over their scene, 1 → 1.06-1.1 | text blocks of a scene |
| reveal mask | `M.mascara(id, atraso, t, lado)` | opens a `clip-path` from `baixo`, `cima`, `esquerda`, `direita` or `centro` | bands, support lines, the contact |
| parallax | `M.parallax([[id, dx, dy], ...])` | each layer drifts its own distance over its scene | a disc or band behind the hero |
| pulse | `M.pulso(id, atraso, periodo, escala)` | 1 → escala → 1 again until the scene ends; 0.6 s and 1.25-1.35 read on the 0.5 s sheet | the CTA ring of the end card |
| entry | `M.entra(id, atraso, t, tipo)` | `sobe`, `esquerda`, `carimbo` (stamp with overshoot), `gira`, `barra`, `painel` | price, sticker, icon, panel |
| ripple | `M.onda([ids], t0, passo, escala)` | a scale wave runs along shapes or texts | a second beat |
| to and fro | `M.vaivem(id, t0, t1, a, b, periodo)` | a `transform` swings a → b → a every `periodo` from t0 to t1 | a body bouncing on its springs, a sign swaying, steam |
| track | `M.trilha(id, prop, [[t, valor, curva], ...])` | any style over the video: `transform`, `opacity`, `fill`, `stroke`, `strokeDashoffset`, `d`, `clipPath` | the hero, the morph, colors at the cuts |

`trilha` blends values with the same numbers in the same places (`translate(0px, 0px) scale(1)` to `translate(-30px, 150px) scale(1.5)`); other shapes (`var(--bg)` to `var(--primary)`) switch at the second time. A jump at a cut is two keys a hair apart: `[4, "scale(1.2)"], [4.0001, "scale(1)"]`. An on/off step is two keys too (`[[0, "0"], [4.44, "0"], [4.45, "1"]]`), or the value fades over the whole gap. Two loops that never stop, both `trilha` with `reta` from 0 to D:
- **scroll**: a dashed `line` (`stroke-dasharray: 110 110`) with `strokeDashoffset` from `0` to a multiple of 220 runs like a road, a belt, a queue or a thread, never leaving the frame.
- **spin**: a part drawn around 0,0 (spokes, a fan, a dial hand) inside `<g transform="translate(x y)">`, with `rotate(0deg)` to `rotate(2700deg)` on the inner `<g id>`.

## Rhythm (QA `movimento`, `freezedetect`)
- Every 0.5 s something visible changes, the end card included: only its last 1 s may rest (QA `movimento` fails 0.75 s almost still anywhere else). A scroll or spin running the whole video, plus the hero drifting 100-150 px inside each scene, gives that for free; a camera of 1 → 1.04 alone does not show.
- Cuts sit off the 0.25 s grid (1.875 s, 4.375 s...) and `tr<N>` (padroes-cena.md) is seen for 0.14 s around its cut, so a frame sampled every 0.5 s never shows a transition (QA `folha_limpa`). Every scene's title is whole at the cut: on it only `palavras(..., "onda")`, `camera`, `parallax`, `pulso` and `onda`; second lines start at `atraso` .5-.7 with `entra(..., "sobe")`; no text gets `mascara`, `entra` `esquerda`/`painel`/`barra` or, on a title, `contador` (QA `texto_inteiro`).
- Scene 1 is readable at frame 0: on its text clips only `palavras(..., "onda")`, `camera`, `parallax`, `pulso` and `onda` (the QA blocks the others); the hero moves from frame 0.
- A price is whole at its cut and takes one `onda` pulse; counting it from 0 puts a false price on screen (QA `script_seguro`) and stamping it in leaves its band empty at the cut (QA `texto_inteiro`).

## The hero (one drawing that carries the story)
One inline `<svg>` clip `deco1` (`data-start="0"`, `data-duration` = the video, `z-index: 2`, `viewBox="0 0 W H"` with the box's own size), built from 15-30 basic shapes with an offset `--text` twin for depth. A ground or band it stands on runs to the frame's bottom edge (1920): no strip of background under it.
- Scene framing comes from one `trilha` on `deco1`'s `transform` (keys `translate(Xpx, Ypx) scale(S)`, a jump at each cut): wide (1-1.1) under the hook, a close-up (1.4-1.6, the detail the service touches) in the on-ramp, back to 1.1-1.2 in the payoff, at least 45% of the frame width on the end card. The `l-*`, the title's place and this scale change at every cut.
- Inside, wrap the figure in `<g id="...">` and drift it 100-150 px per scene with one `trilha` (`translate(-80px, 0px)` → `translate(50px, 0px)`, a jump at each cut): the hero is never parked.
- The payoff transforms the hero with the briefing's own proof, where it is seen: ticks pop on its parts while a counter runs to the number of items checked; what it lacked drops in with `mola` (luggage on the roof, the order in the bag, the full shelf); the bar fills to the written number. Each part that pops is drawn around 0,0 inside `<g transform="translate(x y)">` and scales from `scale(0)` (before its key the first value holds). A color swap alone is not a transformation; colors switch at the cuts with `fill` tracks (`var(--...)` only) so the hero stays visible on each background.

## Choosing, so two businesses never look alike
Pick by the arc of `roteiro.md`, then vary every parameter (alignment, framing, what scrolls or spins, the side the masks open from, the curve of the landing). Never copy a call list, a coordinate or a drawing from here or from an example.

| arc | hero | loop | entry of scenes 2+ | payoff beat | end card |
|---|---|---|---|---|---|
| Situation | the reader's object in their moment | its road, belt or queue scrolls | stagger `sobe` | proof pops on it, the missing part drops in | hero big + ring `pulso` |
| Proof first | the product or its silhouette | a part spins or steams (`vaivem`) | `mascara` from a side | `contador` on the quantity + `traco` under it | stamp + pulse |
| PAS | the object of the pain | the pain shape trembles (`vaivem`) | stagger | the pain shape turns into the fix (`d` morph) | ring pulse |
| Objection | the chat bubble | the dots bounce (`vaivem`) | `carimbo` | the answer lands word by word + tick `traco` | pulse |
| Novelty | the new thing, big | it turns slowly (spin) | `mascara` `centro` | sticker `gira` | pulse |
| Demo in steps | the checklist | the list drifts | items `esquerda`, 0.12 s apart | ticks `traco`, one by one | pulse |

## Self-check before the render
Snapshot `0` plus 25% and 75% of each scene: the two frames of a scene differ visibly; scene 1 at 0 shows the hook whole; the framing of the hero changes at every cut; the payoff at 75% shows the hero transformed with the proof and the price or offer big.
