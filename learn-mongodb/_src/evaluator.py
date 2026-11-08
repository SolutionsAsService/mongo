"""A small evaluator for the slice of the MongoDB query language this site teaches.

It is NOT mongod. It implements, with MongoDB's documented semantics:
  find (filter, projection), insertOne, updateOne ($set), deleteMany, countDocuments,
  aggregate with $match, $group ($sum, $avg, $count-by-sum-1), $lookup, $unwind
  (with preserveNullAndEmptyArrays), $project, $sort.
Filters: implicit AND, $eq $ne $lt $lte $gt $gte. Anything else raises, so the site
can never print a result this module did not compute.
"""
import copy

MISSING = object()


def get(doc, path):
    cur = doc
    for p in path.split('.'):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return MISSING
    return cur


def match(doc, flt):
    for k, cond in flt.items():
        v = get(doc, k)
        if isinstance(cond, dict) and any(c.startswith('$') for c in cond):
            for op, arg in cond.items():
                if v is MISSING:
                    return False
                ok = {'$eq': v == arg, '$ne': v != arg, '$lt': v < arg, '$lte': v <= arg,
                      '$gt': v > arg, '$gte': v >= arg}.get(op)
                if ok is None:
                    raise ValueError(f'unsupported operator {op}')
                if not ok:
                    return False
        elif v is MISSING or v != cond:
            return False
    return True


def expr(e, doc):
    """Evaluate an aggregation expression: a literal, or a "$field" path."""
    if isinstance(e, str) and e.startswith('$'):
        return get(doc, e[1:])
    if isinstance(e, (int, float, str)) or e is None:
        return e
    raise ValueError(f'unsupported expression {e!r}')


def project(doc, spec):
    out = {}
    inc = {k: v for k, v in spec.items() if k != '_id'}
    if spec.get('_id', 1) not in (0, False) and '_id' in doc:
        out['_id'] = doc['_id']
    for k, v in inc.items():
        if v in (1, True):
            val = get(doc, k)
        else:
            val = expr(v, doc)
        if val is not MISSING:  # a missing field is omitted, never null
            out[k] = val
    return out


class DB:
    def __init__(self, colls):
        self.c = {k: copy.deepcopy(v) for k, v in colls.items()}

    def find(self, coll, flt=None, proj=None):
        docs = [d for d in self.c[coll] if match(d, flt or {})]
        return [project(d, proj) if proj else copy.deepcopy(d) for d in docs]

    def insertOne(self, coll, doc):
        self.c[coll].append(copy.deepcopy(doc))
        return {'acknowledged': True, 'insertedId': doc['_id']}

    def updateOne(self, coll, flt, upd):
        hit = [d for d in self.c[coll] if match(d, flt)]
        modified = 0
        if hit:
            for k, v in upd['$set'].items():
                if hit[0].get(k, MISSING) != v:
                    modified = 1
                hit[0][k] = v
        return {'acknowledged': True, 'matchedCount': min(len(hit), 1), 'modifiedCount': modified}

    def deleteMany(self, coll, flt):
        keep = [d for d in self.c[coll] if not match(d, flt)]
        n = len(self.c[coll]) - len(keep)
        self.c[coll] = keep
        return {'acknowledged': True, 'deletedCount': n}

    def countDocuments(self, coll, flt=None):
        return len(self.find(coll, flt))

    def aggregate(self, coll, pipeline):
        docs = copy.deepcopy(self.c[coll])
        for stage in pipeline:
            (name, arg), = stage.items()
            if name == '$match':
                docs = [d for d in docs if match(d, arg)]
            elif name == '$group':
                groups = {}
                for d in docs:
                    key = expr(arg['_id'], d)
                    groups.setdefault(repr(key), (key, []))[1].append(d)
                out = []
                for key, members in groups.values():
                    g = {'_id': key}
                    for field, acc in arg.items():
                        if field == '_id':
                            continue
                        (op, e), = acc.items()
                        vals = [expr(e, m) for m in members]
                        if op == '$sum':
                            g[field] = sum(v for v in vals if isinstance(v, (int, float)))
                        elif op == '$avg':
                            nums = [v for v in vals if isinstance(v, (int, float))]
                            g[field] = sum(nums) / len(nums) if nums else None
                        else:
                            raise ValueError(f'unsupported accumulator {op}')
                    out.append(g)
                docs = out
            elif name == '$lookup':
                foreign = self.c[arg['from']]
                for d in docs:
                    lv = get(d, arg['localField'])
                    d[arg['as']] = [copy.deepcopy(f) for f in foreign
                                    if lv is not MISSING and get(f, arg['foreignField']) == lv]
            elif name == '$unwind':
                path = arg['path'][1:] if isinstance(arg, dict) else arg[1:]
                keep = isinstance(arg, dict) and arg.get('preserveNullAndEmptyArrays')
                out = []
                for d in docs:
                    arr = d.get(path)
                    if isinstance(arr, list) and arr:
                        for item in arr:
                            n = dict(d); n[path] = item; out.append(n)
                    elif keep:
                        n = dict(d); n.pop(path, None); out.append(n)  # field removed, as in MongoDB
                docs = out
            elif name == '$project':
                docs = [project(d, arg) for d in docs]
            elif name == '$sort':
                for k, direction in reversed(list(arg.items())):
                    docs.sort(key=lambda d: (get(d, k) is MISSING, get(d, k) if get(d, k) is not MISSING else 0),
                              reverse=direction < 0)
            else:
                raise ValueError(f'unsupported stage {name}')
        return docs
