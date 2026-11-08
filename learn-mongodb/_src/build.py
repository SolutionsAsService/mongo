"""Builds site/ for Learn MongoDB.

Every query in queries.json is run by evaluator.py (not mongod) on data.json.
Each result is then checked against the equivalent SQL run in SQLite on the same
data; the build stops if the two disagree, if a pinned figure (EXPECT) drifts, or
if an internal link breaks.  Run: python3 _src/build.py
"""
import html, json, pathlib, re, shutil, sqlite3, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / 'site'
sys.path.insert(0, str(HERE))
from evaluator import DB, MISSING  # noqa: E402

DATA = json.loads((HERE / 'data.json').read_text(encoding='utf-8'))
QUERIES = json.loads((HERE / 'queries.json').read_text(encoding='utf-8'))
SITE_URL = 'https://learnmongo.shadw.app/'
REPO_URL = 'https://github.com/SolutionsAsService/mongo/tree/master/learn-mongodb'
TOPICS = [('documents', 'Find and change documents', 'find, insertOne, updateOne and deleteMany. The last three run in order on one collection.'),
          ('aggregates', 'Aggregate', 'countDocuments and the aggregation pipeline: $sum, $avg and $group.'),
          ('joins', 'Join with $lookup', 'Inner, left and right joins, built from $lookup and $unwind.')]
NAVS = {'index': 'Home', 'documents': 'Documents', 'aggregates': 'Aggregate', 'joins': 'Join', 'about': 'About'}
EXPECT = {'find': 2, 'insertOne': 1, 'updateOne': 1, 'deleteMany': -3, 'count': 7, 'sum': 550.75, 'avg': 25.8571,
          'group': 5, 'inner': 6, 'left': 9, 'right': 7}
TILE = {'inner': 'INNER JOIN', 'left': 'LEFT JOIN', 'right': 'RIGHT JOIN'}
SQL_SEED = '''CREATE TABLE users(user_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, age INTEGER);
CREATE TABLE orders(order_id INTEGER PRIMARY KEY, user_id INTEGER, order_amount REAL);'''


def sqldb():
    c = sqlite3.connect(':memory:'); c.executescript(SQL_SEED)
    c.executemany('INSERT INTO users VALUES(?,?,?,?)', [(u['_id'], u['first_name'], u['last_name'], u['age']) for u in DATA['users']])
    c.executemany('INSERT INTO orders VALUES(?,?,?)', [(o['_id'], o['user_id'], o['order_amount']) for o in DATA['orders']])
    return c


# ---- shell-style rendering of a query -------------------------------------------------------
def js(v):
    if isinstance(v, dict):
        return '{ ' + ', '.join(f'{k if re.fullmatch(r"[A-Za-z_$][\w$]*", k) else json.dumps(k)}: {js(x)}' for k, x in v.items()) + ' }' if v else '{}'
    if isinstance(v, list):
        return '[' + ', '.join(js(x) for x in v) + ']'
    if v is None: return 'null'
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, float) and v == int(v): return f'{v:.1f}' if False else str(int(v)) if False else repr(v)
    return json.dumps(v)


def shell(q):
    a = q['args']
    if q['op'] == 'aggregate':
        stages = ',\n'.join('  ' + js(s) for s in a[0])
        return f'db.{q["coll"]}.aggregate([\n{stages}\n])'
    inner = ', '.join(js(x) for x in a)
    one = f'db.{q["coll"]}.{q["op"]}({inner})'
    if len(one) <= 78: return one
    return f'db.{q["coll"]}.{q["op"]}(\n' + ',\n'.join('  ' + js(x) for x in a) + '\n)'


KW = r'\b(db|find|insertOne|updateOne|deleteMany|countDocuments|aggregate)\b'
def code(text, cls='js'):
    esc = html.escape(text)
    esc = re.sub(r'(\$[A-Za-z]+)', r'<i>\1</i>', esc)
    esc = re.sub(KW, r'<b>\1</b>', esc)
    return f'<pre class="{cls}"><code>{esc}</code></pre>'


def ticks(s): return re.sub(r'`([^`]+)`', r'<code>\1</code>', html.escape(s, quote=False))


def num(v):
    if isinstance(v, float):
        s = f'{v:.4f}'.rstrip('0').rstrip('.'); return s
    return str(v)


def doc_line(d):
    return '{ ' + ', '.join(f'{k}: {json.dumps(v)}' for k, v in d.items()) + ' }' if d else '{}'


