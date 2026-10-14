"""Generador de reportes PDF para la API de Consulta de Noticias del Delito.

Convierte los resultados devueltos por el SIAF de la Fiscalía en un documento
PDF estructurado y con formato institucional.
"""

import html
import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class NumberedCanvas(canvas.Canvas):
    """Canvas de dos pasadas para calcular e imprimir 'Página X de Y' y pie de página."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_decorations(page_count)
            super().showPage()
        super().save()

    def _draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))

        # Línea divisoria de pie de página
        self.setStrokeColor(colors.HexColor("#D1D5DB"))
        self.setLineWidth(0.75)
        self.line(36, 38, 576, 38)

        # Pie de página
        footer_text = "Fiscalía General del Estado del Ecuador — Sistema Integrado de Actuaciones Fiscales (SIAF)"
        self.drawString(36, 26, footer_text)
        page_str = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(576, 26, page_str)

        self.restoreState()


def _esc(val: Any) -> str:
    """Escapa caracteres especiales para ser interpretados de forma segura por ReportLab."""
    if val is None:
        return ""
    return html.escape(str(val))


def generate_search_pdf(query: str, data: dict[str, Any]) -> bytes:
    """Genera un archivo PDF binario a partir del resultado de la búsqueda en SIAF.

    Args:
        query: Criterio de búsqueda ingresado por el usuario.
        data: Diccionario con la respuesta estructurada de SIAF (exito, resultados, total, mensaje).

    Returns:
        Bytes del archivo PDF generado.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=48,
    )

    styles = getSampleStyleSheet()

    # Estilos personalizados
    style_inst_title = ParagraphStyle(
        "InstTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0B2545"),
        alignment=1,  # Centrado
    )
    style_subtitle = ParagraphStyle(
        "InstSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#134074"),
        alignment=1,
    )
    style_meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1F2937"),
    )
    style_meta_val = ParagraphStyle(
        "MetaVal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#374151"),
    )
    style_card_title = ParagraphStyle(
        "CardTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.white,
    )
    style_sec_title = ParagraphStyle(
        "SecTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#0B2545"),
    )
    style_tbl_header = ParagraphStyle(
        "TblHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    style_tbl_cell = ParagraphStyle(
        "TblCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#1F2937"),
    )
    style_tbl_cell_bold = ParagraphStyle(
        "TblCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#1F2937"),
    )
    style_no_results = ParagraphStyle(
        "NoResults",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#991B1B"),
        alignment=1,
    )

    story = []

    # ── Encabezado Institucional ────────────────────────────────────────────
    story.append(Paragraph("REPÚBLICA DEL ECUADOR", style_subtitle))
    story.append(Paragraph("FISCALÍA GENERAL DEL ESTADO", style_inst_title))
    story.append(Paragraph("SISTEMA INTEGRADO DE ACTUACIONES FISCALES (SIAF)", style_subtitle))
    story.append(Paragraph("Reporte de Consulta de Noticias del Delito", style_meta_label))
    story.append(Spacer(1, 10))

    # ── Tarjeta de Metadatos de la Búsqueda ─────────────────────────────────
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_results = data.get("total", 0)

    meta_table_data = [
        [
            Paragraph("<b>Criterio Consultado:</b>", style_meta_label),
            Paragraph(_esc(query), style_meta_val),
            Paragraph("<b>Fecha de Emisión:</b>", style_meta_label),
            Paragraph(now_str, style_meta_val),
        ],
        [
            Paragraph("<b>Total Registros:</b>", style_meta_label),
            Paragraph(f"<b>{total_results}</b> resultado(s)", style_meta_val),
            Paragraph("<b>Estado Consulta:</b>", style_meta_label),
            Paragraph(_esc(data.get("mensaje", "OK")), style_meta_val),
        ],
    ]

    meta_table = Table(meta_table_data, colWidths=[110, 160, 110, 160])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D1D5DB")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 12))

    resultados = data.get("resultados", [])

    # ── Caso: Sin Resultados ────────────────────────────────────────────────
    if not resultados:
        empty_box_data = [
            [
                Paragraph(
                    f"No se encontraron coincidencias en la base de datos de la Fiscalía "
                    f"para el criterio de búsqueda: <b>{_esc(query)}</b>.",
                    style_no_results,
                )
            ]
        ]
        empty_table = Table(empty_box_data, colWidths=[540])
        empty_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#FCA5A5")),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ])
        )
        story.append(empty_table)

    # ── Caso: Con Resultados ────────────────────────────────────────────────
    for idx, item in enumerate(resultados, start=1):
        info = item.get("informacion", {})
        sujetos = item.get("sujetos", [])
        vehiculos = item.get("vehiculos", [])

        card_elements = []

        # Título del Bloque NDD
        header_text = info.get("noticia_del_delito") or f"NOTICIA DEL DELITO #{idx}"
        title_table = Table(
            [[Paragraph(f"<b>[{idx}/{total_results}] {_esc(header_text)}</b>", style_card_title)]],
            colWidths=[540],
        )
        title_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#134074")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#134074")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        card_elements.append(title_table)

        # Campos clave de Información General
        info_keys = [k for k in info.keys() if k not in ("noticia_del_delito", "ndd")]
        info_rows = []
        for i in range(0, len(info_keys), 2):
            k1 = info_keys[i]
            v1 = info.get(k1, "")
            row = [
                Paragraph(f"<b>{_esc(k1)}:</b>", style_tbl_cell_bold),
                Paragraph(_esc(v1), style_tbl_cell),
            ]
            if i + 1 < len(info_keys):
                k2 = info_keys[i + 1]
                v2 = info.get(k2, "")
                row.extend([
                    Paragraph(f"<b>{_esc(k2)}:</b>", style_tbl_cell_bold),
                    Paragraph(_esc(v2), style_tbl_cell),
                ])
            else:
                row.extend([Paragraph("", style_tbl_cell), Paragraph("", style_tbl_cell)])
            info_rows.append(row)

        if info_rows:
            info_table = Table(info_rows, colWidths=[100, 170, 100, 170])
            info_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFFFF")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ])
            )
            card_elements.append(info_table)

        # Tabla de Sujetos
        if sujetos:
            card_elements.append(Spacer(1, 4))
            subj_headers = list(sujetos[0].keys())
            subj_rows = [
                [Paragraph(f"<b>{_esc(h)}</b>", style_tbl_header) for h in subj_headers]
            ]
            for s in sujetos:
                subj_rows.append([
                    Paragraph(_esc(s.get(h, "")), style_tbl_cell) for h in subj_headers
                ])

            # Calcular anchos de columna dinámicamente si son las 3 estándar
            if subj_headers == ["CEDULA", "NOMBRES COMPLETOS", "ESTADO"]:
                subj_col_widths = [110, 280, 150]
            else:
                w = 540 / len(subj_headers)
                subj_col_widths = [w] * len(subj_headers)

            subj_table = Table(subj_rows, colWidths=subj_col_widths)
            subj_style = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4ED8")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#93C5FD")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
            for r_idx in range(1, len(subj_rows)):
                if r_idx % 2 == 0:
                    subj_style.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#F8FAFC")))
            subj_table.setStyle(TableStyle(subj_style))
            card_elements.append(subj_table)

        # Tabla de Vehículos (si existen)
        if vehiculos:
            card_elements.append(Spacer(1, 4))
            veh_headers = list(vehiculos[0].keys())
            veh_rows = [
                [Paragraph(f"<b>{_esc(h)}</b>", style_tbl_header) for h in veh_headers]
            ]
            for v in vehiculos:
                veh_rows.append([
                    Paragraph(_esc(v.get(h, "")), style_tbl_cell) for h in veh_headers
                ])

            w_veh = 540 / max(len(veh_headers), 1)
            veh_table = Table(veh_rows, colWidths=[w_veh] * len(veh_headers))
            veh_style = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#99F6E4")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
            for r_idx in range(1, len(veh_rows)):
                if r_idx % 2 == 0:
                    veh_style.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#F0FDFA")))
            veh_table.setStyle(TableStyle(veh_style))
            card_elements.append(veh_table)

        card_elements.append(Spacer(1, 10))
        story.extend(card_elements)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
