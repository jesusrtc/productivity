# Assistant document storage and external links

All independent tasks, notes, meetings and series share documents/<id>.md after
`lab assistant migrate --documents --apply`. Keep projects independent and subtabs
embedded. `storage_layout: unified-documents-v1` is separate from schema and
embedded serialization. Unmigrated clients remain readable/writable. Preserve
Markdown bytes, IDs, metadata, aliases and relative asset bases. The explicit
migration owns manifest aliases/origins, verified backups, maintenance and rollback.
Read `lab migrations assistant-documents` and update each client's technical
instructions; never overwrite their content rules or silently migrate on reads.

Optional `external_url` is HTTP(S) or null. Dashboard/list rows, headers, tab rail,
Index and series history expose it. The collapsed series uses its latest note's
URL; series and member links remain independent. These associated-document links
set data-lab-client-external; shared LabExternalLinks opens on the clicking client
even through SSH (where server-side loopback detection cannot identify the real
browser host). Never send these clicks to the server's OS browser. Normal browser
links open a client tab; remotely forcing a different OS default browser needs a
client-side integration and is not claimed by this feature.
