"""Explicit module boundaries for the TCG grader SELFREFINE runtime.

This package does not own persisted learning state.  It only describes and validates
which top-level subsystem owns each source/state file so grading, collection, repair,
and orchestration can evolve independently.
"""
from .registry import MODULES, ModuleSpec, validate_registry

__all__ = ["MODULES", "ModuleSpec", "validate_registry"]
