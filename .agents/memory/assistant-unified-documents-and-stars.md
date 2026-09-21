# Assistant uses one Documents library

The September 18, 2026 request supersedes separate Tasks/Notes navigation and
mandatory status on every tab. Tasks, notes, meetings and series share one
Documents entry. Keep stable existing task/note paths and identities; the UI
and `lab assistant document` CLI combine them without a file migration.

Task tracking (`track_task`) and document retention (`keep_in_documents`) are
independent. New content tabs are untracked; Add task creates tracked work.
Preserve legacy tracking when no flag is present. Untracked branches do not
block completion. Completed transient tasks go to history; retained documents
remain available with completed work in the same file.

Persist stars in Markdown (`starred`). A meeting series and each note have
independent stars. Meetings is a selectable root label (`note_type: meeting`),
with optional date and series. Keep content and membership on label changes;
reject removing the series label while members still point to it.
