# Objective resource icons follow file paths

Use the existing `fileIconHtml` extension mapping through the Objectives bridge
for owned Markdown/notebooks and generic file references. A generic `kind:file`
resource ending in `.ipynb` gets the Jupyter icon, and `.sql` gets the database
icon, without requiring re-import or a kind change. Assistant references keep
their internal document icon. Links use the shared URL-based service renderer.
