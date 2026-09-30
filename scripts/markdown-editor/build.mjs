import {createRequire} from 'node:module';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

// npm ci && npm run build; an optional directory reuses a temporary install.
const here = dirname(fileURLToPath(import.meta.url));
const packages = resolve(process.argv[2] || here);
const require = createRequire(resolve(packages, 'package.json'));
const {build} = require('esbuild');
const output = resolve(here, '../../core/src/core/static/vendor/lab-markdown-editor');
await mkdir(output, {recursive:true});
await build({
  entryPoints:[resolve(here, '../../core/src/core/static/js/lib/live-markdown-editor.js')],
  outfile:resolve(output,'markdown-editor.min.js'), nodePaths:[resolve(packages,'node_modules')],
  bundle:true, minify:true, format:'iife', target:'es2022', legalComments:'inline',
});
const lock = JSON.parse(await readFile(resolve(packages, 'package-lock.json'),'utf8'));
const licenses = [];
for (const [path, info] of Object.entries(lock.packages)) {
  if (!path || path.includes('esbuild')) continue;
  for (const filename of ['LICENSE', 'LICENSE.txt', 'LICENSE.md']) {
    try { licenses.push(`${path} ${info.version}\n${await readFile(resolve(packages,path,filename),'utf8')}`); break; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}
await writeFile(resolve(output,'LICENSE'), licenses.join('\n\n'));
