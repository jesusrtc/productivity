# Objective links use native service icons

The user wants Objective Links to look like the existing workspace link rows:
compact content-sized pills, one link per row, with recognizable service icons.
Use `LabScopeLinks.icon` so actual URLs determine the locally bundled icons and
global Links and icons domain mappings apply. Changes to those mappings repaint
Objective rows immediately. Long labels truncate at the available sidebar width;
document and notebook resources retain their own icons.
