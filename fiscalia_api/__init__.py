"""Fiscalía API - Consulta de Noticias del Delito."""

from .connector import IncapsulaSession
from .pdf import generate_search_pdf
from .serializer import prepare_search_query

__all__ = ["IncapsulaSession", "generate_search_pdf", "prepare_search_query"]
