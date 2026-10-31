"""Bounded mathematical Python subset, interpreted without exec/eval.

This is an experimental wrapper, not arbitrary Python/bpy: scene is an isolated
JSON snapshot copied into the interpreter; there is no module loader, file,
process, network, host object, or external Python callable in its value space. All arms
receive this same interface. Assign the desired JSON output to ``result``.
"""
from __future__ import annotations

import ast
import copy
import math
import operator
import time
from functools import cmp_to_key
from dataclasses import dataclass


class ComputeError(ValueError):
    pass


@dataclass(frozen=True)
class ComputeLimits:
    source_chars: int = 64000
    ast_nodes: int = 12000
    instructions: int = 300000
    collection_items: int = 200000
    loop_items: int = 20000
    output_bytes: int = 4 * 1024 * 1024
    seconds: float = 8.0
    call_depth: int = 32
    integer_bits: int = 1024


@dataclass
class _Function:
    node: ast.FunctionDef
    closure: dict


class _Returned(Exception):
    def __init__(self, value):
        self.value = value


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


_MATH_FUNCTIONS = frozenset((
    'sqrt', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2',
    'degrees', 'radians', 'floor', 'ceil', 'trunc', 'fabs', 'fsum',
    'hypot', 'dist', 'copysign', 'isclose', 'isfinite', 'exp', 'log',
    'log2', 'log10', 'pow',
))
_MATH_CONSTANTS = {'pi': math.pi, 'e': math.e, 'tau': math.tau}
_BUILTINS = frozenset((
    'sum', 'min', 'max', 'len', 'range', 'enumerate', 'zip', 'abs',
    'float', 'int', 'round', 'list', 'sorted', 'all', 'any', 'bool',
))
_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_COMPARE = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_, ast.IsNot: operator.is_not,
}


