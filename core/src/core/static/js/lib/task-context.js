/* Task and Objective drags carry readable context and exact source references. */
(() => {
  'use strict';
  const mime = 'application/x-lab-task-context';
  const line = value => String(value ?? '').replace(/[\x00-\x1f\x7f]/g, ' ').trim();
  const quoted = value => JSON.stringify(line(value));
  function validReference(value) {
    if(typeof value!=='string'||!value||/[\x00-\x1f\x7f]/.test(value))return false;
    if(value.startsWith('/'))return true;
    try{return ['http:','https:'].includes(new URL(value).protocol);}catch{return false;}
  }
  function groups(context) {
    const whole=context?.kind==='objective';
    if(context?.version!==1||!line(context.objective?.title)
        ||(whole?(!Array.isArray(context.tasks)||!Array.isArray(context.assets)||!context.objective.assets?.length):
          (!line(context.task?.title)||!Array.isArray(context.parents)||!context.task.assets?.length)))throw new Error('Incomplete context');
    const rows=whole?[context.objective,...context.tasks,{title:'Unassigned assets',assets:context.unassigned_assets||[]},{title:'All Objective assets',assets:context.assets}]:[context.objective,...context.parents,context.task];
    if(rows.some(row=>!line(row.title)||!Array.isArray(row.assets)
        ||row.assets.some(asset=>!line(asset.title)||!line(asset.type)||!validReference(asset.reference))))
      throw new Error('Invalid context reference');
    return rows;
  }
  function references(context) {return [...new Set(groups(context).flatMap(group=>group.assets.map(asset=>asset.reference)))];}
  function format(context) {
    groups(context);
    const seen=new Map(),output=['Context:','Objective: '+quoted(context.objective.title)];
    if(line(context.objective.purpose))output.push('Objective outcome: '+line(context.objective.purpose));
    function assets(rows) {
      const local=new Set();
      for(const asset of rows){
        if(local.has(asset.reference))continue;local.add(asset.reference);
        const previous=seen.get(asset.reference),id=previous||seen.size+1;
        output.push('- [R'+id+'] '+line(asset.type)+': '+quoted(asset.title)
          +(previous?' (same reference as above).':' — '+asset.reference));
        seen.set(asset.reference,id);
      }
      if(!rows.length)output.push('- No associated references.');
    }
    if(context.kind==='objective'){
      const index=context.objective.assets.filter(asset=>['Objective manifest','Objective folder'].includes(asset.type));
      output.push('','This objective: '+quoted(context.objective.title),'Objective index:');assets(index);
      output.push('','Global assets (shared across tasks):');assets(context.objective.assets.filter(asset=>!index.includes(asset)));
      for(const task of context.tasks){output.push('',(line(task.parent)?'Subtask of '+quoted(task.parent)+': ':'Task: ')+quoted(task.title),'Task assets and specification:');assets(task.assets);}
      output.push('','Unassigned assets:');assets(context.unassigned_assets||[]);
      output.push('','Asset index by type:');
      const byType=new Map();
      for(const asset of context.assets){if(!byType.has(asset.type))byType.set(asset.type,[]);byType.get(asset.type).push(asset);}
      for(const [type,rows] of byType){output.push(line(type)+':');assets(rows);}
      if(!byType.size)output.push('- No other assets.');
      output.push('','Instructions:',
        'Work on This objective: '+quoted(context.objective.title)+'. Read its Objective manifest and relevant task specifications before making changes.',
        'Use the references above for the whole Objective, including its tasks and subtasks. Preserve exact document tabs, sublinks and original source ownership.',
        'Keep changes within this Objective and its explicitly linked worktrees or folders. Other objectives and unrelated workspace files are outside this scope.');
      return output.join('\n');
    }
    output.push('Shared objective references (background):');assets(context.objective.assets);
    for(const parent of context.parents){output.push('','Parent task: '+quoted(parent.title),'Parent task references (background):');assets(parent.assets);}
    output.push('','This task: '+quoted(context.task.title),'Current task references:');assets(context.task.assets);
    output.push('','Instructions:',
      'Work only on This task: '+quoted(context.task.title)+'. Read its task specification before making changes.',
      'Objective and parent-task references are background context and read-only unless also listed under This task.',
      'Limit changes to the current task references and files within its explicitly linked worktrees or folders. Preserve exact document tabs and sublinks; do not change parent or sibling task specifications, other tasks, or unrelated assets.',
      'If this task requires changes outside those references, ask before expanding the scope.');
    return output.join('\n');
  }
  window.LabTaskContext={mime,references,format};
})();
