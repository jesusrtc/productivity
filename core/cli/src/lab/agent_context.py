"""Framework capabilities supplied at launch, without workspace filesystem changes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import time

GUIDE_DIR = Path(__file__).parent / 'resources' / 'agent-context'
TOPICS = {'overview': 'AGENTS.md', 'markdown': 'markdown.md',
          'notebooks': 'notebooks.md', 'servers': 'servers.md',
          'meetings': 'meetings.md', 'tasks': 'tasks.md',
          'objectives': 'objectives.md', 'cli': 'cli.md',
          'migrations': 'migrations.md', 'user-guide': 'USER-GUIDE.md',
          'changelog': 'CHANGELOG.md'}
DOCUMENTS = {'user-guide': 'Lab user guide', 'changelog': 'Lab changelog'}
AGENTS = ('codex', 'claude', 'copilot')


class ContextError(RuntimeError):
    pass


def guide_path(topic: str = 'overview') -> Path:
    if topic in DOCUMENTS:
        # Editable checkouts read the canonical docs; wheels/sdists carry copies
        # made by the package build, independent of the developer's checkout.
        source = Path(__file__).resolve()
        checkout = source.parents[4] if len(source.parents) > 4 else None
        if checkout is not None and source.parent == checkout / 'core/cli/src/lab':
            return checkout / 'docs' / TOPICS[topic]
        return Path(__file__).parent / 'resources/docs' / TOPICS[topic]
    return GUIDE_DIR / TOPICS[topic]


def documentation() -> list[dict[str, str]]:
    return [{'name': name, 'title': title, 'path': str(guide_path(name).resolve())}
            for name, title in DOCUMENTS.items()]


def _path_code(path: Path | str) -> str:
    value = str(path).replace('\n', '\\n').replace('\r', '\\r')
    fence = '`' * (max((len(run) for run in re.findall(r'`+', value)), default=0) + 1)
    return f'{fence} {value} {fence}' if '`' in value else f'{fence}{value}{fence}'


def read_context(topic: str = 'overview', *, source_root: Path | None = None,
                 vault_root: Path | None = None, workspace_root: Path | None = None,
                 objective_root: Path | None = None) -> str:
    """Read the guide with installation-specific, absolute documentation paths."""
    guide = guide_path(topic).read_text(encoding='utf-8')
    if topic != 'overview':
        return guide
    docs = '## Lab documentation\n\nRead the user guide and changelog before working with Lab, unless already loaded.\n\n'
    docs += '\n'.join(f'- {doc["title"]}: {_path_code(doc["path"])}.' for doc in documentation())
    intro, rest = guide.split('\n\n', 1)
    guide = intro + '\n\n' + docs + '\n\n' + rest
    if source_root is None:
        return guide
    # One packaged template, instantiated against the captured explorer scope.
    # Preserve the visible path spelling, including linked checkout directories.
    source = Path(os.path.abspath(source_root))
    roots = [('Vault', vault_root), ('Workspace', workspace_root), ('Objective', objective_root)]
    if source not in [Path(os.path.abspath(root)) for _, root in roots if root is not None]:
        roots.append(('Source folder / worktree', source))
    rows = []
    for label, root in roots:
        if root is None:
            continue
        root = Path(os.path.abspath(root))
        files = [_path_code(root / name) for name in
                 ('AGENTS.md', 'agent.md', 'CLAUDE.md', '.github/copilot-instructions.md')
                 if (root / name).is_file()]
        instructions = ', '.join(files) if files else 'no root instruction files found'
        rows.append(f'- {label} root: {_path_code(root)}; instructions: {instructions}.')
    template = (GUIDE_DIR / 'instruction-paths.md').read_text(encoding='utf-8')
    scoped = template.replace('{{source_root}}', _path_code(source)).replace('{{instruction_paths}}', '\n'.join(rows))
    intro, rest = guide.split('\n\n', 1)
    return intro + '\n\n' + scoped.rstrip() + '\n\n' + rest


def current_context(*, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    """Include owning roots discoverable from this terminal without creating files."""
    from lab import paths, objective_store
    cwd = (cwd or Path.cwd()).resolve()
    env = os.environ if env is None else env
    selected = env.get('LAB_VAULT') or env.get('LAB_WORKSPACE') or env.get('LAB_ROOT')
    vault = workspace = objective = None
    try:
        vault = Path(selected).expanduser().resolve() if selected else paths.find_vault_root(cwd, use_registry=False, env=env)
        workspace = paths.workspace_dir(vault, paths.find_workspace_id_from_pwd(vault, cwd))
    except (paths.MonorepoNotFound, paths.WorkspaceNotFound):
        pass
    workspace_id = env.get('LAB_CONTEXT_WORKSPACE')
    objective_id = env.get('LAB_CONTEXT_OBJECTIVE')
    if workspace_id:
        if vault is None or workspace_id in ('.', '..') or any(c in workspace_id for c in ('/', '\\', '\x00')):
            raise ContextError('Invalid owning workspace for agent context')
        workspace = paths.workspace_dir(vault, workspace_id).resolve()
        if not workspace.is_dir():
            raise ContextError(f'Owning workspace not found: {workspace_id}')
    if objective_id and workspace is None:
        raise ContextError('Choose the owning workspace for this Objective')
    if workspace is not None:
        try:
            rows = objective_store.read(workspace)['objectives']
        except (ValueError, OSError):
            if objective_id:
                raise ContextError('Unable to read the owning Objective metadata')
            rows = []
        for row in rows:
            root = Path(row['path']).resolve()
            if row['id'] == objective_id or (not objective_id and cwd.is_relative_to(root)
                    and (objective is None or len(root.parts) > len(objective.parts))):
                objective = root
        if objective_id and objective is None:
            raise ContextError(f'Owning Objective not found: {objective_id}')
    return read_context(source_root=cwd, vault_root=vault, workspace_root=workspace, objective_root=objective)


def _codex_config_options(args: list[str], cwd: Path) -> tuple[list[str], list[str], Path]:
    """Pass config overrides through Codex itself; replace only the merged text key.

    The agent still receives every other option, including resume IDs, model,
    approval policy and sandbox settings. Never interpret text after a literal --.
    """
    config_args: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(args):
        item = args[index]
        if item == '--':
            remaining.extend(args[index:])
            break
        if item in ('-c', '--config', '-C', '--cd'):
            if index + 1 >= len(args):
                raise ContextError(f'{item} requires a value')
            value = args[index + 1]
            pair = [item, value]
            index += 2
        elif item.startswith(('--config=', '--cd=')):
            key, value = item.split('=', 1)
            item, pair = key, [args[index]]
            index += 1
        elif item.startswith('-c') and len(item) > 2:
            value, pair, item = item[2:], [item], '-c'
            index += 1
        else:
            remaining.append(item)
            index += 1
            continue
        if item in ('-c', '--config'):
            config_args.extend(['-c', value])
            if value.split('=', 1)[0].strip() != 'developer_instructions':
                remaining.extend(pair)
        else:
            cwd = (cwd / Path(value).expanduser()).resolve()
            remaining.extend(pair)
    return config_args, remaining, cwd


def _codex_developer_instructions(binary: str, config_args: list[str], cwd: Path,
                                   env: dict[str, str]) -> str:
    """Read Codex's trusted, effective config without starting a model turn.

    config/read resolves user + project layers. Parsing just ~/.codex/config.toml
    would silently drop project-level developer instructions and trust decisions.
    No config values are logged or persisted by Lab.
    """
    process = subprocess.Popen([binary, *config_args, 'app-server'], cwd=cwd, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = b''
    deadline = time.monotonic() + 12

    def rpc(ident: int, method: str, params: dict) -> dict:
        nonlocal buffer
        process.stdin.write((json.dumps({'id': ident, 'method': method, 'params': params}) + '\n').encode())
        process.stdin.flush()
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                message = json.loads(line)
                if message.get('id') == ident:
                    if 'error' in message:
                        raise ContextError('Codex could not resolve its existing instructions')
                    return message['result']
        raise ContextError('Timed out reading Codex instructions; update the Codex CLI and retry')

    try:
        rpc(1, 'initialize', {'clientInfo': {'name': 'lab_context', 'version': '1'}})
        config = rpc(2, 'config/read', {'cwd': str(cwd), 'includeLayers': False})['config']
        value = config.get('developer_instructions')
        if value is not None and not isinstance(value, str):
            raise ContextError('Codex developer_instructions must be text')
        return value or ''
    except (OSError, ValueError, KeyError) as exc:
        raise ContextError('Unable to read existing Codex instructions; nothing was overwritten') from exc
    finally:
        selector.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


def prepare_launch(agent: str, args: list[str], *, cwd: Path | None = None,
                   env: dict[str, str] | None = None) -> tuple[list[str], dict[str, str]]:
    if agent not in AGENTS:
        raise ContextError(f'Unsupported agent: {agent}')
    child_env = dict(os.environ if env is None else env)
    binary = shutil.which(agent, path=child_env.get('PATH'))
    if not binary:
        raise ContextError(f'{agent} CLI not found on PATH')
    cwd = (cwd or Path.cwd()).resolve()
    if agent == 'codex':
        overrides, remaining, config_cwd = _codex_config_options(args, cwd)
        guide = current_context(cwd=config_cwd, env=child_env)
        existing = _codex_developer_instructions(binary, overrides, config_cwd, child_env)
        combined = guide + ('\n\n' + existing if existing else '')
        return [binary, '-c', 'developer_instructions=' + json.dumps(combined), *remaining], child_env
    if agent == 'claude':
        guide = current_context(cwd=cwd, env=child_env)
        # Recent Claude versions retain a resumed conversation's initial system
        # prompt. Refresh it where supported; older versions already rebuild when
        # an append flag is supplied. Preserve an explicit user snapshot choice.
        refresh = []
        if any(arg in ('--resume', '-r', '--continue', '-c') or arg.startswith('--resume=') for arg in args) and not any(arg.startswith('--system-prompt-snapshot') for arg in args):
            try:
                version = subprocess.run([binary, '--version'], stdin=subprocess.DEVNULL,
                                         capture_output=True, text=True, timeout=3, env=child_env)
                match = re.search(r'(\d+)\.(\d+)\.(\d+)', version.stdout)
                if match and tuple(map(int, match.groups())) >= (2, 1, 257):
                    refresh = ['--system-prompt-snapshot', 'off']
            except (OSError, subprocess.TimeoutExpired):
                pass
        # Preserve explicit user append flags by combining them with Lab's guide.
        remaining, additions = [], []
        index = 0
        while index < len(args):
            item = args[index]
            if item == '--':
                remaining.extend(args[index:])
                break
            key, equals, value = item.partition('=')
            if key in ('--append-system-prompt', '--append-system-prompt-file'):
                if not equals:
                    index += 1
                    if index >= len(args):
                        raise ContextError(f'{key} requires a value')
                    value = args[index]
                additions.append((cwd / Path(value).expanduser()).read_text(encoding='utf-8')
                                 if key.endswith('-file') else value)
            else:
                remaining.append(item)
            index += 1
        return [binary, *refresh, '--append-system-prompt', '\n\n'.join([guide, *additions]), *remaining], child_env
    # This process-local setting is additive; the user's own instruction dirs,
    # agent home, auth, and repository discovery all retain their normal behavior.
    dirs = [part for part in child_env.get('COPILOT_CUSTOM_INSTRUCTIONS_DIRS', '').split(',') if part]
    if str(GUIDE_DIR) not in dirs:
        dirs.append(str(GUIDE_DIR))
    child_env['COPILOT_CUSTOM_INSTRUCTIONS_DIRS'] = ','.join(dirs)
    child_env['LAB_AGENT_CONTEXT'] = current_context(cwd=cwd, env=child_env)
    return [binary, *args], child_env
