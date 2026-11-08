# DESIGN-LOG: Learn MongoDB (DADA-Lite run)

**DADA-Lite, Adaptive.** Brief: a new front end for MongoDB, in the shape of LearnSQL, to go on the Coding Roadmap. Seed: stance `Make It Bigger (Paula Scher)`, rule `Grid Systems in Graphic Design (Josef Müller-Brockmann)`. Carry-forward read: the LearnSQL run's lessons (below). No critic panel convened; audit-first, one build round.

## Decisions
- **No mongod was available** (binaries blocked, 403; the repo is the 56k-file server source, not buildable here). So the site ships its own evaluator and says so on every page footer and About. Honest framing over a faked "real output".
- **Truth check = a second engine.** Each Mongo result is compared with the same question in SQLite on the same data (11 of 11 match). Content for the lessons is the data the LearnSQL site already uses, so the two sites teach the same answers.
- **Poster landing**, one computed figure per tile (find 2, insertOne +1, updateOne 1, deleteMany −3, count 7, $sum 550.75, $avg 25.8571, $group 5, inner 6, left 9, right 7) plus an About tile: 12 tiles, no empty cell.
- **"No NULL" shown, not stated:** left/right join documents have the field absent, marked in words ("no order: field absent").

## Measured
| Step | Result |
|---|---|
| Break on purpose: `preserveNullAndEmptyArrays` ignored | build failed (left join 9 -> 6 rows) |
| Break on purpose: `$lt` as `$lte` | build **passed**: the data has no value on the edge. Added a boundary self-test; same break now fails (`selftest $lt: [29, 30] != [29]`) |
| `audit.py` round 1 | TOTAL 183: code text 1.40:1, from my own CSS (a find-and-replace left `pre.js,pre.js code{background:none}`, which cleared the block's own background) |
| After fix | TOTAL 0 at 1280/390/320 |
| Screenshot review | join tiles all labelled `$LOOKUP` (fixed to INNER/LEFT/RIGHT JOIN); documents tiles had no fill (fixed); tags scrolled out of view on a phone, leaving colour as the only signal (fixed by wrapping) |

## Not done
No critic panel. Not deployed. The evaluator covers only the operators shown, and results were not run on a real mongod.

## Grade
None given yet.
