# Native Plotly notebook output

Lab renders `application/vnd.plotly.v1+json` for saved notebooks and live display
updates through its shared HTML output renderer. Notebook authors do not need
to embed Plotly HTML or use a CDN to work around an empty native-MIME slot.
The vendored Plotly 3.5.1 bundle supports the encoded typed arrays produced by
modern Plotly.py. Keep the MIME-to-HTML adapter deterministic for notebook
history and target adjacent DOM elements so duplicate views cannot share IDs.
Activate newly inserted output scripts once; later live events must preserve
the existing chart's zoom and selection.
