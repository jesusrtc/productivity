"""Compare the disclosure fast path with the previous parser, using vendored Marked."""
from .test_frontend_logging import _run_node


def test_optional_disclosure_parser_preserves_output_options_and_errors():
    result = _run_node(r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const marked=fs.readFileSync('core/src/core/static/vendor/marked@12.0.1/marked.min.js','utf8');
const source=fs.readFileSync('core/src/core/static/js/lib/markdown-content.js','utf8');
function runtime(forceDisclosure) {
  const calls={starts:0,plain:0,disclosure:0};
  // DOM processing is identical for both paths; the real Chrome copy test
  // separately covers sanitizing, highlighting, code controls and disclosures.
  const context={document:{addEventListener(){},createElement(){return{innerHTML:'',querySelectorAll(){return[];}};}},DOMPurify:{sanitize:html=>html}};
  context.window=context;vm.createContext(context);vm.runInContext(marked,context);
  const Marked=context.marked.Marked;
  context.marked.Marked=class extends Marked {
    constructor(...args) {
      const options=args[0];
      const extension=options?.extensions?.[0];
      if(extension){calls.disclosure++;const start=extension.start;extension.start=function(...args){calls.starts++;return start.apply(this,args);};}
      else calls.plain++;
      super(...args);
    }
  };
  // Force the previous always-enabled extension without copying its tokenizer.
  const script=forceDisclosure?source.replace(/const hasDisclosure = [\s\S]*?;/,'const hasDisclosure = true;'):source;
  assert(!forceDisclosure || script!==source);
  vm.runInContext(script,context);
  return{context,calls,render:context.LabMarkdown.render};
}
const candidate=runtime(false),reference=runtime(true);
const corpus=[
  '', '# Heading\n\n**Bold** and `code` & text < literal.\n',
  '> Quote\n>\n> - List\n> - Second\n\n---\n',
  '| A | B |\n|---|---|\n| C | D |\n\n![alt](images/a.png "title")\n',
  '```sql\nSELECT 1;\n```\n\n    indented\n',
  '<div class="box">\n\n## In HTML\n\n</div>',
  '[a]: https://example.com\n\n[a] and <https://example.org>',
  'text\n<details open><summary>Title</summary>\n## Inside\n\nText\n</details>\n',
  '<DETAILS OPEN>\n<SUMMARY>Mixed case</SUMMARY>\n```sql\nSELECT 2;\n```\n</DETAILS>',
  '   <details>\n<summary title="a > b">Title</summary>\nText\n</details>',
  '<details><summary>Outer</summary>\n<details open><summary>Inner</summary>\ntext\n</details>\n</details>',
  '> <details><summary>Quote</summary>\n> text\n> </details>',
  '- <details><summary>List</summary>\n  text\n  </details>',
  '```md\n<details><summary>Literal</summary>\n</details>\n```',
  '    <details><summary>Indented literal</summary>',
  '`<summary>` and &lt;details&gt;\n',
  '<!-- <details -->\n\nParagraph.',
  '<details-not-a-disclosure>\n\ntext', '<summary>Incomplete',
  '</details>\n\n</summary>', '<detailsish>\n\n<summaryOther>',
  '<script>"<details";</script>\n\nSafe after sanitizing.',
];
for(const text of corpus)assert.equal(candidate.render(text),reference.render(text),text);
for(const runtime of [candidate,reference]) {
  runtime.imageOptions=()=>{
    const renderer=new runtime.context.marked.Renderer();
    renderer.image=(href,title,text)=>`<img src="/scoped/${href}" alt="${text}" title="${title||''}">`;
    return{renderer,breaks:true};
  };
}
for(const text of ['![A](one.png)\nnext', '<details><summary>X</summary>\n![B](two.png)\nnext\n</details>', '![C](three.png)\nnext']) {
  assert.equal(candidate.render(text,candidate.imageOptions()),reference.render(text,reference.imageOptions()));
  assert.equal(candidate.render(text),reference.render(text),'per-call options must not leak');
}
for(const value of [null,undefined,42,{},[]]) {
  const errors=[];
  for(const runtime of [candidate,reference]){try{runtime.render(value);errors.push(null);}catch(error){errors.push(error.message);}}
  assert.equal(errors[0],errors[1]);assert(errors[0]);
}
function hookOptions(runtime) {
  const hooks=new runtime.context.marked.Hooks();
  hooks.preprocess=text=>`<details open><summary>Generated</summary>\n${text}\n</details>`;
  return{hooks};
}
assert.equal(candidate.render('### Generated heading\n\n**Body**',hookOptions(candidate)),reference.render('### Generated heading\n\n**Body**',hookOptions(reference)));
const large=Array.from({length:1500},(_,i)=>`## Section ${i}\n\nParagraph **bold** and \`code\`.\n`).join('\n');
candidate.calls.starts=reference.calls.starts=0;
assert.equal(candidate.render(large),reference.render(large));
process.stdout.write(JSON.stringify({cases:corpus.length,largeStarts:{candidate:candidate.calls.starts,reference:reference.calls.starts},parsers:{plain:candidate.calls.plain,disclosure:candidate.calls.disclosure}}));
''')
    assert result['cases'] >= 20
    assert result['largeStarts'] == {'candidate': 0, 'reference': 1500}
    assert result['parsers'] == {'plain': 1, 'disclosure': 1}
