# Legacy behavior references

This directory records behavior that must survive architectural migrations.
These documents are parity references, not active implementations.

Do not keep copied executable implementations here. During a migration, move
the active implementation to its new owner and use Git history plus the parity
record to audit behavior.

- [Darwin notebook behavior](darwin-notebook-behavior.md) — behavior of the
  embedded Darwin executor before notebook providers are introduced.

