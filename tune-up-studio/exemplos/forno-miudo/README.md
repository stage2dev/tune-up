# Forno Miúdo (fictional example)

Neutral sample project for the tune-up studio. The business is invented; any
resemblance to a real one is coincidence.

- **Product:** small-batch sourdough bread and take-away breakfast baskets from a neighborhood bakery.
- **Audience:** people living within walking distance, 25-60, who want fresh bread in the morning and order by WhatsApp.
- **Brand source of truth:** `gabarito.json` (colors as hex, system fonts only, `logo.svg`, tone, CTA). `styles.css` mirrors the same values as CSS variables.
- **Piece copy** (posts, videos) is written in Brazilian Portuguese.
- No external requests: no CDN, no web fonts, no scripts.
- The post (`post-4x5/`, with `copy.md`) and the reel (`video-9x16/`) follow the conventions of `referencias/` (`l-*` arrangements, scene ids `s<N>_*`, one call to action) and pass `--atencao`.
- `briefing.md` holds the only facts the pieces use (the QA reads it as `entrada.md`); `estrategia.md` is the strategy step written for them.
- Both pieces open on the reader's situation ("O pão acabou antes de você?"), not on the product, and both come from the composition kit: `post-4x5/peca.json`, `video-9x16/peca.json` and one drawing, `heroi.svg` (a wicker basket: crumbs before, three loaves dropping in and steam drawing itself after), assembled by `scripts/montar.py`. Nothing in `fonte/index.html` was written by hand.
- Post: composition `palco` (the hero on a light arch, the offer on a price tag: name + `6h` + proof, a full call band). Reel, 10 s: hook, close-up on-ramp, offer (the hour giant on the accent band while the basket fills), end card with the hero at 83% of the width; cuts at 1.875, 4.375 and 6.875 s, off the 0.25 s grid.
- Round 7: the reel is the style `produto-em-destaque` (`estilo:` in `estrategia.md`); a marker draws under the hook's key words, the basket fills the hook (`heroi_topo_antes`), a cursor presses the contact on the end card.
- Proven on 2026-11-12 with HyperFrames 0.9.6 in a job layout: post `PRONTO: 1 de 1 quadros verdes` (`--final --atencao`), reel rendered and `PRONTO: video verde (hyperframes)` (`--atencao`, `check --strict` clean); two renders gave the same MP4 byte for byte.
