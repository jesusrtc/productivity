# Keep client-specific work out of Lab

Lab is a general-purpose framework. Client-specific workflows, agent roles,
skills, repository defaults, integrations, and historical plans belong in
client vaults or separate repositories. Do not reintroduce them into the
framework checkout. Use neutral examples in framework docs and tests.

Notebook execution uses a configured local Jupyter runtime. An unconfigured
workspace can view notebooks but must configure and build its runtime before
running cells; it must not fall back to an external execution service.
