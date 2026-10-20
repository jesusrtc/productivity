# Linked terminal tabs use their asset names

On October 20, 2026 the user requested terminal tabs linked to a task file to
show the same displayed name as that file, alongside the existing linked icon.
Give the resolved asset title precedence over task titles, saved labels and
fixed-main names, including automation and merged tabs. Exact document subtabs
and URL sublinks use their existing full asset title. Active headers use the
same display helper; asset renames update the display, and unlink restores
normal naming without overwriting the saved terminal label or changing its
identity, process, folder or task membership.

This refines the name-preservation wording in terminal-asset-links-preserve-origin.md
and the saved-name display preference in terminal-tabs-show-only-saved-names.md:
keep saved names in metadata while a linked asset supplies the visible label.
