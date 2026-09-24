// Read-only validation of Git responses and decorations in the owned fixture.
export async function checkSidebarGitFixture(evaluate) {
  const expected=Number(process.env.LAB_PERF_GIT_CHANGES||0);
  if(!expected)return null;
  return evaluate(`(${inspect.toString()})(${JSON.stringify(expected)})`);
}

function inspect(expected) {
  const root=_sidebarScopedRoot(currentWorkspace.path);
  const files=_gitStatusByPath.get(root)?.files||{};
  const fixturePath=/^notes\/(?:batch-\d+\/)?entry-(\d+)\.[a-z0-9]+$/;
  const changed=Object.entries(files).filter(([path])=>fixturePath.test(path));
  const errors=[];
  if(changed.length!==expected || changed.some(([path,status])=>status!=='M'||Number(path.match(fixturePath)[1])>=expected))errors.push('Git response does not contain the expected modified fixture files');
  const paths=new Set();let modifiedRows=0,cleanRows=0;
  for(const row of document.querySelectorAll('#sidebar .sidebar-file[data-filepath]')) {
    if(row.dataset.entryRoot && row.dataset.entryRoot!==root)continue;
    const match=row.dataset.filepath.match(fixturePath);
    if(!match)continue;
    const badge=row.querySelector('.git-badge');
    if(Number(match[1])<expected) {
      modifiedRows++;paths.add(row.dataset.filepath);
      if(!row.classList.contains('git-m') || badge?.textContent!=='M' || badge.title!=='Modified')errors.push('Modified fixture row has missing or incorrect Git decoration: '+row.dataset.filepath);
    } else {
      cleanRows++;
      if(badge || ['git-m','git-a','git-u','git-d','git-r','git-ignored'].some(cls=>row.classList.contains(cls)))errors.push('Clean fixture row has a Git decoration: '+row.dataset.filepath);
    }
  }
  if(paths.size!==expected)errors.push('Modified fixture files are missing from the rendered sidebar');
  return {expectedChanges:expected,statusChanges:changed.length,modifiedPaths:paths.size,modifiedRows,cleanRows,errors};
}
