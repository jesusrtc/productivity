(function () {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const zone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  const labels = {day:'Daily',week:'Weekly',month:'Monthly',year:'Yearly'};
  function fields(task = {}) {
    const cycle = typeof task.recurrence === 'object' && task.recurrence || {};
    const minutes = cycle.reactivate_before_minutes ?? 1440;
    const divisor = minutes && minutes % 1440 === 0 ? 1440 : minutes && minutes % 60 === 0 ? 60 : 1;
    return `<div class="lab-task-schedule"><label>Due date<input name="due" type="date" value="${esc(task.due || '')}"></label><label>Repeat<select name="cycle_unit"><option value="">Once</option>${Object.entries(labels).map(([value,label]) => `<option value="${value}"${cycle.unit === value ? ' selected' : ''}>${label}</option>`).join('')}</select></label><div data-cycle-fields${cycle.unit ? '' : ' hidden'}><div class="lab-task-schedule-pair"><label>Every<input name="cycle_every" type="number" min="1" max="1000" value="${esc(cycle.every || 1)}" required><span data-cycle-unit-label>${esc((cycle.unit || 'week') + '(s)')}</span></label><label>Deadline time<input name="cycle_time" type="time" value="${esc(cycle.time || '23:59')}" required></label></div><label>Time zone<input name="cycle_timezone" value="${esc(cycle.timezone || zone())}" required placeholder="America/Los_Angeles"></label><div class="lab-task-schedule-pair"><label>Reactivate before deadline<input name="cycle_lead" type="number" min="0" max="525600" value="${minutes / divisor}" required></label><label>Unit<select name="cycle_lead_unit">${[[1,'Minutes'],[60,'Hours'],[1440,'Days']].map(([value,label]) => `<option value="${value}"${divisor === value ? ' selected' : ''}>${label}</option>`).join('')}</select></label></div><p class="lab-task-schedule-help">After completion, this task stays quiet until the reactivation window. Then it returns to Todo with its existing action items and subtasks unchecked. Unfinished overdue tasks keep their deadline. For daily work, choose a shorter window such as 1 hour to leave a quiet period.</p></div>${typeof task.recurrence === 'string' ? '<p class="lab-task-schedule-help">This task currently uses manual repeats. Saving a repeat here enables automatic reactivation.</p>' : ''}</div>`;
  }
  function bind(host) {
    const unit = host.querySelector('[name=cycle_unit]');
    if (!unit) return;
    let edited = !!unit.value;
    host.querySelector('[name=cycle_lead]').addEventListener('input', () => { edited = true; });
    const limitLead = () => { host.querySelector('[name=cycle_lead]').max = Math.floor(525600 / Number(host.querySelector('[name=cycle_lead_unit]').value)); };
    host.querySelector('[name=cycle_lead_unit]').addEventListener('change', () => { edited = true; limitLead(); });
    const update = () => {
      const enabled = !!unit.value;
      host.querySelector('[data-cycle-fields]').hidden = !enabled;
      host.querySelectorAll('[data-cycle-fields] input,[data-cycle-fields] select').forEach(input => { input.disabled = !enabled; });
      host.querySelector('[name=due]').required = enabled;
      host.querySelector('[data-cycle-unit-label]').textContent = unit.value + '(s)';
      if (!edited) {
        host.querySelector('[name=cycle_lead]').value = '1';
        host.querySelector('[name=cycle_lead_unit]').value = '1440';
      }
      limitLead();
    };
    unit.addEventListener('change', update); update();
  }
  function read(values) {
    const due = values.get('due') || null, unit = values.get('cycle_unit');
    if (!unit) return {due, recurrence:null};
    return {due, recurrence:{every:Number(values.get('cycle_every')), unit, time:values.get('cycle_time'), timezone:values.get('cycle_timezone').trim(), reactivate_before_minutes:Number(values.get('cycle_lead')) * Number(values.get('cycle_lead_unit'))}};
  }
  function checklist(body) {
    if (!window.marked?.lexer) return null;
    const result = {total:0,done:0,pending:0};
    function visit(tokens) {
      for (const token of tokens) {
        if (token.type === 'blockquote' || token.type === 'code') continue;
        if (token.type === 'list_item' && token.task) { result.total++; if (token.checked) result.done++; else result.pending++; }
        if (token.items) visit(token.items);
        if (token.tokens) visit(token.tokens);
      }
    }
    visit(marked.lexer(body));
    return result;
  }
  function badges(task, body) {
    const counts = body === undefined ? task.checklist : checklist(body) || task.checklist;
    const cycle = task.recurrence, state = task.recurrence_state;
    let repeat = '';
    if (cycle && typeof cycle === 'object') {
      const label = cycle.every === 1 ? labels[cycle.unit] : `Every ${cycle.every} ${cycle.unit}s`;
      const wake = state?.reactivate_at ? new Intl.DateTimeFormat(undefined, {timeZone:cycle.timezone,month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}).format(new Date(state.reactivate_at)) : '';
      repeat = `<span class="lab-task-repeat" title="${esc(wake ? 'Next due: ' + state.next_due + ' at ' + cycle.time + ' ' + cycle.timezone : 'Reactivates ' + cycle.reactivate_before_minutes + ' minutes before the next deadline after completion')}">↻ ${esc(label)}${wake ? ' · reopens ' + esc(wake) : ''}</span>`;
    }
    return (counts?.total ? `<span class="lab-task-checklist${counts.pending ? ' has-pending' : ''}" title="Required action items in the task’s Markdown">${counts.done} completed · ${counts.pending} pending</span>` : '') + repeat;
  }
  function edit(task, save) {
    const node = document.createElement('dialog'); node.className = 'lab-task-schedule-dialog';
    node.innerHTML = `<form><h2>Schedule · ${esc(task.title)}</h2>${fields(task)}<p role="alert" hidden></p><footer><button type="button" data-cancel>Cancel</button><button type="submit">Save</button></footer></form>`;
    document.body.append(node); bind(node); node.showModal();
    node.addEventListener('close', () => node.remove());
    node.querySelector('[data-cancel]').onclick = () => node.close();
    node.querySelector('form').onsubmit = async event => {
      event.preventDefault(); const button = node.querySelector('[type=submit]'); button.disabled = true;
      try { await save(read(new FormData(event.target))); node.close(); }
      catch (error) { const alert = node.querySelector('[role=alert]'); alert.hidden = false; alert.textContent = error.message; button.disabled = false; }
    };
  }
  window.LabTaskSchedule = {fields,bind,read,badges,checklist,edit};
})();
