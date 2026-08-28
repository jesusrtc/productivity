# Preserve selected venv Python paths

When resolving a project notebook runtime's Python executable, normalize it to
an absolute path but do not call `Path.resolve()` on it. Virtualenv Python
binaries are often symlinks to a system interpreter; resolving the symlink
prevents Python from finding the venv's `pyvenv.cfg`, installed `ipykernel`, and
client libraries. Jupyter kernelspec `argv[0]` must retain the selected venv
path verbatim.
