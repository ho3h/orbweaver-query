"""Shared validation and immutable numeric storage."""

import numpy as np


def positive_int(value, name, *, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def immutable_array(value, dtype=None):
    """Bytes backing prevents callers re-enabling writes on public arrays."""
    array = np.ascontiguousarray(value, dtype=dtype)
    return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)


def names(values, name, *, allow_empty=False):
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a sequence of strings, not a string")
    values = tuple(values)
    if (not values and not allow_empty) or any(type(v) is not str or not v for v in values):
        raise ValueError(f"{name} must contain nonempty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    return values