def doclist(docs, marks, caption):
    lis = []
    for d, m in zip(docs, marks):
        tag = {'both': 'both', 'only-left': 'no order: field absent', 'only-right': 'no user: fields absent',
               'new': 'new', 'changed': 'changed', 'gone': 'removed', '': ''}[m]
        cls = {'both': 'matched', 'only-left': 'only-left', 'only-right': 'only-right'}.get(m, m)
        lis.append(f'<li class="{cls}"><code>{html.escape(doc_line(d))}</code><span class="tag">{tag}</span></li>')
    return f'<div class="dw" tabindex="0" role="region" aria-label="{html.escape(caption)}"><p class="cap">{html.escape(caption)}</p><ol class="docs">{"".join(lis)}</ol></div>'


# ---- run -------------------------------------------------------------------------------------
def selftest():
    """The sample data has no value on a filter's edge, so it cannot tell $lt from $lte.
    Check every comparison operator on edge values against SQLite."""
    vals = [29, 30, 31]
    docs = [{'_id': i, 'n': v} for i, v in enumerate(vals)]
    c = sqlite3.connect(':memory:'); c.execute('CREATE TABLE t(n INTEGER)'); c.executemany('INSERT INTO t VALUES(?)', [(v,) for v in vals])
    for op, sym in [('$lt', '<'), ('$lte', '<='), ('$gt', '>'), ('$gte', '>='), ('$eq', '='), ('$ne', '!=')]:
        got = sorted(d['n'] for d in DB({'t': docs}).find('t', {'n': {op: 30}}))
        want = sorted(x[0] for x in c.execute(f'SELECT n FROM t WHERE n {sym} 30'))
        assert got == want, f'selftest {op}: {got} != {want}'


def run():
    selftest()
    results = {}
    mdb = DB(DATA); sdb = sqldb()
    pristine = lambda: DB(DATA)
    for q in QUERIES:
        r = dict(q=q)
        op, coll, a = q['op'], q['coll'], q['args']
        if q['op'] in ('insertOne', 'updateOne', 'deleteMany'):
            before = mdb.find('users')
            res = getattr(mdb, op)(coll, *a)
            after = mdb.find('users')
            sdb.execute(q['sql']) if q['sql'].startswith(('INSERT', 'UPDATE', 'DELETE')) else None
            sqlrows = sdb.execute('SELECT user_id,first_name,last_name,age FROM users ORDER BY user_id').fetchall()
            mrows = [(d['_id'], d['first_name'], d['last_name'], d['age']) for d in sorted(after, key=lambda d: d['_id'])]
            assert sqlrows == mrows, f'{q["id"]}: Mongo and SQLite disagree\n{mrows}\n{sqlrows}'
            r.update(kind='dml', ack=res, before=before, after=after)
        else:
            m = pristine()
            if op == 'find': docs = m.find(coll, *a)
            elif op == 'countDocuments': docs = m.countDocuments(coll, *a)
            else: docs = m.aggregate(coll, a[0])
            fresh = sqldb()
            sqlrows = fresh.execute(q['sql']).fetchall()
            if op == 'countDocuments':
                assert [docs] == [x[0] for x in sqlrows], q['id']
            else:
                got = [tuple(None if d.get(f, MISSING) is MISSING else d[f] for f in q['cmp']) for d in docs]
                want = [tuple(x) for x in sqlrows]
                got = [tuple(round(x, 6) if isinstance(x, float) else x for x in t) for t in got]
                want = [tuple(round(x, 6) if isinstance(x, float) else x for x in t) for t in want]
                key = lambda t: tuple((x is None, str(x)) for x in t)
                assert sorted(got, key=key) == sorted(want, key=key), f'{q["id"]}: Mongo and SQLite disagree\n{got}\n{want}'
            r.update(kind='value' if op == 'countDocuments' else 'docs', docs=docs)
        results[q['id']] = r
    return results


def figure(r):
    i = r['q']['id']
    if r['kind'] == 'dml':
        if i == 'updateOne': return '1', 'modified: age 30 → 31'
        d = len(r['after']) - len(r['before']); return f'{d:+d}'.replace('-', '−'), 'document' if abs(d) == 1 else 'documents'
    if r['kind'] == 'value': return str(r['docs']), 'documents counted'
    docs = r['docs']
    if i in ('sum', 'avg'):
        (k, v), = [(k, v) for k, v in docs[0].items() if k != '_id']; return num(v), k.replace('_', ' ')
    if i == 'group': return str(len(docs)), 'groups'
    return str(len(docs)), 'documents'


