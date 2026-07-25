# API de Consulta de Noticias del Delito — Fiscalía General del Ecuador

API wrapper que permite consultar la base de datos de noticias del delito del
**Sistema Integrado de Actuaciones Fiscales (SIAF)** de la Fiscalía General del
Estado del Ecuador a través de un endpoint REST moderno, evitando la interfaz
web tradicional.

## Endpoints

### `GET /search?q=<criterio>`

Busca noticias del delito por cualquier criterio aceptado por el SIAF:

| Criterio | Ejemplo | Descripción |
|----------|---------|-------------|
| Cédula | `1712345678` | 10 dígitos |
| RUC | `1712345678001` | 13 dígitos |
| Nombres | `PEREZ GOMEZ` | Mínimo 5 caracteres |
| Noticia del Delito | `17010011223344` | 15 dígitos (solo uno) |
| Placa | `ABC0123` | Formato ecuatoriano |
| Nro. Oficio | `1240` | Parte policial |

**Respuesta:**
```json
{
  "exito": true,
  "resultados": [
    {
      "informacion": {
        "noticia_del_delito": "NOTICIA DEL DELITO Nro. 090101815110538 - DELITO FLAGRANTE",
        "ndd": "090101815110538",
        "LUGAR": "GUAYAS - GUAYAQUIL",
        "FECHA": "2015-11-04",
        "HORA": "16:38:30",
        "DIGITADOR": "YEROVI RIOFRIO GIAN PAOLO",
        "DELITO": "INGRESO DE ARTÍCULOS PROHIBIDOS(3409)",
        "Nro. OFICIO": "SN-PARTE DE DETENCION",
        "UNIDAD": "FISCALIA DE INVESTIGACION DE FLAGRANCIA - ..."
      },
      "sujetos": [
        {"CEDULA": "1760010970001", "NOMBRES COMPLETOS": "FISCALIA GENERAL DEL ESTADO", "ESTADO": "DENUNCIANTE"},
        {"CEDULA": "0907236111", "NOMBRES COMPLETOS": "PEREZ GOMEZ TEODORA NARCISA", "ESTADO": "PROCESADO"}
      ],
      "vehiculos": []
    }
  ],
  "total": 17,
  "mensaje": "Se encontraron 17 resultado(s)"
}
```

Cuando no hay resultados:
```json
{
  "exito": true,
  "resultados": [],
  "total": 0,
  "mensaje": "No existen coincidencias para los criterios ingresados"
}
```

### `GET /health`

Estado del servicio:
```json
{
  "estado": "ok",
  "sesion_activa": true,
  "ultima_actualizacion": "2026-07-25T07:18:09.249462+00:00"
}
```

## Inicio rápido

```bash
# Instalar dependencias
uv sync

# Iniciar servidor
uv run uvicorn main:app --reload --port 8000

# Consultar por cédula
curl "http://localhost:8000/search?q=1712345678"

# Consultar por nombres
curl "http://localhost:8000/search?q=PEREZ%20GOMEZ"

# Consultar por placa
curl "http://localhost:8000/search?q=ABC0123"
```

## Arquitectura

```
api_consulta_fiscalia/
├── main.py                    # FastAPI app + rutas
├── pyproject.toml             # Dependencias
├── README.md
└── fiscalia_api/
    ├── __init__.py
    ├── serializer.py          # Serialización PHP compatible con el backend
    └── connector.py           # Cliente HTTP + gestión de sesión Incapsula
```

## Cómo funciona

1. La página `https://www.fiscalia.gob.ec/accesibilidad/consulta-de-noticias-del-delito/`
   carga un iframe desde `https://www.gestiondefiscalias.gob.ec/siaf/...`
2. El backend SIAF está protegido por **Imperva/Incapsula WAF** — bloquea
   accesos directos sin cookie de sesión.
3. La API sortea esta barrera **sin CAPTCHA**:
   - Visita el `index.php` del iframe con el `Referer` apropiado
   - Obtiene y mantiene automáticamente la cookie `incap_ses_*`
   - Renueva la sesión cada 10 minutos
4. La búsqueda se envía serializada en **formato PHP `serialize()`**:
   `a:2:{i:0;s:5:"PEREZ";i:1;s:5:"GOMEZ";}`
5. La respuesta HTML se parsea a JSON estructurado con BeautifulSoup

## Stack

- **FastAPI** + uvicorn
- **httpx** — cliente HTTP async con persistencia de cookies
- **BeautifulSoup** + lxml — parser HTML
- **Python 3.13**

## Notas

- No hay límite de tasa conocido, pero se recomienda no exceder ~1 req/s
- Los datos son públicos según los arts. 76.7.d) Constitución, 13 COFJ,
  y 421 COIP
- El uso de la información es responsabilidad del consumidor — no usar con
  fines discriminatorios
