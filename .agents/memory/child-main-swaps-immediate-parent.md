# Set as main swaps with the immediate parent

The user corrected Set as main on October 7, 2026: a nested child must swap only
with its immediate parent, keeping grandparent and higher ancestor rows in
place. Preserve the actual hierarchy and real-parent automation recovery.
Correct saved tree-root display choices to the chosen child's immediate parent.
New choices are invalidated if their direct relationship changes, and adjacent
choices must not duplicate any terminal row. The chosen row stays visible at its
parent's existing depth, with its worktree color and a reversible display choice.
