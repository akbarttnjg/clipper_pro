"""Dependency injection point for A. Does not access app globals.

A may supply a FastAPI APIRouter factory taking the host API below. B mounts
it at startup. Missing optional components never produce fake analysis results.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class AnalysisHost:
    snapshot: Callable
    submit_changes: Callable
    get_words_page: Callable
    run_stage: Callable


def mount(app, host, router_factory=None):
    if router_factory is not None:
        app.include_router(router_factory(host), prefix='/api/analysis')
