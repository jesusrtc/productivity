# Notebook review diff granularity

In semantic `.ipynb` history review, highlight source changes line by line:
removed lines are red, added lines are green, and unchanged lines stay neutral.
Treat a changed cell output as one indivisible rendered block, with a red rail on
the Before output and a green rail on the After output. Do not attempt to diff
inside rendered tables, charts, images, or other rich output.
