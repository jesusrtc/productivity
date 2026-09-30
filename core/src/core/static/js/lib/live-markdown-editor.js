/* Markdown remains the editable source; inactive blocks render in place. */
import {EditorState, StateEffect, StateField} from '@codemirror/state';
import {Decoration, EditorView, WidgetType, keymap} from '@codemirror/view';
import {defaultKeymap, history, historyKeymap} from '@codemirror/commands';
import {markdown} from '@codemirror/lang-markdown';
import {defaultHighlightStyle, syntaxHighlighting} from '@codemirror/language';

const focused = StateEffect.define();
const focusState = StateField.define({
  create: () => false,
  update(value, transaction) {
    for (const effect of transaction.effects) if (effect.is(focused)) value = effect.value;
    return value;
  },
});

class RenderedMarkdown extends WidgetType {
  constructor(source, from, definitions, prepare) { super(); Object.assign(this, {source, from, definitions, prepare}); }
  eq(other) { return this.source === other.source && this.from === other.from && this.definitions === other.definitions; }
  toDOM(view) {
    const block = document.createElement('div');
    block.className = 'lab-live-markdown-block assistant-markdown';
    block.innerHTML = window.LabMarkdown.render(this.source + this.definitions);
    this.prepare?.(block);
    block.addEventListener('mousedown', event => {
      if (event.button !== 0 || event.target.closest('button, summary') || (event.metaKey || event.ctrlKey) && event.target.closest('a')) return;
      event.preventDefault();
      const anchor = event.shiftKey ? view.state.selection.main.anchor : this.from;
      view.dispatch({selection:{anchor, head:this.from}, effects:focused.of(true)});
      view.focus();
      // Once source is exposed, place the caret close to the clicked text.
      view.requestMeasure({read: () => view.posAtCoords({x:event.clientX, y:event.clientY}), write: position => {
        if (position != null && position >= this.from && position <= this.from + this.source.length) {
          view.dispatch({selection:{anchor:event.shiftKey ? anchor : position, head:position}});
        }
      }});
    });
    return block;
  }
  ignoreEvent() { return true; }
}

function previewDecorations(state, prepare) {
  const body = state.doc.toString(), decorations = [];
  const tokens = window.marked.lexer(body);
  const definitions = '\n\n' + Object.entries(tokens.links || {}).map(([label, link]) =>
    `[${label}]: <${link.href}>${link.title ? ' "' + link.title.replace(/"/g, '\\"') + '"' : ''}`).join('\n');
  let offset = 0;
  for (let index = 0; index < tokens.length; index++) {
    const token = tokens[index];
    let raw = token.raw;
    // Disclosure bodies must be sanitized/rendered together with their tags.
    if (token.type === 'html' && /^\s*<details\b/i.test(raw) && !/<\/details>/i.test(raw)) {
      let depth = (raw.match(/<details\b/gi) || []).length - (raw.match(/<\/details>/gi) || []).length;
      while (depth > 0 && index + 1 < tokens.length) {
        const next = tokens[++index].raw; raw += next;
        depth += (next.match(/<details\b/gi) || []).length - (next.match(/<\/details>/gi) || []).length;
      }
    }
    const from = body.indexOf(raw, offset);
    if (from < 0) continue;
    const to = from + raw.replace(/\n+$/, '').length;
    offset = from + raw.length;
    if (token.type === 'space' || to <= from) continue;
    const selected = state.field(focusState) && state.selection.ranges.some(range => range.from <= to && range.to >= from);
    if (!selected) {
      decorations.push(Decoration.replace({block:true, widget:new RenderedMarkdown(raw, from, definitions, prepare)}).range(from, to));
    } else if (/^#{1,6} /.test(raw)) {
      const level = raw.match(/^#+/)[0].length;
      decorations.push(Decoration.line({class:'lab-live-heading lab-live-heading-' + level}).range(from));
    }
  }
  return Decoration.set(decorations, true);
}

window.LabMarkdownEditor = {
  create(parent, {body, onChange, onSave, prepare}) {
    const preview = StateField.define({
      create: state => previewDecorations(state, prepare),
      update: (value, transaction) => transaction.docChanged || transaction.selection || transaction.effects.some(effect => effect.is(focused))
        ? previewDecorations(transaction.state, prepare) : value,
      provide: field => EditorView.decorations.from(field),
    });
    const view = new EditorView({parent, state:EditorState.create({doc:body, extensions:[
      focusState, preview, markdown(), history(), syntaxHighlighting(defaultHighlightStyle), EditorView.lineWrapping,
      EditorView.contentAttributes.of({'aria-label':'Current tab Markdown', spellcheck:'true'}),
      keymap.of([{key:'Mod-s', run:() => { onSave(); return true; }}, ...defaultKeymap, ...historyKeymap]),
      EditorView.updateListener.of(update => { if (update.docChanged) onChange(update.state.doc.toString()); }),
      EditorView.domEventHandlers({
        focus:(_event, editor) => { queueMicrotask(() => { if (!editor.state.field(focusState)) editor.dispatch({effects:focused.of(true)}); }); },
        blur:(_event, editor) => { queueMicrotask(() => { if (!editor.hasFocus) editor.dispatch({effects:focused.of(false)}); }); },
      }),
    ]})});
    return {
      view,
      get value() { return view.state.doc.toString(); },
      set value(value) { if (value !== view.state.doc.toString()) view.dispatch({changes:{from:0,to:view.state.doc.length,insert:value}}); },
      focus:() => view.focus(),
      destroy:() => view.destroy(),
    };
  },
};
