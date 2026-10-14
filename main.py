"""
API de Consulta de Noticias del Delito — Fiscalía General del Ecuador.

Expone endpoints REST que envuelven el backend SIAF de la Fiscalía,
gestionando automáticamente la sesión Incapsula/Imperva.
"""

import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from fiscalia_api import IncapsulaSession, generate_search_pdf

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fiscalia_api")

# ── Sesión global ─────────────────────────────────────────────────────────
_session: IncapsulaSession | None = None
_last_refresh: datetime | None = None
_REFRESH_INTERVAL = timedelta(minutes=10)


async def get_session() -> IncapsulaSession:
    """Retorna la sesión Incapsula compartida, renovándola si está vencida."""
    global _session, _last_refresh

    assert _session is not None, "Sesión no inicializada"

    now = datetime.now(timezone.utc)
    if _last_refresh is None or (now - _last_refresh) > _REFRESH_INTERVAL:
        logger.info("Renovando sesión Incapsula (vencida)")
        await _session.refresh()
        _last_refresh = now

    return _session


# ── Ciclo de vida ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización / cierre de la aplicación."""
    global _session
    logger.info("Iniciando API de la Fiscalía…")
    _session = IncapsulaSession()
    await _session.start()
    _last_refresh = datetime.now(timezone.utc)
    yield
    logger.info("Deteniendo API de la Fiscalía…")
    await _session.close()


# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="API Consulta de Noticias del Delito — Fiscalía General del Ecuador",
    description=str(__doc__),
    version="0.1.0",
    lifespan=lifespan,
    contact={
        "name": "Fiscalía General del Estado — Datos Públicos",
        "url": "https://www.fiscalia.gob.ec/accesibilidad/consulta-de-noticias-del-delito/",
    },
    license_info={
        "name": "Creative Commons — Datos Públicos",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Rutas ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Verifica el estado del servicio.

    Retorna el estado actual y la última vez que se renovó la sesión
    con el backend SIAF.
    """
    session = await get_session()
    return {
        "estado": "ok",
        "sesion_activa": bool(session.client.cookies),
        "ultima_actualizacion": _last_refresh.isoformat() if _last_refresh else None,
    }


def _safe_filename(query: str) -> str:
    """Genera un nombre de archivo seguro a partir del criterio de búsqueda."""
    cleaned = re.sub(r"[^\w\-_]", "_", query).strip("_")
    return f"reporte_fiscalia_{cleaned or 'consulta'}.pdf"


@app.get(
    "/search",
    responses={
        200: {
            "content": {
                "application/json": {},
                "application/pdf": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                },
            },
            "description": "Resultados en formato JSON o documento PDF descargable.",
        }
    },
)
async def search(
    q: str = Query(
        ...,
        min_length=5,
        description=(
            "Criterio de búsqueda. Puede ser:\n"
            "  * Nombres y Apellidos: apellido1 apellido2 nombre1 nombre2\n"
            "  * Cédula (10 dígitos) o RUC (13 dígitos)\n"
            "  * Noticia del Delito (15 dígitos)\n"
            "  * Placa: ABC0123\n"
            "  * Nro. de Oficio (Parte policial)\n"
            "Mínimo 5 caracteres."
        ),
    ),
    format: str = Query(
        "json",
        pattern="^(json|pdf)$",
        description="Formato de respuesta deseado: 'json' (por defecto) o 'pdf'.",
    ),
):
    """Busca noticias del delito por cualquier criterio.

    Realiza una consulta en el Sistema Integrado de Actuaciones Fiscales
    (SIAF) de la Fiscalía General del Estado. Retorna los resultados en
    formato JSON estructurado o como documento PDF descargable.
    """
    try:
        session = await get_session()
        result = await session.search(q)

        if format == "pdf":
            pdf_bytes = generate_search_pdf(query=q, data=result)
            filename = _safe_filename(q)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"',
                },
            )

        return result

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.exception("Error en búsqueda")
        raise HTTPException(
            status_code=502,
            detail=f"Error al consultar el backend SIAF: {e}",
        )


@app.get(
    "/search/pdf",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/pdf": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                }
            },
            "description": "Reporte formal en formato PDF generado exitosamente.",
        }
    },
)
async def search_pdf(
    q: str = Query(
        ...,
        min_length=5,
        description=(
            "Criterio de búsqueda (Cédula, RUC, Nombres, NDD, Placa u Oficio). "
            "Genera y retorna un documento PDF formal."
        ),
    ),
):
    """Genera un reporte PDF con el resultado de la consulta en la Fiscalía."""
    try:
        session = await get_session()
        result = await session.search(q)
        pdf_bytes = generate_search_pdf(query=q, data=result)
        filename = _safe_filename(q)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        logger.exception("Error generando reporte PDF")
        raise HTTPException(
            status_code=502,
            detail=f"Error al consultar el backend SIAF: {e}",
        )


# ── Punto de entrada ──────────────────────────────────────────────────────
def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
