"""Conector HTTP para el backend SIAF de la Fiscalía.

Gestiona la sesión con el WAF Incapsula/Imperva y se comunica
con el endpoint info_mod.php del SIAF.
"""

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .serializer import prepare_search_query

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────────────────
SIAF_BASE = "https://www.gestiondefiscalias.gob.ec/siaf"
INDEX_URL = f"{SIAF_BASE}/informacion/web/noticiasdelito/index.php"
SEARCH_URL = f"{SIAF_BASE}/comunes/noticiasdelito/info_mod.php"
REFERER = "https://www.fiscalia.gob.ec/accesibilidad/consulta-de-noticias-del-delito/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

FISCALIA_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-EC,es;q=0.9,en;q=0.8",
    "Referer": REFERER,
}


class IncapsulaSession:
    """Gestiona una sesión HTTP protegida por Incapsula.

    El backend SIAF está detrás del WAF Imperva/Incapsula (visible por la
    cookie ``incap_ses_*``). Acceder directamente al ``index.php`` del iframe
    desde un script resulta bloqueado, pero la cookie que establece la página
    padre (fiscalia.gob.ec) concede el acceso.

    Esta clase:
    * Visita el index.php del SIAF con el Referer de la página padre para
      obtener y mantener una cookie de sesión Incapsula válida.
    * Usa un solo ``httpx.AsyncClient`` con persistencia de cookies.
    * Expone ``refresh()`` para renovar la sesión y ``search()`` para
      ejecutar consultas.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._last_refresh_url: Optional[str] = None

    # ── Ciclo de vida ──────────────────────────────────────────────────

    async def start(self) -> None:
        """Crea el cliente HTTP e inicia la sesión."""
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            headers=FISCALIA_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=15.0),
        )
        await self.refresh()

    async def close(self) -> None:
        """Cierra el cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("IncapsulaSession no iniciada")
        return self._client

    # ── Gestión de sesión ─────────────────────────────────────────────

    async def refresh(self) -> None:
        """Renueva la sesión Incapsula visitando el index.php del SIAF.

        Envía una petición al ``index.php`` del iframe desde el Referer
        de fiscalia.gob.ec, lo que provoca que Incapsula establezca o
        renueve la cookie de sesión.  Llamar periódicamente
        (ej. cada 10-15 minutos) para mantener la sesión activa.
        """
        resp = await self.client.get(INDEX_URL)
        resp.raise_for_status()
        self._last_refresh_url = str(resp.url)
        logger.info(
            "Sesión Incapsula renovada (%s, cookies=%s)",
            resp.status_code,
            dict(self.client.cookies),
        )

    # ── Búsqueda ─────────────────────────────────────────────────────

    async def search(self, query: str) -> dict:
        """Ejecuta una búsqueda en la base de datos de Noticias del Delito del SIAF.

        Args:
            query: Cadena de búsqueda (nombre, placa, NDD, cédula, etc.)

        Returns:
            Un diccionario con:
                * ``exito`` — ``True`` si la solicitud tuvo éxito
                * ``resultados`` — lista de resultados parseados
                * ``mensaje`` — mensaje legible del backend
        """
        businfo = prepare_search_query(query)
        url = f"{SEARCH_URL}?businfo={httpx.URL(businfo)}"

        resp = await self.client.get(url)
        resp.raise_for_status()

        html = resp.text.strip()
        return self._parse_results(html)

    # ── Parseo de respuestas ──────────────────────────────────────────

    @staticmethod
    def _parse_results(html: str) -> dict:
        """Parsea el HTML devuelto por info_mod.php a JSON estructurado.

        El backend retorna grupos por NDD.  Cada NDD se identifica por
        un ``<th>`` que contiene ``NOTICIA DEL DELITO Nro.``, seguido de
        su tabla de información, una tabla SUJETOS y (opcionalmente)
        una tabla VEHICULOS.
        """
        soup = BeautifulSoup(html, "lxml")

        # Verificar mensaje de "sin resultados"
        no_results = soup.find(
            "h2", string=lambda t: t and "no existen coincidencias" in t.lower()
        )
        if no_results:
            return {
                "exito": True,
                "resultados": [],
                "total": 0,
                "mensaje": "No existen coincidencias para los criterios ingresados",
            }

        # ── Encontrar límites de NDD ─────────────────────────────────
        all_ths = soup.find_all("th")
        ndd_boundaries: list[int] = []
        for idx, th in enumerate(all_ths):
            text = th.get_text(strip=True)
            if text.startswith("NOTICIA DEL DELITO"):
                ndd_boundaries.append(idx)

        if not ndd_boundaries:
            return {
                "exito": True,
                "resultados": [],
                "total": 0,
                "mensaje": "No se encontraron resultados",
            }

        # ── Funciones auxiliares ─────────────────────────────────────

        def _parse_info_table(table) -> dict[str, str]:
            """Extrae pares clave-valor de la tabla de información del NDD."""
            info: dict[str, str] = {}
            tbody = table.find("tbody")
            if not tbody:
                return info
            for tr in tbody.find_all("tr"):
                tds = tr.find_all("td")
                texts = [td.get_text(strip=True) for td in tds]
                # Filtrar celdas vacías (placeholder de imagen)
                texts = [t for t in texts if t]
                i = 0
                while i < len(texts):
                    label = texts[i].rstrip(":")
                    if i + 1 < len(texts):
                        info[label] = texts[i + 1]
                        i += 2
                    else:
                        info[label] = ""
                        i += 1
            return info

        def _parse_subjects_table(table) -> list[dict]:
            """Extrae las filas de sujetos de una tabla SUJETOS."""
            rows: list[dict] = []
            thead = table.find("thead")
            if not thead:
                return rows
            header_rows = thead.find_all("tr")
            if len(header_rows) < 2:
                return rows
            col_headers = [
                td.get_text(strip=True) for td in header_rows[1].find_all("td")
            ]
            tbody = table.find("tbody")
            if not tbody:
                return rows
            for tr in tbody.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if col_headers and cells and any(c.strip() for c in cells):
                    rows.append(dict(zip(col_headers, cells)))
            return rows

        def _parse_vehicles_table(table) -> list[dict]:
            """Extrae las filas de vehículos de una tabla VEHICULOS."""
            rows: list[dict] = []
            thead = table.find("thead")
            if not thead:
                return rows
            header_rows = thead.find_all("tr")
            if len(header_rows) < 2:
                return rows
            col_headers = [
                td.get_text(strip=True) for td in header_rows[1].find_all("td")
            ]
            tbody = table.find("tbody")
            if not tbody:
                return rows
            for tr in tbody.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if col_headers and cells and any(c.strip() for c in cells):
                    rows.append(dict(zip(col_headers, cells)))
            return rows

        def _table_classifier(table) -> str:
            """Clasifica una tabla como 'info', 'sujetos', 'vehiculos' o 'unknown'."""
            thead = table.find("thead")
            if not thead:
                return "unknown"
            header_rows = thead.find_all("tr")
            if not header_rows:
                return "unknown"
            first_th = header_rows[0].find("th")
            if first_th:
                text = first_th.get_text(strip=True)
                if text.startswith("NOTICIA DEL DELITO"):
                    return "info"
            first_text = header_rows[0].get_text(strip=True)
            if first_text == "SUJETOS":
                return "sujetos"
            if first_text == "VEHICULOS":
                return "vehiculos"
            return "unknown"

        # ── Construir resultados ──────────────────────────────────────
        all_tables = soup.find_all("table")
        results: list[dict] = []

        # Convertir cada límite de NDD en el índice de su tabla padre
        ndd_table_indices: list[int] = []
        for th_idx in ndd_boundaries:
            th = all_ths[th_idx]
            table = th.find_parent("table")
            if table:
                try:
                    ndd_table_indices.append(all_tables.index(table))
                except ValueError:
                    pass

        # Agrupar tablas por NDD
        for i in range(len(ndd_table_indices)):
            start = ndd_table_indices[i]
            end = ndd_table_indices[i + 1] if i + 1 < len(ndd_table_indices) else len(all_tables)
            group_tables = all_tables[start:end]

            ndd_info: dict[str, str] = {}
            subjects: list[dict] = []
            vehicles: list[dict] = []

            for tbl in group_tables:
                kind = _table_classifier(tbl)
                if kind == "info":
                    ndd_info = _parse_info_table(tbl)
                    thead = tbl.find("thead")
                    if thead:
                        th = thead.find("th")
                        if th:
                            ndd_info["noticia_del_delito"] = th.get_text(strip=True)
                            m = re.search(
                                r"NOTICIA DEL DELITO\s+Nro\.\s+(\d{15})",
                                ndd_info["noticia_del_delito"],
                            )
                            if m:
                                ndd_info["ndd"] = m.group(1)
                elif kind == "sujetos":
                    subjects.extend(_parse_subjects_table(tbl))
                elif kind == "vehiculos":
                    vehicles.extend(_parse_vehicles_table(tbl))

            if ndd_info:
                results.append({
                    "informacion": ndd_info,
                    "sujetos": subjects,
                    "vehiculos": vehicles,
                })

        return {
            "exito": True,
            "resultados": results,
            "total": len(results),
            "mensaje": f"Se encontraron {len(results)} resultado(s)",
        }
