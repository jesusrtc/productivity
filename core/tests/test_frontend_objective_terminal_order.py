"""Terminal task hierarchy wins over launch folders and incoming tab order."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


SOURCE = Path(__file__).resolve().parents[1] / 'src/core/static/js/lib/workspace-objectives.js'


def test_objective_terminals_follow_tasks_across_folders_and_reassignments():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    source = SOURCE.read_text()
    helpers = source[source.index('  function terminalIdentity('):source.index('  function openForTerminal(')]
    script = r'''
const assert=require('node:assert/strict');
const first={id:'one',name:'One',color:'#58a6ff',worktrees:[{id:'a',path:'/a',resolved_path:'/real-a',label:'A'},{id:'b',path:'/b',label:'B'}],tasks:[
  {id:'parent',title:'Parent',children:[{id:'child-one',title:'First child',children:[]},{id:'child-two',title:'Second child',children:[]}]},
  {id:'next',title:'Next task',children:[]}]};
const second={id:'two',name:'Two',color:'#bc8cff',worktrees:[{path:'/two',label:'Two folder'}],tasks:[{id:'other',title:'Other task',children:[]}]};
const registry={enabled:true,objectives:[first,second,{id:'parked',tasks:[],worktrees:[]}],focused:['one','two'],terminal_links:{}};
const context=()=>({path:'/workspace'}),active=()=>registry.enabled,data=()=>registry,objective=()=>first;
const tasks=o=>o?.tasks.flatMap(t=>[t,...t.children])||[],esc=value=>String(value),taskIcon=()=>'<icon>';
const session=(name,cwd='/a',assignment)=>{
  const t={name,session_id:'uuid-'+name,logical_name:'logical-'+name,cwd,label:name,agent_session_id:'kept'};
  if(assignment)registry.terminal_links[t.session_id]={objective_id:'one',...assignment};
  return t;
};
const sessions=[session('free'),session('child-two','/b',{task_id:'child-two'}),session('next','/a',{task_id:'next'}),
  session('asset','/b',{resource_id:'document'}),session('parent-second','/b',{task_id:'parent'}),
  session('whole','/real-a',{}),session('child-one','/a',{task_id:'child-one'}),
  session('parent-first','/a',{task_id:'parent'}),session('tasks-view','/b',{view:'tasks'}),
  session('missing-task','/a',{task_id:'removed'}),session('other-task','/two',{objective_id:'two',task_id:'other'}),
  session('other-free','/two'),session('parked','/b',{objective_id:'parked'})];
const original=JSON.stringify(sessions);
const names=()=>{
  let indices=[];
  const html=terminalHtml(sessions,(t,index)=>{indices.push(index);return '<tab>'+t.name+'</tab>';},'<new>');
  assert.deepEqual(indices,indices.map((_,index)=>index),'row numbers follow the displayed order');
  assert(html.endsWith('<new>'));
  return [...html.matchAll(/<tab>(.*?)<\/tab>/g)].map(match=>match[1]);
};
assert.deepEqual(names(),['whole','tasks-view','parent-second','parent-first','child-one','child-two','next','free','asset','missing-task','other-task','other-free']);
assert.equal(JSON.stringify(sessions),original,'sorting preserves session identity, launch folders and conversations');
assert.deepEqual(taskForTerminal(sessions[1]),{title:'Second child',icon:'<icon>'});
first.tasks[0].children.reverse();
assert.deepEqual(names().slice(0,7),['whole','tasks-view','parent-second','parent-first','child-two','child-one','next'],'new task ordering is reflected on every render');
registry.terminal_links['uuid-free']={objective_id:'one',task_id:'child-one'};
assert.deepEqual(names().slice(0,8),['whole','tasks-view','parent-second','parent-first','child-two','free','child-one','next'],'assigning a task promotes an unassigned session into its task group');
delete registry.terminal_links['uuid-parent-second'];
assert.deepEqual(names().slice(0,10),['whole','tasks-view','parent-first','child-two','free','child-one','next','asset','parent-second','missing-task'],'removing a task sends its session to the bottom');
first.tasks.reverse();
assert.deepEqual(names().slice(0,7),['whole','tasks-view','next','parent-first','child-two','free','child-one'],'parent task moves carry their children together');
sessions.unshift(session('new-child','/b',{task_id:'new-child'}));
assert(names().indexOf('new-child')>names().indexOf('parent-first'),'unknown task links stay at the bottom');
first.tasks[0].children.push({id:'new-child',title:'New subtask',children:[]});
assert.deepEqual(names().slice(0,8),['whole','tasks-view','next','new-child','parent-first','child-two','free','child-one'],'creating a subtask places its terminal directly below its parent');
registry.enabled=false;assert.equal(terminalHtml(sessions,()=>'', ''),null);
console.log(JSON.stringify({passed:true}));
'''
    result = subprocess.run([node, '-e', helpers + script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['passed']
