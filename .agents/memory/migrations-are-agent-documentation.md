# Lab migrations is documentation for agents

The user clarified that `lab migrations` should explain migrations and expected
formats, not act as another migration executor or inspect client state.

`lab migrations [topic]` prints packaged guidance, including Assistant schema 2
examples, identity and relationship rules, old-to-new mapping, preservation and
verification steps. Existing `lab assistant migrate` remains the conversion tool.

`lab agent context migrations`, `lab agents context migrations`, and
`lab context migrations` read the same overview. The launch guide and UI's Lab
agent context point to it. Keep these documentation commands free of client-data
reads and writes. Add future format/migration guides as package resources.
