"""Vercel-compatible ASGI entrypoint."""

from partner_reports.config import get_settings
from partner_reports.main import create_app

app = create_app(get_settings())
