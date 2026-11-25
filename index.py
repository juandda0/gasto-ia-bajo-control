"""Punto de entrada para Vercel: expone la misma app de servidor.py."""

import os

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

from servidor import app  # noqa: E402,F401
