# Lab operating docs and absolute context

The client requires a maintained `docs/USER-GUIDE.md` and `docs/CHANGELOG.md`.
Every Lab change the client requests must ALWAYS update the user guide in the
same change, with a changelog entry and relevant topic updates. This includes
changes to operational guidance. Treat documentation as required work.

Operating guidance belongs in the user guide; startup context requires agents
to read it and the changelog, plus the owning instruction files. References
must use absolute paths to the actual installation's docs and existing vault,
workspace, Objective and selected-folder instructions. This supersedes the
earlier preference for source-relative instruction paths. Keep source capture
and drag scope stable. META exposes both docs and existing scoped instructions.
Wheels/sdists ship canonical docs; editable installs use checkout `docs/` files.

Lab launches pin workspace/Objective ownership independently of the launch
folder, so linked worktrees retain owning rules. Do not generate instruction
or memory files in user vaults as part of framework integration.
