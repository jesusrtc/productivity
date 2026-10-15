from types import SimpleNamespace

from core import terminal_llm


def test_detects_only_agent_processes_in_own_pane_tree_and_respects_off(monkeypatch):
    rows = [dict(name=str(pid), pane_pid=pid, tmux_id=f'${pid}', tmux_socket='owned',
                 llm_controlled=False if pid == 50 else None) for pid in (10, 20, 30, 50)]
    snapshot = {pid:dict(ppid=1, stat='S', comm='/bin/zsh') for pid in (10,20,30,50)}
    snapshot.update({11:dict(ppid=10,stat='S',comm='/usr/bin/codex'),
                     12:dict(ppid=11,stat='S',comm='/usr/bin/node'),
                     21:dict(ppid=20,stat='S',comm='/usr/bin/python'),
                     31:dict(ppid=30,stat='Z',comm='claude'),
                     51:dict(ppid=50,stat='S',comm='copilot')})
    monkeypatch.setattr(terminal_llm, 'processes', lambda candidates:snapshot)
    monkeypatch.setattr(terminal_llm.psutil, 'Process', lambda pid:SimpleNamespace(cmdline=lambda:['node','other.js','codex']))
    calls=[]
    monkeypatch.setattr(terminal_llm.subprocess,'run',lambda argv,**kw:calls.append(argv))
    terminal_llm.enrich(rows)
    assert [r['llm_controlled'] for r in rows] == [True,False,False,False]
    assert rows[0]['agent'] == 'codex'
    assert len(calls)==1 and calls[0][-4:] == ['-t','$10','@lab_llm','codex']
    # No repeated process scan for marked sessions.
    monkeypatch.setattr(terminal_llm, 'processes', lambda candidates:1/0)
    terminal_llm.enrich(rows[:1])


def test_node_agent_detection_uses_script_path_not_prompt_arguments(monkeypatch):
    argv=['node','/bin/tool.js','/node_modules/@openai/codex/bin/codex.js']
    monkeypatch.setattr(terminal_llm.psutil,'Process',lambda pid:SimpleNamespace(cmdline=lambda:argv))
    assert terminal_llm.provider(10,'node') is None
    argv[1]='/opt/node_modules/@openai/codex/bin/codex.js'
    assert terminal_llm.provider(10,'node') == 'codex'
    assert terminal_llm.provider(10,'python') is None


def test_missing_process_snapshot_does_not_mark_shell(monkeypatch):
    monkeypatch.setattr(terminal_llm,'processes',lambda rows:None)
    rows=[dict(pane_pid=10)]
    terminal_llm.enrich(rows)
    assert rows == [dict(pane_pid=10,llm_controlled=False)]
