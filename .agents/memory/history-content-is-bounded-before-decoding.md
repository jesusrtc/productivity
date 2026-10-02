# Bound Git history content before decoding

Git patches can contain non-UTF-8 text, including unrelated commit companions.
subprocess.run(text=True) decodes before route code can inspect the output and
previously crashed on a roughly 138 MB patch. History patches and notebook blobs
now spool to a temporary file, check the 8 MiB preview limit, and decode UTF-8
with replacement. Apply the same aggregate limit to untracked worktree patches.
Binary files keep their file entries without text hunks; oversized previews
return an explicit 413 instead of exhausting the renderer or raising 500.
