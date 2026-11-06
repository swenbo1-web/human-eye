"""Explicit, immutable v1 deployment inputs for Cerebellar Flash."""

from dataclasses import dataclass, fields

import numpy as np

from .cerebellar_flash import CerebellarFlash, EXPERIENCE_CAPACITY, LinearHead


def _version(value):
    value = np.asarray(value)
    if value.shape != () or value.dtype.kind not in "iu" or int(value) != 1:
        raise ValueError("CF deployment version must be the scalar integer 1")
    return 1


def _array(value, name, shape, dtype=np.float64):
    value = np.asarray(value)
    expected = np.dtype(dtype)
    if (value.dtype.kind, value.dtype.itemsize) != (expected.kind, expected.itemsize):
        raise ValueError(f"{name} must have dtype {expected.name}")
    if value.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {value.shape}")
    if expected == np.float64 and not np.isfinite(value).all():
        raise ValueError(f"{name} must contain only finite values")
    return value


def _immutable_array(value):
    # Owning a NumPy allocation with WRITEABLE=False still lets its caller
    # re-enable writes. An immutable bytes backing prevents that as well.
    dtype = value.dtype.newbyteorder("=")
    storage = np.asarray(value, dtype=dtype, order="C").tobytes()
    return np.frombuffer(storage, dtype=dtype).reshape(value.shape)


@dataclass(frozen=True, slots=True, eq=False)
class CFDeployment:
    """Validated, owned read-only arrays in v1 live oldest-to-newest order."""

    v_mean: np.ndarray
    v_scale: np.ndarray
    v_weights: np.ndarray
    v_quadratic: bool
    v_lambda: float
    a_mean: np.ndarray
    a_scale: np.ndarray
    a_weights: np.ndarray
    a_quadratic: bool
    a_lambda: float
    retrieval_scale: np.ndarray
    v_keys: np.ndarray
    v_values: np.ndarray
    v_known: np.ndarray
    a_keys: np.ndarray
    a_values: np.ndarray
    a_known: np.ndarray
    version: int = 1

    def __post_init__(self):
        object.__setattr__(self, "version", _version(self.version))
        self._validate_head("v", 5)
        self._validate_head("a", 23)
        retrieval = self._store_array("retrieval_scale", (16, 5))
        if np.any(retrieval <= 0):
            raise ValueError("retrieval_scale must be positive")
        self._validate_bank("v", (16, 5), (16, 2), (16,))
        self._validate_bank("a", (23,), (1,), (1,))
        observed = self.v_values[self.v_known]
        labels, rays = observed.T
        if np.any((labels != 0) & (labels != 1)):
            raise ValueError("Known v_values safety labels must be 0 or 1")
        if np.any((rays < 0) | (rays != np.floor(rays))):
            raise ValueError("Known v_values ray counts must be nonnegative integers")

    def _store_array(self, name, shape, dtype=np.float64):
        value = _immutable_array(_array(getattr(self, name), name, shape, dtype))
        object.__setattr__(self, name, value)
        return value

    def _validate_head(self, prefix, width):
        quadratic_name = f"{prefix}_quadratic"
        lambda_name = f"{prefix}_lambda"
        quadratic = bool(_array(getattr(self, quadratic_name), quadratic_name, (), np.bool_))
        regularization = float(_array(getattr(self, lambda_name), lambda_name, ()))
        if regularization < 0:
            raise ValueError(f"{lambda_name} must be nonnegative")
        object.__setattr__(self, quadratic_name, quadratic)
        object.__setattr__(self, lambda_name, regularization)
        self._store_array(f"{prefix}_mean", (width,))
        scale = self._store_array(f"{prefix}_scale", (width,))
        if np.any(scale <= 0):
            raise ValueError(f"{prefix}_scale must be positive")
        products = width * (width + 1) // 2 if quadratic else 0
        self._store_array(f"{prefix}_weights", (width + products + 1,))

    def _validate_bank(self, prefix, key_shape, value_shape, known_shape):
        name = f"{prefix}_keys"
        keys = np.asarray(getattr(self, name))
        if keys.ndim != len(key_shape) + 1:
            raise ValueError(f"{name} must have shape (N, {', '.join(map(str, key_shape))})")
        if len(keys) > EXPERIENCE_CAPACITY:
            raise ValueError(f"{name} must have at most {EXPERIENCE_CAPACITY} live rows")
        count = len(keys)
        self._store_array(name, (count, *key_shape))
        self._store_array(f"{prefix}_values", (count, *value_shape))
        self._store_array(f"{prefix}_known", (count, *known_shape), np.bool_)

    def session(self):
        """Start one private CF instance from the immutable deployment."""
        view = LinearHead(self.v_mean, self.v_scale, self.v_weights, quadratic=self.v_quadratic,
                          regularization=self.v_lambda, view=True)
        action = LinearHead(self.a_mean, self.a_scale, self.a_weights, quadratic=self.a_quadratic,
                            regularization=self.a_lambda, view=False)
        result = CerebellarFlash(view, action, retrieval_scale=self.retrieval_scale)
        for bank, keys, values, known in (
            (result.views, self.v_keys, self.v_values, self.v_known),
            (result.actions, self.a_keys, self.a_values, self.a_known),
        ):
            count = len(keys)
            bank.keys[:count] = keys
            bank.values[:count] = values
            bank.known[:count] = known
            bank.writes = count
        return result


def load_cf_deployment(path):
    """Load a v1 NPZ with explicit parameters and no pickled objects."""
    loaded = np.load(path, allow_pickle=False)
    if not isinstance(loaded, np.lib.npyio.NpzFile):
        raise ValueError("CF deployment must be a v1 NPZ archive")
    names = tuple(field.name for field in fields(CFDeployment) if field.name != "version")
    with loaded as data:
        if set(data.files) != {*names, "version"} or len(data.files) != len(names) + 1:
            raise ValueError("CF deployment must contain exactly the v1 fields")
        version = _version(data["version"])
        return CFDeployment(**{name: data[name] for name in names}, version=version)
