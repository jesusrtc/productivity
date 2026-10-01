"""Workspace terminal launch choices are deliberate, scoped, and accessible."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest

from .test_frontend_terminal_ui import ROOT, _js_between, _run_node

STATIC = ROOT / 'core/src/core/static'


def test_choices_include_workspace_and_exact_pins_only():
    result = _run_node((STATIC / 'js/lib/terminal-folder.js').read_text() + r'''
const config={folderScopes:[{path:'/repo',label:'Project',color:'#123abc'},
 {path:'/trees/feature',projectPath:'/repo',kind:'worktree',label:'Project/feature',color:'#456def'},
 {path:'/unused',label:'Unused'}],pinnedScopes:['/repo','/trees/feature','/workspace','/repo'],
 selectedFolders:{'/workspace':'/unused'},selectedWorktrees:{'/unused':'/unpinned-tree'}};
console.log(JSON.stringify(window.LabTerminalFolder.choices('/workspace','Workspace',config,'vault::work')));
''')
    assert [row['scope']['root'] for row in result] == ['/workspace', '/repo', '/trees/feature']
    assert [row['kind'] for row in result] == ['Workspace', 'Folder', 'Worktree']
    assert result[2]['scope']['project_root'] == '/repo'
    assert result[2]['scope']['worktree'] == '/trees/feature'
    assert all(row['scope']['base_root'] == '/workspace' and row['scope']['config_scope'] == 'vault::work'
               for row in result)


@pytest.mark.parametrize('viewport', [1440, 390])
def test_folder_chooser_browser(tmp_path, viewport):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    setup = r'''
const assert=(condition,message)=>{if(!condition)throw Error(message)};
let workspace='work',vault='one',home=null;
const _termActiveWorkspaceId=()=>workspace,_termVaultId=()=>vault,_termHomeSection=()=>home;
const _workspaceDisplayName=()=> 'My workspace';
let currentWorkspace={path:'/workspace',is_workspace:true};
let _sidebarFileConfigScope='one::work';
const _sidebarFileConfig={folderScopes:[{path:'/repo',label:'Project',color:'#58a6ff'},
 {path:'/trees/feature',label:'Project/feature',kind:'worktree',projectPath:'/repo',color:'#d2a8ff'},
 {path:'/unused',label:'Unused'}],pinnedScopes:['/repo','/trees/feature']};
let termSessions=[],posts=[],attachments=[];
const _termSelectedScope=()=>({root:'/unused'});
const termSetStatus=()=>{},termSetAutoSpawnEnabled=async()=>{},_termClearDead=()=>{};
const _termSessionsKey=(w,v)=>v+'::'+w,_termInvalidateSessionReads=()=>{};
const _termSessionsCache=new Map();
const _termSaveHomeAssociation=()=>{};
const termAttach=(name,w)=>attachments.push({name,w});
const termRefreshSessions=async()=>{},termRefreshSessionsByWorkspaceId=async()=>{};
const CEREBRO_WORKSPACE_ID='__cerebro__',SELF_WORKSPACE_ID='__self__',ASSISTANT_WORKSPACE_ID='__assistant__';
window.fetch=async(url,options)=>{const body=JSON.parse(options.body);posts.push(body);
 return {ok:true,json:async()=>({name:'new'+posts.length,logical_name:'new'+posts.length,
  cwd:body.cwd,linked_scope:body.linked_scope})};};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const q=selector=>document.querySelector(selector);
const pick=i=>q(`[data-folder-choice="${i}"]`).click();
const cancelChoice=()=>q('.term-folder-footer [data-cancel]').click();
const open=()=>termSpawnSession('terminal',{startFresh:true});
'''
    helpers = _js_between('  async function _termChooseNewScope(', '  async function termKillCurrent(')
    checks = r'''
(async()=>{
 document.getElementById('new').focus();
 let pending=open();await tick();
 assert(!posts.length&&!attachments.length,'nothing starts before a choice');
 assert(q('[role=dialog]')&&q('#termFolderHint').textContent.includes('stays fixed'),'dialog announces fixed folder');
 assert(q('.term-folder-list').children.length===3,'workspace and pinned choices only');
 assert(document.activeElement===q('[data-folder-choice="0"]'),'initial keyboard focus is in chooser');
 assert(!q('[aria-selected=true]'),'no remembered selection');
 const dialog=q('[role=dialog]'),rect=dialog.getBoundingClientRect();
 assert(rect.left>=0&&rect.right<=innerWidth+1&&dialog.scrollWidth<=dialog.clientWidth+1,'dialog fits viewport');
 pick(2);await pending;
 assert(posts[0].cwd==='/trees/feature'&&posts[0].linked_scope.worktree==='/trees/feature','worktree chosen as exact launch folder');
 assert(document.activeElement===document.getElementById('new'),'focus returns to launch control');
 pending=open();await tick();cancelChoice();await pending;assert(posts.length===1,'cancel creates no session');
 pending=open();await tick();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 await pending;assert(posts.length===1&&!q('.term-folder-overlay'),'escape cancels');
 pending=open();await tick();
 q('.term-folder-footer button').focus();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));
 assert(document.activeElement===q('.fm-close'),'focus stays inside chooser');
 pick(0);await pending;assert(posts[1].cwd==='/workspace','workspace choice ignores selected sidebar folder');
 pending=open();await tick();vault='two';
 await pending;assert(posts.length===2&&!q('.term-folder-overlay'),'navigation cancels captured origin');
 vault='one';pending=open();await tick();
 // A second launch cancels the previous request without creating two terminals.
 const replacement=open();await tick();await pending;
 pick(1);await replacement;assert(posts.length===3&&posts[2].cwd==='/repo','each launch asks independently');
 _sidebarFileConfig.pinnedScopes=[];
 pending=open();await tick();assert(q('.term-folder-list').children.length===1,'even workspace-only launch asks');
 cancelChoice();await pending;
 // File-created terminals must ask too, and cannot silently use the file folder.
 _sidebarFileConfig.pinnedScopes=['/repo','/trees/feature'];
 pending=termSpawnSession('claude',{startFresh:true,agent:'codex',linkedScope:{root:'/file-folder'}});
 await tick();pick(1);await pending;assert(posts[3].cwd==='/repo'&&posts[3].agent==='codex','file launch uses explicit choice');
 document.body.classList.remove('workspace-active');
 pending=open();await pending;assert(posts[4].cwd==='/unused','other terminal surfaces keep their launch behavior');
 document.body.classList.add('workspace-active');
 open();await tick();
 document.getElementById('result').textContent='PASS choices, explicit launch, cancel, keyboard, navigation, repeated launch, agents, mobile';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    page = tmp_path / 'folder.html'
    css = (STATIC / 'css/lab-shell.css').read_text() + (STATIC / 'css/terminal-folder.css').read_text()
    page.write_text('<!doctype html><meta charset="utf-8"><style>' + css + '</style>'
                    '<body class="workspace-active"><button id="new">New terminal</button><pre id="result">PENDING</pre>'
                    '<script>' + setup + '</script><script>' + (STATIC / 'js/lib/terminal-folder.js').read_text()
                    + '</script><script>' + helpers + checks + '</script>')
    profile = tmp_path / 'chrome-profile'
    process = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
                                '--no-default-browser-check', '--allow-file-access-from-files',
                                '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(.05)
        driver = tmp_path / 'browser.mjs'
        driver.write_text((ROOT / 'scripts/chrome-dump-auth.mjs').read_text()
                          .replace('width: 1440,', 'width: ' + str(viewport) + ','))
        result = subprocess.run([node, str(driver), str(profile), page.as_uri(), str(tmp_path / 'dom.html'),
                                 str(tmp_path / 'folder.png')], capture_output=True, text=True, timeout=30,
                                env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        html = (tmp_path / 'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
    result = re.search(r'<pre id="result">(.*?)</pre>', html, re.S)
    assert result and result[1].startswith('PASS '), result[1] if result else html[-1500:]
