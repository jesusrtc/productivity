"""Resource release against a real, isolated tmux server and a local dummy agent."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

import pytest
from lab import settings
from core import document_terminals as dm
from core.routes import term
from .test_assistant_documents_unified import library


def test_real_tmux_sleep_releases_agent_and_child(monkeypatch, library, tmp_path):
    if not shutil.which('tmux'):
        pytest.skip('tmux is required')
    root, _, note, *_ = library
    socket='lab-document-test-'+uuid.uuid4().hex[:12]
    pidfile=root/'agent-processes.json'
    script=tmp_path/'claude'
    script.write_text('#!'+sys.executable+'\nimport json,os,subprocess,sys,time\nchild=subprocess.Popen([sys.executable,"-c","import time; time.sleep(300)"])\ncontext=json.load(open(os.environ["LAB_DOCUMENT_CONTEXT"]))\nopen(os.path.join(os.getcwd(),"agent-processes.json"),"w").write(json.dumps({"pids":[os.getpid(),child.pid],"args":sys.argv[1:],"context":context,"home":os.environ["LAB_ASSISTANT_HOME"]}))\nprint("Dummy agent ready",flush=True)\ntime.sleep(300)\n')
    script.chmod(0o700)
    monkeypatch.setenv('PATH',str(tmp_path)+os.pathsep+os.environ['PATH'])
    env={k:v for k,v in os.environ.items() if k not in {'TMUX','TMUX_PANE'}}
    def tmux(*args):
        return subprocess.run(['tmux','-L',socket,*args],env=env,capture_output=True,text=True,timeout=5)
    tmux('-f','/dev/null','new-session','-d','-s','keep-test-server','sleep 300')
    monkeypatch.setattr(term,'_active_tmux_socket',lambda:socket)
    monkeypatch.setattr(term,'_configure_tmux_wheel_scrolling',lambda *args:None)
    monkeypatch.setattr(dm,'_transcript',lambda *args:None)
    monkeypatch.setattr(dm,'_INPUT',{})
    settings.update(root,{'defaultAgent':'claude'})
    def wait_for(fn):
        deadline=time.monotonic()+5
        while not fn():
            assert time.monotonic()<deadline,'Timed out waiting for process state'
            time.sleep(.025)
    def alive(pid):
        result=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True)
        return result.returncode==0 and result.stdout.strip()[:1] not in {'Z',''}
    try:
        first=dm.operate(root,note.stem)
        wait_for(pidfile.is_file)
        launched=json.loads(pidfile.read_text())
        pids=launched['pids']
        assert launched['context']['document_id']==note.stem
        assert launched['home']==str(root)
        assert '--append-system-prompt-file' in launched['args'] and '--session-id' in launched['args']
        assert all(alive(pid) for pid in pids)
        assert dm.operate(root,note.stem)['name']==first['name']
        result=dm.operate(root,note.stem,'sleep')
        assert result['state']=='sleeping'
        wait_for(lambda:not any(alive(pid) for pid in pids))
        assert tmux('has-session','-t',first['name']).returncode!=0
        assert tmux('has-session','-t','keep-test-server').returncode==0
        pidfile.unlink()
        resumed=dm.operate(root,note.stem)
        wait_for(pidfile.is_file)
        assert resumed['name']==first['name']
        assert set(json.loads(pidfile.read_text())['pids']).isdisjoint(pids)
        dm.operate(root,note.stem,'sleep')
    finally:
        tmux('kill-server')
