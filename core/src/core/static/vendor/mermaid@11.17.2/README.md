Mermaid 11.17.2, vendored from the npm package:
https://registry.npmjs.org/mermaid/-/mermaid-11.17.2.tgz

`mermaid.lab.min.js` is the `dist/mermaid.min.js` standalone browser bundle
with a lexical wrapper `(function (define) { ... })(undefined)` and its final
export changed from `globalThis.__esbuild_esm_mermaid_nm` to the local
`__esbuild_esm_mermaid_nm`. No other upstream code is changed.

FastDOM inside the bundle tests for any global `define` function, even without
`define.amd`, and otherwise registers into Lab's notebook loader instead of
its bundled CommonJS module. The wrapper hides `define` only inside Mermaid,
leaving the page's notebook loader untouched. The distinct filename also
avoids the immutable cache of the previously shipped upstream bundle.

Its MIT license is included in `LICENSE`. Loaded on demand for Mermaid code
fences; no external asset requests are required.
