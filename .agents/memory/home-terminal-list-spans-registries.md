# Home terminal listing spans registries

Home sections share `__self__`, but auth derives the request root from the
page Referer. Listing only that root hides Home terminals when switching
between Overview and a vault. Legacy Home tmux names and runtime records may
belong to different vaults even though durable Home metadata is shared.

The Home list must combine `__self__` rows from the server's configured root,
registered vaults, and framework checkout, independently of the Referer.
Deduplicate by live tmux name, preserve saved ordering, and perform one tmux
listing and one agent-detail enrichment for the combined pool. Real workspace
lists retain their vault boundary; Home remains admin-only.
