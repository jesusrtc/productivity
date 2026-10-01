# Markdown editor builds use local lock entries

The live Markdown bundle is built from scripts/markdown-editor with npm ci and
npm run build. Its package-lock.json must use ordinary node_modules/ entries,
not links to a /private/tmp build tree. Temporary-directory package records made
npm ci reject the committed lockfile. Normalize paths without changing pinned
versions or integrity hashes, and check a clean npm ci before rebuilding both
the checked-in bundle and its dependency licenses.