def check(results):
    for i, want in EXPECT.items():
        r = results[i]
        if r['kind'] == 'dml':
            got = len(r['after']) - len(r['before']) if i != 'updateOne' else r['ack']['modifiedCount']
        elif r['kind'] == 'value': got = r['docs']
        elif i in ('sum', 'avg'): got = round([v for k, v in r['docs'][0].items() if k != '_id'][0], 4)
        else: got = len(r['docs'])
        assert got == want, f'{i}: {got} != pinned {want}'


def section(r):
    q = r['q']; fig, unit = figure(r)
    out = [f'<section class="ex" id="{q["id"]}"><header><h2>{html.escape(q["name"])}</h2><p class="fig"><b>{html.escape(fig)}</b> <span>{html.escape(unit)}</span></p></header>',
           f'<p class="intro">{html.escape(q["intro"])}</p>', code(shell(q))]
    if r['kind'] == 'dml':
        b, a = r['before'], r['after']; bid = {d['_id']: d for d in b}; aid = {d['_id']: d for d in a}
        bm = ['gone' if d['_id'] not in aid else ('changed' if aid[d['_id']] != d else '') for d in b]
        am = ['new' if d['_id'] not in bid else ('changed' if bid[d['_id']] != d else '') for d in a]
        out.append(f'<h3>Acknowledgement</h3>{code(doc_line(r["ack"]), "js res")}')
        out.append('<div class="ba2"><div><h3>Before</h3>' + doclist(b, bm, f'users before ({len(b)} documents)') +
                   '</div><div><h3>After</h3>' + doclist(a, am, f'users after ({len(a)} documents)') + '</div></div>')
    elif r['kind'] == 'value':
        out.append(f'<h3>Result</h3>{code(str(r["docs"]), "js res")}')
    else:
        docs = r['docs']; marks = ['' for _ in docs]
        if q['topic'] == 'joins':
            marks = []
            for d in docs:
                marks.append('only-right' if 'first_name' not in d else ('only-left' if 'order_id' not in d else 'both'))
        out.append(f'<h3>Result: {len(docs)} document{"" if len(docs) == 1 else "s"}</h3>' + doclist(docs, marks, 'result documents'))
    out.append(f'<h3>In SQL</h3>{code(q["sql"], "sql")}<p class="src">The SQL gives the same answer: the build runs both on the same data and stops if they differ.</p>')
    out.append('<h3>Reading it</h3><ul class="notes">' + ''.join(f'<li>{ticks(n)}</li>' for n in q['notes']) + '</ul></section>')
    return ''.join(out)


def page(name, title, desc, body):
    nav = ''.join(f'<a href="{k}.html"{" aria-current=page" if k == name else ""}>{v}</a>' for k, v in NAVS.items())
    canon = SITE_URL + ('' if name == 'index' else name)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{canon}"><link rel="icon" href="favicon.svg" type="image/svg+xml">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}"><meta property="og:type" content="website"><meta property="og:url" content="{canon}">
<link rel="stylesheet" href="style.css"></head>
<body><a class="skip" href="#main">Skip to content</a>
<header class="top"><a class="brand" href="index.html">Learn<b>Mongo</b></a><nav aria-label="Pages">{nav}</nav></header>
<main id="main">{body}</main>
<footer><p>Results come from this site's own evaluator for a slice of the MongoDB query language, not from a running mongod, and are checked against the same queries in SQLite. Invented data. <a href="{REPO_URL}">Source</a>. By SolutionsAsService.</p></footer></body></html>'''


