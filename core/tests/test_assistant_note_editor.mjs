import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const elements = new Map();
function element() {
  const classes = new Set();
  return {hidden:false, disabled:false, textContent:'', classList:{toggle:(name, on) => on ? classes.add(name) : classes.delete(name), contains:name => classes.has(name)}, setAttribute() {}};
}
const listeners = {};
const window = {addEventListener:(name, fn) => listeners[name] = fn};
const document = {addEventListener() {}, querySelectorAll:() => [], getElementById:id => {
  if (!elements.has(id)) elements.set(id, element());
  return elements.get(id);
}};
const context = vm.createContext({window, document, console, URL, setTimeout, clearTimeout});
let source = fs.readFileSync(new URL('../src/core/static/js/views/assistant.js', import.meta.url), 'utf8');
// Expose private helpers only in this isolated unit harness. Rendering and polling
// are collaborators; no browser, production server or user data is touched.
source = source.replace('  window.AssistantView = {', `
  window.noteTest = {state, noteLineChanges, markNoteChanges, noteDraft, noteDraftKey, renderNoteControls, saveNoteContent};
  renderModal = async () => { window.rendered = (window.rendered || 0) + 1; };
  refresh = async () => {};
  window.AssistantView = {`);
vm.runInContext(source, context);
const {state, noteLineChanges:diff, markNoteChanges:mark, noteDraft, noteDraftKey, renderNoteControls:controls, saveNoteContent:save} = window.noteTest;
const lines = set => [...set];
assert.deepEqual(lines(diff('one\ntwo\nthree', 'one\nnew\nthree').changed), [1]);
assert.deepEqual(lines(diff('one\ntwo', 'zero\none\ntwo').changed), [0]);
assert.deepEqual(lines(diff('one\ntwo', 'one\ntwo').changed), []);
let result = diff('one\ntwo\nthree', 'one\nthree');
assert.equal(result.removed, 1);
assert.deepEqual(lines(result.changed), []);
assert.deepEqual(lines(result.deleted), [1]);
result = diff('one\ntwo\nthree\nfour\nfive', 'ONE\ntwo\nthree\nfour\nFIVE');
assert.deepEqual(lines(result.changed), [0, 4]);
assert.deepEqual(lines(diff('a\nb\na', 'a\na').changed), []);
assert.deepEqual(lines(diff('', 'first').changed), [0]);
assert.deepEqual(lines(diff('hello', '').changed), [0]);
assert.equal(diff(Array(1500).fill('a').join('\n'), Array(1500).fill('b').join('\n')).changed.size, 1500);

state.data = {root:'/example/assistant'};
const detail = {path:'notes/note.md#tab=child', metadata:{schema:2, type:'note'}, body:'Original'};
state.modalCurrent = detail; state.modalRoot = detail;
const draft = {path:detail.path, base:detail.body, body:'Changed <script>bad()</script>', marks:{}, input:{}, editing:true};
state.noteDrafts.set(noteDraftKey(detail.path), draft);
mark(draft); controls(detail, 'note');
assert.equal(elements.get('assistantSaveNote').disabled, false);
assert.equal(elements.get('assistantNoteStatus').hidden, false);
assert.ok(draft.marks.innerHTML.includes('&lt;script&gt;'));
assert.ok(!draft.marks.innerHTML.includes('<script>'));
const a = noteDraft(); state.modalCurrent = {path:'notes/other.md'};
assert.equal(noteDraft(), undefined);
state.modalCurrent = detail; assert.equal(noteDraft(), a);
state.data.root = '/another/assistant'; assert.equal(noteDraft(), undefined);
state.data.root = '/example/assistant';
let warned = false;
listeners.beforeunload({preventDefault:() => warned = true});
assert.equal(warned, true);

let sent;
context.fetch = async (url, options) => {
  sent = JSON.parse(options.body);
  return {ok:false, json:async () => ({detail:'This note changed elsewhere.'})};
};
await save(detail, 'note');
assert.equal(sent.expected, 'Original');
assert.equal(sent.path, detail.path);
assert.equal(draft.body, 'Changed <script>bad()</script>');
assert.equal(draft.base, 'Original');
assert.equal(draft.saving, false);
assert.equal(draft.input.readOnly, false);
assert.ok(elements.get('assistantNoteStatus').textContent.includes('changed elsewhere'));
assert.equal(elements.get('assistantSaveNote').disabled, false);

context.fetch = async () => { throw new Error('Network unavailable'); };
await save(detail, 'note');
assert.equal(draft.base, 'Original');
assert.equal(draft.error, 'Network unavailable');

let release;
context.fetch = () => new Promise(resolve => release = resolve);
const pending = save(detail, 'note');
assert.equal(draft.saving, true);
assert.equal(elements.get('assistantSaveNote').disabled, true);
const next = {path:'notes/other.md', metadata:{schema:2, type:'note'}, body:'Other'};
state.modalRequest++; state.modalCurrent = next;
release({ok:true, json:async () => ({...detail, body:draft.body})});
await pending;
assert.equal(state.modalCurrent, next, 'Late save must not navigate back');
assert.equal(window.rendered || 0, 0);
assert.equal(draft.base, draft.body);
assert.ok(!draft.marks.innerHTML.includes('class="note-line-changed'));
state.modalCurrent = detail; controls(detail, 'note');
assert.equal(elements.get('assistantSaveNote').disabled, true);
assert.equal(elements.get('assistantNoteStatus').textContent, 'Saved');
warned = false;
listeners.beforeunload({preventDefault:() => warned = true});
assert.equal(warned, false);
controls({metadata:{schema:2, type:'note'}, format:'text'}, 'content');
assert.equal(elements.get('assistantEditNote').hidden, true);
console.log('Draft state, stale saves, errors, line markers and original protection passed.');
