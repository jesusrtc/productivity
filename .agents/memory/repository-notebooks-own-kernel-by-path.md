# Repository notebooks own their kernel by path

The durable notebook is the `.ipynb` at the user-selected location inside the active workspace repository. Lab writes cells and outputs back to that file; it does not relocate notebooks into server storage. Kernel identity is derived from the workspace-relative notebook path, so the same path shares state between humans and agents while different `.ipynb` paths get different sessions. The Files sidebar's **+ Notebook** flow must expose the destination folder and create valid nbformat JSON.
