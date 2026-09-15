# File modal sort is remembered per file

The modal file list defaults globally to modification date, newest first.
Offer modified date, creation date, and name in either direction, and save
changes automatically in browser storage keyed by root and opened file.
Each file retains its own sort on reopening; other files keep their own saved
choice or the default. Use filesystem birth time for creation, never Unix
ctime; unknown dates sort last in either direction.
