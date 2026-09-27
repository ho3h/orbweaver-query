"""Portable query-aware graph inference; no training-framework imports."""

from .bindings import BindingResult, ScoredBinding, iter_score_bindings, score_bindings
from .graph import GraphSnapshot
from .model import ExplicitPathModel, GraphModel, Limits, ResourceLimitError
from .session import LinkQuery, LinkResult, Profile, QueryResult, Session

__all__ = [
    "BindingResult",
    "ExplicitPathModel",
    "GraphModel",
    "GraphSnapshot",
    "Limits",
    "LinkQuery",
    "LinkResult",
    "Profile",
    "QueryResult",
    "ResourceLimitError",
    "ScoredBinding",
    "Session",
    "iter_score_bindings",
    "score_bindings",
]

__version__ = "0.1.0"
