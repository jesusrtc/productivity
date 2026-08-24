# Local authentication and workspace access

Lab requires a signed `lab_session` cookie for every UI and API route except
the health check, login page, login endpoint, and static assets. Authentication
state is global across registered workspaces and is stored in
`~/.lab/auth.json` with file mode `0600`.

## First-run accounts

| User | Password | Role |
| --- | --- | --- |
| `admin` | `admin` | Built-in Admin |

The built-in account is fixed so a local installation cannot lose its bootstrap
administrator. Lab stores its SHA-256 digest rather than plaintext. Additional
accounts, passwords, roles, disabled state, and workspace grants are managed
from **Home → Admin**. Changing an added user's password or disabling the user
invalidates that user's existing sessions.

Upgrading from the original version removes the seeded `jesus`, `cesar`, and
`miriam` accounts. The administrator can recreate any needed users explicitly
with their intended workspace permissions.

## Roles and access

- Admins can use Home, create or register workspaces, manage users, and access
  every workspace.
- Users see only workspaces explicitly checked for them in **Home → Admin**.
  They can edit those workspaces and use terminals for their workspace and
  project scopes.
- Home, framework administration, consolidated logs, code search, and Home
  terminal scopes are admin-only.
- Requests for an unassigned workspace return `404` so the workspace catalog is
  not disclosed. A user with no assignments sees a restricted landing page.

The implementation is intended to prevent accidental access on a localhost Lab
instance. It is not an internet-facing identity system.