class RestrictedCompute:
    """One invocation owns only its plain data and an AST; never Python globals."""

    def __init__(self, limits=None, clock=time.monotonic):
        self.limits = limits or ComputeLimits()
        self.clock = clock

    def run(self, code, scene, *, deadline=None):
        import json
        started = self.clock()
        if deadline is not None and (type(deadline) not in (int, float)
                or not math.isfinite(deadline)):
            raise ComputeError('absolute compute deadline must be finite')
        # Parsing, validation, copying and serialization share the invocation
        # budget, which cannot extend the enclosing episode's deadline.
        self.deadline = min(started + self.limits.seconds,
                            deadline if deadline is not None else math.inf)
        self.steps = 0
        self.allocated = 0
        self.depth = 0
        self._tick(0)
        if type(code) is not str or len(code) > self.limits.source_chars:
            raise ComputeError('code must be a string within source limit')
        try:
            tree = ast.parse(code, mode='exec')
        except (SyntaxError, RecursionError, ValueError) as exc:
            raise ComputeError('invalid mathematical subset source') from exc
        self._tick(0)
        nodes = list(ast.walk(tree))
        self._tick(0)
        if len(nodes) > self.limits.ast_nodes:
            raise ComputeError('AST limit exceeded')
        forbidden = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.With,
                     ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom,
                     ast.Global, ast.Nonlocal, ast.Try, ast.Raise, ast.While,
                     ast.Delete, ast.Lambda, ast.NamedExpr, ast.Set, ast.SetComp)
        for node in nodes:
            self._tick(0)
            if isinstance(node, forbidden):
                raise ComputeError('unsupported statement or expression')
            if isinstance(node, ast.Name) and '__' in node.id:
                raise ComputeError('double underscore identifiers are forbidden')
            if isinstance(node, ast.Attribute):
                if not (isinstance(node.value, ast.Name) and node.value.id == 'math'
                        and node.attr in _MATH_FUNCTIONS | _MATH_CONSTANTS.keys()):
                    raise ComputeError('only whitelisted math attributes are available')
            if isinstance(node, ast.Call) and any(k.arg is None for k in node.keywords):
                raise ComputeError('keyword expansion is forbidden')
        # Validate JSON exactly before deepcopy: external objects never reach the VM.
        self._plain(scene, input_data=True)
        env = {'scene': copy.deepcopy(scene)}
        self._tick(0)
        try:
            self._block(tree.body, env)
            if 'result' not in env:
                raise ComputeError('assign the JSON output to result')
            value = env['result']
            self._plain(value)
            self._output_budget(value)
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            self._tick(0)
            if len(raw.encode('utf-8')) > self.limits.output_bytes:
                raise ComputeError('output byte limit exceeded')
            self._tick(0)
            return {'result': value, 'instructions': self.steps,
                    'implementation': 'restricted_ast_math_no_exec'}
        except ComputeError:
            raise
        except (Exception, RecursionError) as exc:
            # Do not expose host traceback, source path, or repr of external objects.
            raise ComputeError('mathematical program rejected: ' + type(exc).__name__) from None

    def _tick(self, amount=1):
        self.steps += amount
        if self.steps > self.limits.instructions:
            raise ComputeError('instruction limit exceeded')
        if self.clock() >= self.deadline:
            raise ComputeError('compute time limit exceeded')

    def _plain(self, value, input_data=False, depth=0):
        self._tick()
        if depth > 80:
            raise ComputeError('data nesting limit exceeded')
        typ = type(value)
        if typ in (type(None), bool):
            return
        if typ in (int, float):
            if typ is int and value.bit_length() > self.limits.integer_bits:
                raise ComputeError('integer magnitude limit exceeded')
            if typ is float and not math.isfinite(value):
                raise ComputeError('nonfinite number')
            return
        if typ is str:
            if len(value) > (64 * 1024 * 1024 if input_data else self.limits.output_bytes):
                raise ComputeError('string limit exceeded')
            return
        if typ in (list, tuple, dict):
            if not input_data and len(value) > self.limits.collection_items:
                raise ComputeError('collection limit exceeded')
            if typ is dict:
                if any(type(k) not in (str, int, float, bool, type(None)) for k in value):
                    raise ComputeError('plain scalar dictionary keys required')
                for k, v in value.items():
                    self._plain(k, input_data, depth + 1)
                    self._plain(v, input_data, depth + 1)
            else:
                for v in value:
                    self._plain(v, input_data, depth + 1)
            return
        raise ComputeError('only plain data may cross the compute boundary')

    def _alloc(self, count):
        self.allocated += count
        if count > self.limits.collection_items or self.allocated > self.limits.collection_items:
            raise ComputeError('allocation limit exceeded')

    def _output_budget(self, value):
        # Count every occurrence, including aliased strings/subcollections, before
        # json.dumps can expand a shared DAG into an unbounded serialized tree.
        remaining = self.limits.output_bytes
        def visit(item, depth=0):
            nonlocal remaining
            self._tick()
            if depth > 80:
                raise ComputeError('output nesting limit exceeded')
            typ = type(item)
            if typ is str:
                # UTF-8 uses <=4 bytes/character; JSON escaping uses <=6.
                remaining -= 2 + 6 * len(item)
            elif typ in (int, float):
                remaining -= len(str(item))
            elif typ in (bool, type(None)):
                remaining -= 5
            elif typ in (list, tuple):
                remaining -= 2 + len(item)
                for v in item:
                    visit(v, depth + 1)
            elif typ is dict:
                remaining -= 2 + 2 * len(item)
                for k, v in item.items():
                    visit(str(k), depth + 1)
                    visit(v, depth + 1)
            else:
                raise ComputeError('output must be JSON data')
            if remaining < 0:
                raise ComputeError('output serialized byte budget exceeded')
        visit(value)

    def _key(self, value):
        # Recursive tuple hashing of shared DAGs is another unchecked Python
        # computation. JSON dictionaries have scalar keys in this subset.
        if type(value) not in (str, int, float, bool, type(None)):
            raise ComputeError('dictionary keys must be plain scalars')
        self._plain(value)
        return value

    def _compare(self, op, left, right, depth=0):
        self._tick()
        if depth > 80:
            raise ComputeError('comparison nesting limit exceeded')
        if isinstance(op, (ast.Is, ast.IsNot)):
            return (left is right) if isinstance(op, ast.Is) else (left is not right)
        if isinstance(op, (ast.In, ast.NotIn)):
            if type(right) is dict:
                found = self._key(left) in right
            elif type(right) is str and type(left) is str:
                self._tick(len(left) + len(right))
                found = left in right
            else:
                found = any(self._compare(ast.Eq(), left, item, depth + 1) for item in self._iter(right))
            return not found if isinstance(op, ast.NotIn) else found
        lt, rt = type(left), type(right)
        if lt is _Function or rt is _Function:
            if isinstance(op, (ast.Eq, ast.NotEq)):
                return (left is right) if isinstance(op, ast.Eq) else (left is not right)
            raise ComputeError('functions are not orderable')
        if isinstance(op, (ast.Eq, ast.NotEq)):
            if lt in (list, tuple) and rt is lt:
                equal = len(left) == len(right) and all(
                    self._compare(ast.Eq(), a, b, depth + 1) for a, b in zip(left, right))
            elif lt is dict and rt is dict:
                equal = len(left) == len(right)
                if equal:
                    for key, value in left.items():
                        self._tick()
                        if key not in right or not self._compare(ast.Eq(), value, right[key], depth + 1):
                            equal = False
                            break
            elif lt in (list, tuple, dict) or rt in (list, tuple, dict):
                equal = False
            else:
                if lt is str or rt is str:
                    self._tick((len(left) if lt is str else 0) + (len(right) if rt is str else 0))
                equal = left == right
            return not equal if isinstance(op, ast.NotEq) else equal
        if lt in (list, tuple) and rt is lt:
            for a, b in zip(left, right):
                if not self._compare(ast.Eq(), a, b, depth + 1):
                    return self._compare(op, a, b, depth + 1)
            left, right = len(left), len(right)
        elif lt in (dict, list, tuple) or rt in (dict, list, tuple):
            raise ComputeError('incompatible ordering types')
        if type(left) is str or type(right) is str:
            self._tick((len(left) if type(left) is str else 0) + (len(right) if type(right) is str else 0))
        func = _COMPARE.get(type(op))
        if func is None:
            raise ComputeError('unsupported comparison')
        return func(left, right)

    def _assign(self, target, value, env):
        self._tick()
        if isinstance(target, ast.Name):
            if target.id in _BUILTINS or target.id in ('math', 'scene'):
                raise ComputeError('reserved name cannot be assigned')
            env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            values = list(self._iter(value))
            if len(values) != len(target.elts):
                raise ComputeError('unpack length mismatch')
            for t, v in zip(target.elts, values):
                self._assign(t, v, env)
        elif isinstance(target, ast.Subscript):
            base, index = self._expr(target.value, env), self._expr(target.slice, env)
            if type(base) not in (dict, list):
                raise ComputeError('assignment requires a list or dictionary')
            if type(base) is dict:
                index = self._key(index)
            self._alloc(1)
            base[index] = value
        else:
            raise ComputeError('unsupported assignment target')

    def _block(self, nodes, env):
        for node in nodes:
            self._tick()
            if isinstance(node, ast.Assign):
                value = self._expr(node.value, env)
                for target in node.targets:
                    self._assign(target, value, env)
            elif isinstance(node, ast.AugAssign):
                value = self._binary(node.op, self._expr(node.target, env), self._expr(node.value, env))
                self._assign(node.target, value, env)
            elif isinstance(node, ast.Expr):
                self._expr(node.value, env)
            elif isinstance(node, ast.If):
                self._block(node.body if self._expr(node.test, env) else node.orelse, env)
            elif isinstance(node, ast.For):
                broke = False
                for value in self._iter(self._expr(node.iter, env)):
                    self._assign(node.target, value, env)
                    try:
                        self._block(node.body, env)
                    except _Continue:
                        continue
                    except _Break:
                        broke = True
                        break
                if not broke:
                    self._block(node.orelse, env)
            elif isinstance(node, ast.FunctionDef):
                args = node.args
                if (node.decorator_list or args.vararg or args.kwarg or args.kwonlyargs
                        or args.defaults or args.posonlyargs or node.returns
                        or any(a.annotation for a in args.args)):
                    raise ComputeError('functions accept plain positional arguments only')
                if node.name in _BUILTINS or node.name in ('scene', 'math') or '__' in node.name:
                    raise ComputeError('reserved function name')
                env[node.name] = _Function(node, env)
            elif isinstance(node, ast.Return):
                raise _Returned(self._expr(node.value, env) if node.value else None)
            elif isinstance(node, ast.Break):
                raise _Break()
            elif isinstance(node, ast.Continue):
                raise _Continue()
            elif isinstance(node, ast.Pass):
                pass
            else:
                raise ComputeError('unsupported statement: ' + type(node).__name__)

    def _iter(self, value):
        if type(value) not in (list, tuple, dict, str, range):
            raise ComputeError('plain bounded iterable required')
        if len(value) > self.limits.loop_items:
            raise ComputeError('iteration length limit exceeded')
        for item in value:
            self._tick()
            yield item

    def _binary(self, op, left, right):
        func = _BINOPS.get(type(op))
        if func is None:
            raise ComputeError('unsupported arithmetic operator')
        if isinstance(op, ast.Mod) and (type(left) not in (int, float) or type(right) not in (int, float)):
            raise ComputeError('modulo is available for numbers only, never string formatting')
        if isinstance(op, ast.Mult):
            for seq, count in ((left, right), (right, left)):
                if type(seq) in (str, list, tuple) and type(count) is int:
                    self._alloc(len(seq) * max(0, count))
        if isinstance(op, ast.Add) and type(left) in (str, list, tuple):
            self._alloc(len(left) + len(right))
        if isinstance(op, ast.Pow) and (type(right) not in (int, float) or abs(right) > 1000):
            raise ComputeError('exponent limit exceeded')
        value = func(left, right)
        if type(value) in (int, float):
            self._plain(value)
        elif type(value) not in (str, list, tuple):
            raise ComputeError('arithmetic produced unsupported data')
        return value

    def _expr(self, node, env):
        self._tick()
        if isinstance(node, ast.Constant):
            self._plain(node.value)
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ComputeError('unknown variable: ' + node.id)
            return env[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            self._alloc(len(node.elts))
            values = [self._expr(v, env) for v in node.elts]
            return tuple(values) if isinstance(node, ast.Tuple) else values
        if isinstance(node, ast.Dict):
            if any(k is None for k in node.keys):
                raise ComputeError('dictionary expansion is forbidden')
            self._alloc(len(node.keys))
            return {self._key(self._expr(k, env)): self._expr(v, env) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.BinOp):
            return self._binary(node.op, self._expr(node.left, env), self._expr(node.right, env))
        if isinstance(node, ast.UnaryOp):
            value = self._expr(node.operand, env)
            func = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}.get(type(node.op))
            if func is None:
                raise ComputeError('unsupported unary operator')
            return func(value)
        if isinstance(node, ast.BoolOp):
            value = self._expr(node.values[0], env)
            for expr in node.values[1:]:
                if (isinstance(node.op, ast.And) and not value) or (isinstance(node.op, ast.Or) and value):
                    return value
                value = self._expr(expr, env)
            return value
        if isinstance(node, ast.Compare):
            left = self._expr(node.left, env)
            for op, expr in zip(node.ops, node.comparators):
                right = self._expr(expr, env)
                if type(op) not in _COMPARE or not self._compare(op, left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return self._expr(node.body if self._expr(node.test, env) else node.orelse, env)
        if isinstance(node, ast.Subscript):
            value = self._expr(node.value, env)
            if type(value) not in (dict, list, tuple, str):
                raise ComputeError('indexing requires plain data')
            index = self._expr(node.slice, env)
            if type(value) is dict:
                index = self._key(index)
            result = value[index]
            if isinstance(index, slice):
                self._alloc(len(result))
            return result
        if isinstance(node, ast.Slice):
            return slice(*(self._expr(v, env) if v else None for v in (node.lower, node.upper, node.step)))
        if isinstance(node, ast.Attribute):
            if node.attr in _MATH_CONSTANTS:
                return _MATH_CONSTANTS[node.attr]
            raise ComputeError('math functions must be called directly')
        if isinstance(node, ast.Call):
            args = [self._expr(a, env) for a in node.args]
            kwargs = {k.arg: self._expr(k.value, env) for k in node.keywords}
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
                if name not in _MATH_FUNCTIONS:
                    raise ComputeError('math function unavailable')
                # Only VM data may reach the small fixed math allowlist.
                for value in (*args, *kwargs.values()):
                    self._plain(value)
                if name == 'pow' and (len(args) != 2 or abs(args[1]) > 1000):
                    raise ComputeError('exponent limit exceeded')
                result = getattr(math, name)(*args, **kwargs)
                self._plain(result)
                return result
            if not isinstance(node.func, ast.Name):
                raise ComputeError('only direct named calls are allowed')
            name = node.func.id
            if name in _BUILTINS:
                return self._builtin(name, args, kwargs)
            function = env.get(name)
            if type(function) is not _Function or kwargs:
                raise ComputeError('call target is not an interpreted function')
            return self._call_function(function, args)
        if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.DictComp)):
            items = []
            local = dict(env)
            def visit(index):
                if index == len(node.generators):
                    self._alloc(1)
                    items.append((self._key(self._expr(node.key, local)), self._expr(node.value, local))
                                 if isinstance(node, ast.DictComp) else self._expr(node.elt, local))
                    return
                gen = node.generators[index]
                if gen.is_async:
                    raise ComputeError('async comprehension is forbidden')
                for value in self._iter(self._expr(gen.iter, local)):
                    self._assign(gen.target, value, local)
                    if all(self._expr(test, local) for test in gen.ifs):
                        visit(index + 1)
            visit(0)
            return dict(items) if isinstance(node, ast.DictComp) else items
        raise ComputeError('unsupported expression: ' + type(node).__name__)

    def _call_function(self, function, args):
        if len(args) != len(function.node.args.args):
            raise ComputeError('function arity mismatch')
        self.depth += 1
        if self.depth > self.limits.call_depth:
            raise ComputeError('function depth limit exceeded')
        local = dict(function.closure)
        local.update({a.arg: v for a, v in zip(function.node.args.args, args)})
        try:
            self._block(function.node.body, local)
            return None
        except _Returned as returned:
            return returned.value
        finally:
            self.depth -= 1

    def _builtin(self, name, args, kwargs):
        if name == 'sorted':
            if len(args) != 1 or set(kwargs) - {'reverse', 'key'}:
                raise ComputeError('sorted arguments rejected')
            items = list(self._iter(args[0]))
            self._alloc(len(items))
            key = kwargs.get('key')
            if key is not None and type(key) is not _Function:
                raise ComputeError('sorted key must be an interpreted function')
            decorated = [(self._call_function(key, [value]) if key else value, value) for value in items]
            def compare(a, b):
                if self._compare(ast.Eq(), a[0], b[0]):
                    return 0
                return -1 if self._compare(ast.Lt(), a[0], b[0]) else 1
            return [value for _, value in sorted(decorated, key=cmp_to_key(compare),
                                                reverse=bool(kwargs.get('reverse', False)))]
        if kwargs:
            raise ComputeError('keyword arguments unavailable for this builtin')
        if name == 'range':
            if not 1 <= len(args) <= 3 or any(type(a) is not int for a in args):
                raise ComputeError('range requires integers')
            result = range(*args)
            if len(result) > self.limits.loop_items:
                raise ComputeError('range length limit exceeded')
            return result
        if name in ('enumerate', 'zip'):
            if name == 'enumerate':
                if len(args) not in (1, 2) or (len(args) == 2 and type(args[1]) is not int):
                    raise ComputeError('enumerate arguments rejected')
                result = list(enumerate(list(self._iter(args[0])), args[1] if len(args) == 2 else 0))
            else:
                result = list(zip(*(list(self._iter(a)) for a in args)))
            self._alloc(len(result))
            return result
        if name in ('sum', 'all', 'any', 'list'):
            if not args and name == 'list':
                return []
            if not 1 <= len(args) <= (2 if name == 'sum' else 1):
                raise ComputeError('builtin arity mismatch')
            items = list(self._iter(args[0]))
            if name == 'list':
                self._alloc(len(items))
                return items
            if name == 'sum':
                total = args[1] if len(args) == 2 else 0
                for value in items:
                    total = self._binary(ast.Add(), total, value)
                return total
            return all(items) if name == 'all' else any(items)
        if name in ('min', 'max'):
            items = list(self._iter(args[0])) if len(args) == 1 else args
            if not items:
                raise ComputeError('min/max require values')
            self._tick(len(items))
            value = items[0]
            for item in items[1:]:
                if self._compare(ast.Lt() if name == 'min' else ast.Gt(), item, value):
                    value = item
            return value
        # None of these can invoke a user Python protocol: all operands are VM values.
        for value in args:
            self._plain(value)
        func = {'len': len, 'abs': abs, 'float': float, 'int': int,
                'round': round, 'bool': bool}[name]
        if name == 'int' and args and type(args[0]) is str and len(args[0]) > 1024:
            raise ComputeError('integer string length limit exceeded')
        result = func(*args)
        self._plain(result)
        return result
