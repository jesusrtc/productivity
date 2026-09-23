"""Opt-in process milestones for the owned document agent, without payloads."""
from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path
import sys


def traced_argv(argv, trace_dir, executable):
    if argv[:3] != [sys.executable, '-m', 'lab']:
        raise ValueError('Unexpected document launcher')
    # -c enters after the interpreter's ordinary site/startup hooks. Delegate to
    # the same runpy entry as -m; do not replace or shadow sitecustomize.
    code = f'''
import os,sys,time
events=[dict(phase='interpreter-ready',epoch=time.time_ns()/1_000_000,cpuMs=time.process_time_ns()/1_000_000)]
original_exec=os.execvpe
def traced_exec(binary,argv,env):
    if binary!={str(executable)!r}:raise RuntimeError('Unowned agent in launch diagnostic')
    events.append(dict(phase='provider-exec',epoch=time.time_ns()/1_000_000,cpuMs=time.process_time_ns()/1_000_000))
    import json
    from pathlib import Path
    Path({str(trace_dir)!r},str(os.getpid())+'.json').write_text(json.dumps(dict(pid=os.getpid(),events=events)))
    child_env=dict(env)
    child_env['LAB_PERF_DOCUMENT_EXEC_EPOCH']=str(time.time_ns()/1_000_000)
    return original_exec(binary,argv,child_env)
os.execvpe=traced_exec
if sys.path and sys.path[0]=='':sys.path[0]=os.getcwd()
import runpy
runpy._run_module_as_main('lab',alter_argv=True)
'''
    return [argv[0], '-c', code, *argv[3:]]


@contextmanager
def document_launch_trace(root, *, enabled=False):
    if not enabled:
        yield None
        return
    root = Path(root).resolve()
    base = root.parent
    if root.name != 'assistant' or not base.name.startswith('lab-navigation-'):
        raise ValueError('Agent launch tracing requires the disposable fixture')
    if Path(os.environ.get('LAB_HOME', '')).resolve() != base/'config':
        raise ValueError('Agent launch tracing requires fixture-owned configuration')
    from core import document_terminals
    original = document_terminals._argv
    trace_dir = base/'detail-launches'
    trace_dir.mkdir()
    report = {'measurement':'Diagnostic interpreter entry and provider exec; includes probe overhead',
              'launches':[], 'restored':False}

    @wraps(original)
    def observed(folder, entry):
        if Path(folder).resolve() != root:
            raise ValueError('Agent launch trace crossed fixture scope')
        return traced_argv(original(folder, entry), trace_dir, base/'detail-bin/claude')

    document_terminals._argv = observed
    try:
        yield report
    finally:
        document_terminals._argv = original
        report['restored'] = True
        report['launches'] = [json.loads(path.read_text()) for path in trace_dir.glob('*.json')]
