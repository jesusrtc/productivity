# Notebook typing includes the visible highlight and browser draft

Notebook textarea text is transparent; the syntax overlay is what users see.
The optional --notebook-view --notebook-typing workflow therefore checks exact
textarea/cursor/focus, connected/editable state, matching highlight text and
the saved localStorage draft at native input and paint opportunity. Keep the
25 ms independent key cadence, clock validation and 200 ms failure gate.
This is a browser paint estimate, not physical display latency.

Each visit verifies every notebook cell, output and control; the final two
workspace switches restore both latest drafts. Both on-disk notebooks must
remain byte-for-byte unchanged. The probe does not execute cells or claim
execution/interrupt coverage. --notebook-code-lines explicitly extends the
first code cell; its default zero preserves the old viewing fixture. Native
Tab is not replaced by a synthetic indentation operation in this workflow.
