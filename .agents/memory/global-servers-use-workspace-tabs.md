# Servers is a global workspace-tabbed control

The user requested Servers in the global top bar beside Logs, with tabs for all
known workspaces across registered vaults and the current workspace selected on
each opening. Tab selection stays independent of main workspace navigation.
Read, save, create-template and lifecycle actions use the selected workspace's
stable ID and owning vault. Keep empty workspaces available, guard late reads,
disable writes after failed reads, and protect unsaved edits on tab switches.
The former workspace server strip is removed, including its extra layout offset.
Continue using standalone servers.json and explicit make lifecycle commands.
