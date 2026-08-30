"""Marker so Poetry bundles skills/ into the wheel as emdx/skills.

The Claude Code plugin ignores this file (it only reads subdirectories
containing SKILL.md). poetry-core refuses to package a directory without
at least one .py file, and pyproject.toml maps this directory to
emdx/skills in built distributions so `emdx setup` can install the
skills from a pip/uv install. See issue #1033.
"""
