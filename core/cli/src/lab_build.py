"""Ship the canonical framework docs in both wheels and source distributions."""
from pathlib import Path
import shutil

from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

NAMES = ('USER-GUIDE.md', 'CHANGELOG.md')


def docs_dir():
    project = Path(__file__).resolve().parents[1]
    checkout = project.parent.parent
    if project == checkout / 'core/cli' and all((checkout / 'docs' / name).is_file() for name in NAMES):
        return checkout / 'docs'
    return project / 'src/lab/resources/docs'


def copy_docs(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        shutil.copyfile(docs_dir() / name, destination / name)


class BuildPy(build_py):
    def run(self):
        super().run()
        copy_docs(Path(self.build_lib) / 'lab/resources/docs')

    def get_outputs(self, include_bytecode=1):
        return super().get_outputs(include_bytecode) + [str(Path(self.build_lib) / 'lab/resources/docs' / name) for name in NAMES]


class Sdist(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        copy_docs(Path(base_dir) / 'src/lab/resources/docs')
