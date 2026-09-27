"""Portable query-aware graph inference; no training-framework imports."""

from .bindings import BindingResult, ScoredBinding, iter_score_bindings, score_bindings
from .cache import BindingCache, CacheInfo
from .graph import GraphSnapshot
from .model import ExplicitPathModel, GraphModel, Limits, ResourceLimitError, SourceFeatures
from .neighborhood import NeighborhoodModel
from .pipeline import GraphPipeline
from .plan import CostEstimate, PlanResult, PlanStatistics, Prediction, QueryPlan
from .session import LinkQuery, LinkResult, Profile, QueryResult, Session

__all__ = [
    "BindingCache",
    "BindingResult",
    "CacheInfo",
    "CostEstimate",
    "ExplicitPathModel",
    "GraphModel",
    "GraphPipeline",
    "GraphSnapshot",
    "Limits",
    "LinkQuery",
    "LinkResult",
    "NeighborhoodModel",
    "PlanResult",
    "PlanStatistics",
    "Prediction",
    "Profile",
    "QueryPlan",
    "QueryResult",
    "ResourceLimitError",
    "ScoredBinding",
    "Session",
    "SourceFeatures",
    "iter_score_bindings",
    "score_bindings",
]

__version__ = "1.0.0.dev1"
