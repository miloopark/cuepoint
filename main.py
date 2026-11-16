"""Vercel entrypoint: serves the FastAPI app as a Python function on Fluid Compute.

The real application lives in api/src/cuepoint_api; requirements.txt installs
./api and ./analysis as packages, so this file only has to re-export the app."""

from cuepoint_api.main import app  # noqa: F401
