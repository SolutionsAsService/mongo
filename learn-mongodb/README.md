# Learn MongoDB

Eleven MongoDB queries, every one run: find, insertOne, updateOne, deleteMany, countDocuments, `$sum`, `$avg`, `$group` and inner, left and right joins with `$lookup`. A front end for learning MongoDB, side by side with SQL (see LearnSQL).

This directory sits inside a fork of the MongoDB server repository and does not touch the server code.

- **What runs the queries:** `_src/evaluator.py`, this site's own evaluator for the operators shown. It is **not mongod**; a mongod binary could not be fetched or built in the session that made this.
- **How the results are trusted:** the build runs every query, then runs the equivalent SQL in SQLite on the same data and stops if the answers differ. A boundary self-test checks every comparison operator on edge values, because the sample data alone cannot tell `$lt` from `$lte` (proved by breaking the evaluator on purpose).
- **Build:** `python3 _src/build.py` writes `site/` (Python 3, no dependencies). Queries: `_src/queries.json`. Data: `_src/data.json` (invented).
- **Deploy:** `vercel.json` serves `site/`. Intended address https://learnmongo.shadw.app/ (not yet deployed).
- **Record:** `_src/design/DESIGN-LOG.md`.
