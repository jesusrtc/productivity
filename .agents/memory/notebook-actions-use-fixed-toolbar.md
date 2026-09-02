# Notebook actions use the docked navigation toolbar

Notebook-wide actions (Runtime, Run all, Restart & run all, Interrupt, and
Restart kernel) live in the full-width, top-docked `.nb-jump-controls` bar alongside
Start/End and Show/Hide code. Keep `All notebooks` in the notebook header.
The toolbar must remain visible while scrolling long notebooks and account for
the sidebar and open terminal panel widths. Actions are compact icons with
immediate custom `data-nb-tooltip` labels plus `aria-label` attributes; do not
fall back to delayed native `title` tooltips. Toggle controls such as Hide code
must expose `aria-pressed` and keep a persistent visual selected state.
