"""Portable query-aware graph inference; no training-framework imports."""

from .bindings import BindingResult, ScoredBinding, iter_score_bindings, score_bindings
from .cache import BindingCache, CacheInfo
from .graph import GraphSnapshot
from .model import ExplicitPathModel, GraphModel, Limits, ResourceLimitError, SourceFeatures
from .neighborhood import NeighborhoodModel
from .session import LinkQuery, LinkResult, Profile, QueryResult, Session

__all__ = [
    "BindingCache",
    "BindingResult",
    "CacheInfo",
    "ExplicitPathModel",
    "GraphModel",
    "GraphSnapshot",
    "Limits",
    "LinkQuery",
    "LinkResult",
    "NeighborhoodModel",
    "Profile",
    "QueryResult",
    "ResourceLimitError",
    "ScoredBinding",
    "Session",
    "SourceFeatures",
    "iter_score_bindings",
    "score_bindings",
]

__version__ = "1.0.0.dev1"
