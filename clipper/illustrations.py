"""Compatibility facade. Catalog is owned by A; scheduling is owned by B."""
from . import illustration_catalog as catalog
from .illustration_catalog import recipe_path, propose, stock, editorial
from .illustration_schedule import attach, credits


def prepare(words, clip, cfg, progress=lambda p,m:None, refresh=False, *, input_fingerprint=None):
    return catalog.prepare(words, clip, cfg, progress, refresh, proposer=propose,input_fingerprint=input_fingerprint)
