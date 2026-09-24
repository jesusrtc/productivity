import subprocess

from core.git_files import tracked_paths, tracked_subset


def test_subset_preserves_literal_paths_ignore_rules_and_subdirectories(tmp_path):
    def git(*args):
        subprocess.run(['git', '-C', str(tmp_path), *args], check=True, capture_output=True)
    git('init')
    (tmp_path / 'src').mkdir()
    names = ['space name.txt', 'line\nbreak.txt', '[literal].txt', 'ignored.txt', 'removed.txt']
    for name in names:
        (tmp_path / 'src' / name).write_text('fixture')
    git('add', '.')
    (tmp_path / '.gitignore').write_text('ignored.txt\n')
    git('rm', '--cached', 'src/removed.txt')
    (tmp_path / 'src/untracked.txt').touch()
    candidates = ['src/' + name for name in names + ['untracked.txt']]
    assert tracked_subset(tmp_path, candidates) == tracked_paths(tmp_path).intersection(candidates)
    assert tracked_subset(tmp_path / 'src', names) == tracked_paths(tmp_path / 'src').intersection(names)
    assert tracked_subset(tmp_path, []) == set()


def test_large_subset_falls_back_without_exceeding_argument_limits(tmp_path):
    subprocess.run(['git', '-C', str(tmp_path), 'init'], check=True, capture_output=True)
    for number in range(130):
        (tmp_path / str(number)).touch()
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True, capture_output=True)
    assert tracked_subset(tmp_path, [str(number) for number in range(140)]) == tracked_paths(tmp_path)
