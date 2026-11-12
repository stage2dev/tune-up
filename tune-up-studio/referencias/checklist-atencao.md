# Attention checklist

Read by the post, video and anuncio skills in the Inputs step (the regulated-niche rules bind the copy from the start) and again in the self-review step, while looking at the snapshot or the contact sheets.

## Score (0 or 1 each)
| # | item | how to check on the snapshot | usual fix |
|---|---|---|---|
| 1 | the cover / frame 0 stops the thumb on its own, with no logo first | one big thing to read or see in under a second; the logo is never the dominant element | bigger headline, fewer words; the logo small in its corner (video: out of frame 0) |
| 2 | the hook speaks to the reader, passes the swap test and has a concrete | could a competitor post the same headline? is the offer alone the headline? | the reader's situation or question as headline, the offer as support (`ganchos.md`) |
| 3 | one promise; on-ramp in the 2nd frame/scene; payoff before the CTA | does 2 continue 1, and does the one before the CTA bring a new fact? | rewrite 2 to continue the hook; move the proof right before the CTA |
| 4 | one dominant element, ≤ 3 text levels | squint: one shape or text wins | cut the third text level |
| 5 | headline readable at 1/3 of the size; no letter cut; each sentence starts a line; no line ends in a 1-2 letter word | read every line end of the headline and the CTA: "o", "E", "de" alone is a 0 | `<br>` between sentences; `&nbsp;` after short words; padding on clipped text |
| 6 | no template look: arrangements and devices vary, not "headline, sticker, band" again | the eye sees a new layout at each cut: the title moves, the hero is reframed; the `l-*` class alone does not count | another composition or variant of the kit (kit-post.md, kit-video.md) |
| 7 | only brand colors; `accent` on one element; logo in the same place, visible, with the brand name written | no color outside the kit; the logo never on its own main color | a pair from `--pares`; a plate behind the logo; the name beside it |
| 8 | the device shows the product, the situation or the moment of use (the real photo when it exists, never under text); never only text or only abstract shapes | a stranger can tell what is sold or for whom without reading | the hero redrawn by heroi.md, with the briefing's detail, 45% wide or more |
| 9 | one CTA: verb + where + a gain not said before, the channel icon, the briefing's condition and deadline | the last frame/scene names the verb, the channel and the deadline; it does not repeat the support line | rewrite the CTA; put the deadline back before any support text |
| 10 | no number, name or promise outside the briefing; regulated niche respected (below) | every number on the art is in `entrada.md` or the brand kit | delete it; never replace it with another guess |
| 11 | no tic and no `!` on the art; the frame is full | the list below; text + device fill most of the safe area | rewrite from the fact; a bigger device or text |
| 12 | video only: something moves every 0.5 s (the end card too), the hero transforms with the proof, no half-gone text | `folha.png` (one frame every 0.5 s): 2 equal frames in a row before the last second is a 0; `folha_cortes.png`: a word cut in half, an empty band, an icon without its ring or a transition leftover is a 0 | the kit already does it: if a frame is still or broken, the hero is missing its loops or its change (heroi.md) |

Rule: any item at 0 is fixed in a fix round (the worst first), whatever the total. If item 1, 5 or 9 is still 0 after the rounds, the answer is `PRECISA DO SEU OLHO: autoavaliação item <n>`, never `PRONTO`. Totals: video 12; a carousel 11 (item 12 does not apply); a piece of one frame (single post, ad image) 9 (also skips items 3 and 6).
Write in `resultado.md`: `autoavaliacao: <score>/<total> | pior: <item> | corrigido: sim|não`.

## Director score (0-10; the bar is 9)
Then look again as an exacting creative director who asks "does it stop the thumb, does it look made by a studio, is it clear what to do?". Five criteria, 0, 1 or 2 each:
| criterion | 2 means |
|---|---|
| stops the thumb | frame 0 or the cover has one huge thing (headline across 70% of the width, or the hero) and a concrete situation |
| reads in 3 s | the offer is named as the briefing names it (the service) and its price or offer word is the second level, big and highlighted; 3 text levels at most; the CTA says verb + channel + deadline once |
| art direction | its own drawing with a detail of this briefing (what it carries, the number it shows) and depth (an offset twin, layers, contrast of scale); shapes bleed to the real frame edge; an asymmetric layout; no copied mold. A figure any business of the sector could post (a car in profile, a tooth, a cup) is a 0 here |
| motion (reel) or eye path (post) | reel: nothing still for 0.5 s, the hero transforms in the payoff, no dry cut; post: title, device, offer, CTA in one path, no shape touching a text |
| finish | brand colors only, logo with the name, no cut letter, nothing loose (an icon without its ring, a leftover of a transition) |
Score as the stranger who will judge it, not as its author: a criterion you hesitate on is a 1. Below 9: fix the weakest criterion in a visual round and look again. Write `nota_diretor: <n>/10 | pior: <criterion>` in `resultado.md`. Never answer `PRONTO` below 9 while a visual round is left; after the last one the answer is `PRECISA DO SEU OLHO: nota do diretor <n>/10`.

## Finish (the QA checks all of it)
- `text-wrap: balance` on `#root`; in a headline, `<br>` between two sentences (the reel: the second one in `_destaque`) and `&nbsp;` after every 1-2 letter word ("O&nbsp;pão", "às&nbsp;6h"), so no line ends in "o", "E" or "de" (QA `legibilidade`).
- A text with `clip-path` or `overflow: hidden` keeps `padding: .12em 0 .2em` (or `line-height` 1.2): accents and the legs of g, j, p, q, y stay whole.
- The logo never sits on its own main color: give it a round plate in `--bg` (padding 16 px) or move it. The brand name is written next to it (QA `marca`).
- Occupancy (QA `ocupacao`, on the pixels): no plain-background void above 15% of a post's safe area or 18% of a reel scene's; a block of another brand color is a device, a flat frame is empty.

## Regulated niches (health, legal, finance)
- Never, on the art, in the caption or in ad texts: "melhor", "garantido", "cura", "100%", "sem dor", patient before/after, a promise of result.
- Use: "consulta", "avaliação", "agende", "atendimento", "orientação"; the professional's registration only if written in the briefing. Molds: "Avaliação com horário marcado aos sábados." / "Orientação para o seu MEI, com hora marcada."

## Tics
Compared in lowercase, without accents, spaces collapsed, by whole word. The em dash matches as a character. On the art (post and video) `!` is also forbidden. Never write these; if one slipped in, rewrite the sentence from the fact, do not swap in a synonym.

```tiques
—
nao e so
nao e apenas
mais do que um
diga adeus
proximo nivel
descubra o poder
no mundo corrido
seja voce
experiencia unica
o resultado?
o melhor:
pare de rolar
venha conhecer
qualidade e tradicao
imagine so
```

Also avoid, though the script does not check them: a list of negations ("sem fila, sem estresse, sem complicação"), a drumbeat of fragments ("Rápido. Fácil. Gostoso."), a question the piece answers itself, and every word in capitals.
