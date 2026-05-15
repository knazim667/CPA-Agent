## CODE ARCHITECTURE RULES

- No single file exceeds 300 lines. If adding code would push a file past 
  300 lines, stop and refactor first — split into components, then continue.
- One component, one file. Never combine multiple components in one file.
- One responsibility per file. A file that fetches data does not also render UI.
- When fixing a bug, read only the relevant component file — not the whole codebase.
- Before creating any new file, state what it does in one sentence. 
  If you cannot, the responsibility is not clear enough — redesign first.