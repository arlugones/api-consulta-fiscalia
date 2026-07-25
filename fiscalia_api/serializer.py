"""Utilidades de serialización PHP para la API de la Fiscalía.

El backend de la Fiscalía utiliza el formato PHP serialize() para su
parámetro de búsqueda.  Este módulo provee una implementación en Python
compatible con la función serialize() del frontend original.
"""

import re


def php_serialize_array(values: list[str]) -> str:
    """Serializa una lista de cadenas a formato PHP array.

    Compatible con la función serialize() del JavaScript original:
      function serialize(arr) {
        var res = 'a:' + arr.length + ':{';
        for (i = 0; i < arr.length; i++) {
          res += 'i:' + i + ';s:' + arr[i].length + ':"' + arr[i] + '";';
        }
        res += '}';
        return res;
      }

    Args:
        values: Lista de tokens a serializar.

    Returns:
        Cadena serializada en PHP, ej: "a:2:{i:0;s:5:"PEREZ";i:1;s:5:"GOMEZ";}"
    """
    parts = [f'a:{len(values)}:{{']
    for i, v in enumerate(values):
        parts.append(f'i:{i};s:{len(v)}:"{v}";')
    parts.append('}')
    return ''.join(parts)


def prepare_search_query(raw: str) -> str:
    """Transforma una consulta de usuario al parámetro serializado PHP.

    Aplica las mismas transformaciones que la función JS mirar():
      1. Recorta espacios
      2. Reemplaza espacios y comas por '*'
      3. Divide por '*' en tokens
      4. Serializa a formato PHP array

    Args:
        raw: Cadena de búsqueda ingresada por el usuario.

    Returns:
        Parámetro serializado PHP listo para el query param businfo=.

    Raises:
        ValueError: Si la consulta está vacía o tiene menos de 5 caracteres.
    """
    txt = raw.strip()
    if not txt:
        raise ValueError("Debe ingresar algún criterio para la búsqueda")
    if len(txt) < 5:
        raise ValueError("Debe ingresar al menos 5 caracteres")

    txt = re.sub(r'[ ,]+', '*', txt)
    tokens = [t for t in txt.split('*') if t]

    # Validar: solo se permite un NDD de 15 dígitos
    ndd_count = sum(1 for t in tokens if re.match(r'^\d{15}$', t))
    if ndd_count > 1:
        raise ValueError("Solo se puede ingresar una noticia del delito")

    return php_serialize_array(tokens)
