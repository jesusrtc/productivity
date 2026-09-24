// Original vector geometry and inline rendering retained for visual regression checks.
// Snapshot: a54295a; formerly shared MD/Python/SQL/JSON graphics expanded inline.
const legacyFileIconHtml = (() => {
  const _FT_FONT = "-apple-system,'Segoe UI',Roboto,sans-serif";
  const _ftDoc = (stroke) => `<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="${stroke}" stroke-width="1.2"><path d="M4 1.5h5.5L13 5v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2.5a1 1 0 0 1 1-1z"/><path d="M9.5 1.5V5H13"/></svg>`;
  const _ftBadge = (bg, label, fg) => `<svg viewBox="0 0 16 16" width="14" height="14"><rect width="16" height="16" rx="3" fill="${bg}"/><text x="8" y="11.8" text-anchor="middle" font-size="8.5" font-weight="700" font-family="${_FT_FONT}" fill="${fg}">${label}</text></svg>`;
  const _ftText = (label, color, size) => `<svg viewBox="0 0 16 16" width="14" height="14"><text x="8" y="12" text-anchor="middle" font-size="${size || 10}" font-weight="700" font-family="${_FT_FONT}" fill="${color}">${label}</text></svg>`;
  const _FT_SVGS = {
    // Jupyter: orange top/bottom crescents plus the two grey moons.
    ipynb: '<svg viewBox="0 0 16 16" width="14" height="14"><path fill="#F37726" d="M8 12.1c-2.1 0-3.9-.9-5-2.2a5.4 5.4 0 0 0 10 0c-1.1 1.3-2.9 2.2-5 2.2zM8 3.9c2.1 0 3.9.9 5 2.2a5.4 5.4 0 0 0-10 0c1.1-1.3 2.9-2.2 5-2.2z"/><circle cx="13" cy="13.2" r="1" fill="#989798"/><circle cx="2.8" cy="2.6" r=".8" fill="#6f7070"/></svg>',
    sh: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="1" y="2.2" width="14" height="11.6" rx="1.8" stroke="#4EAA25" stroke-width="1.1"/><path d="M3.8 6l2.1 2-2.1 2M8.4 10.4h3.4" stroke="#4EAA25" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    csv: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#8BC34A" stroke-width="1.1"><rect x="1.5" y="2.5" width="13" height="11" rx="1"/><path d="M1.5 6h13M1.5 9.5h13M6 2.5v11M10.5 2.5v11"/></svg>',
    // Scala: the language's three stacked red ribbon forms.
    scala: '<svg viewBox="0 0 16 16" width="14" height="14"><path fill="#DE3423" d="M3 1.5c3.4 1 6.5-.1 10-1v4.1c-3.3.9-6.6 2-10 1V1.5zm0 5.1c3.4 1 6.5-.1 10-1v4.1c-3.3.9-6.6 2-10 1V6.6zm0 5.1c3.4 1 6.5-.1 10-1v4.1c-3.3.9-6.6 2-10 1v-4.1z"/></svg>',
    git: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#F05033" stroke-width="1.2"><circle cx="4.5" cy="3.8" r="1.5"/><circle cx="4.5" cy="12.2" r="1.5"/><circle cx="11.5" cy="8" r="1.5"/><path d="M4.5 5.3v5.4M6 8h4" stroke-linecap="round"/></svg>',
    vid: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#A074C4" stroke-width="1.2"><rect x="1.5" y="3" width="13" height="10" rx="1.5"/><path d="M6.5 6l3.5 2-3.5 2z" fill="#A074C4" stroke="none"/></svg>',
    conf: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#A074C4" stroke-width="1.2" stroke-linecap="round"><path d="M2.5 5.2h11M2.5 10.8h11"/><circle cx="6.2" cy="5.2" r="1.5" fill="var(--bg-primary,#111)"/><circle cx="10" cy="10.8" r="1.5" fill="var(--bg-primary,#111)"/></svg>',
    img: '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2" y="3" width="12" height="10" rx="1"/><circle cx="5.5" cy="6.5" r="1" fill="currentColor" stroke="none"/><path d="M2.5 11.5l3-2.8 2.8 2.3 2.7-2.5 2.5 2.5"/></svg>',
  };
  function fileIconHtml(name, node) {
    const base = String(name || '').split('/').pop();
    const lower = base.toLowerCase();
    const ext = lower.includes('.') ? lower.slice(lower.lastIndexOf('.') + 1) : '';
    let cls, glyph;
    if ((node && node.type === 'image') || ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'bmp'].includes(ext)) { cls = 'ft-img'; glyph = _FT_SVGS.img; }
    else if (['mp4', 'webm', 'mov', 'm4v'].includes(ext)) { cls = 'ft-vid'; glyph = _FT_SVGS.vid; }
    else if (ext === 'ipynb') { cls = 'ft-nb'; glyph = _FT_SVGS.ipynb; }
    else if (ext === 'md' || ext === 'markdown' || ext === 'rst') { cls = 'ft-md'; glyph = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 16 16\" width=\"14\" height=\"14\" fill=\"none\" stroke=\"#519ABA\" stroke-width=\"1.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><rect x=\"1\" y=\"3.2\" width=\"14\" height=\"9.6\" rx=\"1.5\"/><path d=\"M3.4 10.3V5.7l1.9 2.2 1.9-2.2v4.6\"/><path d=\"M11.6 5.9v3M10.2 7.6l1.4 1.7 1.4-1.7\"/></svg>"; }
    else if (ext === 'py') { cls = 'ft-py'; glyph = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" width=\"14\" height=\"14\"><path fill=\"#3776AB\" d=\"M11.9 2c-5 0-4.6 2.2-4.6 2.2v2.3h4.7v.7H5.3S2 6.8 2 11.9c0 5 2.9 4.9 2.9 4.9h1.7v-2.4s-.1-2.9 2.8-2.9h4.7s2.7.1 2.7-2.6V4.7S17.2 2 11.9 2zM9.3 3.4a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8z\"/><path fill=\"#FFD43B\" d=\"M12.1 22c5 0 4.6-2.2 4.6-2.2v-2.3H12v-.7h6.7s3.3.4 3.3-4.7c0-5-2.9-4.9-2.9-4.9h-1.7v2.4s.1 2.9-2.8 2.9h-4.7s-2.7-.1-2.7 2.6v4.2S6.8 22 12.1 22zm2.6-1.4a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8z\"/></svg>"; }
    else if (['js', 'mjs', 'cjs', 'jsx'].includes(ext)) { cls = 'ft-js'; glyph = _ftBadge('#F7DF1E', 'JS', '#222'); }
    else if (ext === 'ts' || ext === 'tsx') { cls = 'ft-ts'; glyph = _ftBadge('#3178C6', 'TS', '#fff'); }
    else if (ext === 'json' || ext === 'lock') { cls = 'ft-json'; glyph = _ftText('{}', '#CBCB41'); }
    else if (['toml', 'yaml', 'yml', 'ini', 'cfg'].includes(ext)) { cls = 'ft-json'; glyph = _FT_SVGS.conf; }
    else if (['html', 'htm', 'xml'].includes(ext)) { cls = 'ft-html'; glyph = _ftText('&lt;&gt;', '#E44D26', 9); }
    else if (['css', 'scss', 'less'].includes(ext)) { cls = 'ft-css'; glyph = _ftText('#', '#2965F1', 11); }
    else if (['sh', 'bash', 'zsh', 'fish'].includes(ext) || lower === 'makefile' || lower === 'dockerfile') { cls = 'ft-sh'; glyph = _FT_SVGS.sh; }
    else if (ext === 'pdf') { cls = 'ft-pdf'; glyph = _ftDoc('#E5252A'); }
    else if (ext === 'sql') { cls = 'ft-sql'; glyph = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 16 16\" width=\"14\" height=\"14\" fill=\"none\"><path d=\"M2 4v8c0 1.1 2.7 2 6 2s6-.9 6-2V4\" fill=\"#4479A1\"/><ellipse cx=\"8\" cy=\"4\" rx=\"6\" ry=\"2.3\" fill=\"#69A7D0\"/><path d=\"M2 8c0 1.1 2.7 2 6 2s6-.9 6-2M2 11c0 1.1 2.7 2 6 2s6-.9 6-2\" stroke=\"#C7E9FF\" stroke-width=\".9\"/></svg>"; }
    else if (ext === 'scala') { cls = 'ft-scala'; glyph = _FT_SVGS.scala; }
    else if (['csv', 'tsv', 'parquet'].includes(ext)) { cls = 'ft-csv'; glyph = _FT_SVGS.csv; }
    else if (lower.startsWith('.git')) { cls = 'ft-git'; glyph = _FT_SVGS.git; }
    else { cls = 'ft-generic'; glyph = _ftDoc('currentColor'); }
    const ln = node && node.is_symlink ? ' ft-ln' : '';
    return `<span class="ft-icon ${cls}${ln}" aria-hidden="true">${glyph}</span>`;
  }

return fileIconHtml;
})();
