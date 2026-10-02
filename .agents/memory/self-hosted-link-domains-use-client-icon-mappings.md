# Self-hosted link domains use client icon mappings

The user wants company and self-hosted tool domains mapped to any bundled
service icon, including Grafana, or an uploaded icon for a custom tool. Manage
these client-wide mappings in Settings → Global → Links and icons, using the
validated `linkDomainMappings` setting rather than editing metadata files.

Exact hostname matching is the default. Including subdomains is optional;
the most specific configured hostname wins before built-in URL heuristics.
Browser detection and backend inference share that policy. Saving mappings
updates mounted link icons immediately; older in-flight reads cannot replace
the newer configuration. Removing a mapping must not reuse its former name as
a legacy service hint.

Uploads are decoded and resized to at most 64 pixels in the browser, then
stored as validated, bounded PNG data in the client settings. Original SVGs
and external image URLs are not stored. Keep upload drafts on failed saves.
