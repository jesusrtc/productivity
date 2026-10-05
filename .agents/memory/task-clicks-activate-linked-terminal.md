# Task clicks activate their linked terminal

The user wants clicking an Objective task or subtask to reveal and activate
its linked terminal while keeping its task details open. Each terminal can
link to only one task/subtask at a time. Reassignment replaces its old target,
including across Objectives; never create another process or change its
launch folder merely to select or relink it.

A task can have several terminals. Preserve the currently selected terminal
if it belongs to that task; otherwise activate the first available linked
session. A task without a linked terminal leaves terminal selection alone.
Terminal-originated document navigation must not recursively activate itself.