def build_pages(results):
    tiles = []
    for slug, label, _ in TOPICS:
        for q in [q for q in QUERIES if q['topic'] == slug]:
            fig, unit = figure(results[q['id']])
            tiles.append(f'<a class="tile t-{slug}{" long" if len(fig) > 4 else ""}" href="{slug}.html#{q["id"]}"><span class="nm">{html.escape(TILE.get(q["id"], q["name"]))}</span><span class="big">{html.escape(fig)}</span><span class="un">{html.escape(unit)}</span></a>')
    tiles.append('<a class="tile t-about" href="about.html"><span class="nm">HOW</span><span class="big">?</span><span class="un">How these numbers were made</span></a>')
    topics = ''.join(f'<li><a href="{s}.html"><b>{l}</b><span>{d}</span></a></li>' for s, l, d in TOPICS)
    pages = {'index': page('index', 'Learn MongoDB: eleven queries, every one run',
        'Learn MongoDB queries from results that were computed, not typed: find, insert, update, delete, aggregation and $lookup joins, each checked against SQL.',
        f'<section class="hero"><h1>Eleven queries.<br>Every one <em>run</em>.</h1><p class="lede">MongoDB, side by side with SQL. Each tile is the number its query returned on {len(DATA["users"])} user documents and {len(DATA["orders"])} order documents, and each is checked against the same question asked in SQL. Click one for the query and the documents.</p></section>'
        f'<section class="poster" aria-label="All eleven queries">{"".join(tiles)}</section><section class="start"><h2>Three lessons, in order</h2><ol class="topics">{topics}</ol></section>')}
    tabs = ('<div class="ba2"><div><h3>users</h3>' + doclist(DATA['users'], [''] * len(DATA['users']), 'users collection') +
            '</div><div><h3>orders</h3>' + doclist(DATA['orders'], [''] * len(DATA['orders']), 'orders collection') + '</div></div>')
    intros = {'documents': '<p>Documents are JSON-like objects in a collection; no schema is declared first. Insert, update and delete run in order on one copy of <code>users</code>; rows are marked <b>new</b>, <b>changed</b> or <b>removed</b>.</p>',
              'aggregates': '<p>An aggregation pipeline is a list of stages; each feeds the next. Every query here reads the original, unchanged collections.</p>',
              'joins': '<p>MongoDB joins with <code>$lookup</code>. There is no NULL: a missing match leaves a field <b>absent</b>. Documents marked <b>both</b> matched, <b>no order</b> are users with no order, and <b>no user</b> is order 107, whose user_id 99 matches nobody.</p>'}
    for i, (slug, label, blurb) in enumerate(TOPICS):
        secs = ''.join(section(results[q['id']]) for q in QUERIES if q['topic'] == slug)
        body = f'<h1>{label}</h1><p class="lede">{blurb}</p>{intros[slug]}<details class="data"{" open" if slug == "joins" else ""}><summary>The two collections these run on</summary>{tabs}</details>{secs}'
        if i + 1 < len(TOPICS): body += f'<p class="next"><a href="{TOPICS[i+1][0]}.html">Next: {TOPICS[i+1][1]} →</a></p>'
        pages[slug] = page(slug, f'{label}: Learn MongoDB', blurb + ' Every result is computed and cross-checked.', body)
    pages['about'] = page('about', 'About: Learn MongoDB', 'How the Learn MongoDB results are produced, and what is not covered.',
        f'''<h1>About</h1><p class="lede">The only claims here are ones the build checks.</p>
<h2>How the numbers get here</h2><p><code>python3 _src/build.py</code> runs each query in <code>_src/queries.json</code> with <code>_src/evaluator.py</code> on <code>_src/data.json</code>, then runs the equivalent SQL in SQLite on the same data and stops if the answers differ. Eleven of eleven agreed at build time.</p>
<h2>What is not covered</h2><p>The evaluator is this site's own, about 150 lines, and covers only the operators shown. It is not <code>mongod</code>: indexes, ObjectId generation, type ordering, transactions and every other operator are outside it. To see a result from a real server, run the shown query in <code>mongosh</code>. Data is invented; nobody in it is real.</p>
<h2>Source</h2><p>This site lives in <a href="{REPO_URL}">learn-mongodb/</a> of a fork of the MongoDB server repository; it does not touch the server code.</p>''')
    return pages


def main():
    results = run(); check(results)
    OUT.mkdir(exist_ok=True)
    for p in OUT.glob('*.html'): p.unlink()
    shutil.copy(HERE / 'style.css', OUT / 'style.css')
    pages = build_pages(results)
    for n, h in pages.items(): (OUT / f'{n}.html').write_text(h, encoding='utf-8')
    (OUT / 'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#0b2e1f"/><path d="M16 3c4 5 7 9 7 14a7 7 0 0 1-14 0c0-5 3-9 7-14z" fill="#00ed64"/><rect x="15" y="17" width="2" height="12" fill="#f4f1ea"/></svg>')
    (OUT / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n')
    (OUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{SITE_URL}{"" if n == "index" else n}</loc></url>' for n in pages) + '</urlset>')
    bad = []
    for n, h in pages.items():
        for f, frag in re.findall(r'href="([^"#]*)(#[^"]*)?"', h):
            if not f or f.startswith('http'): continue
            if not (OUT / f).exists(): bad.append((n, f))
            elif frag and f'id="{frag[1:]}"' not in (OUT / f).read_text(encoding='utf-8'): bad.append((n, f + frag))
    if bad: sys.exit(f'broken links: {bad}')
    print(f'built {len(pages)} pages; {len(results)} queries run and matched SQLite; figures match EXPECT')


if __name__ == '__main__':
    main()
