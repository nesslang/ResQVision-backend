"""
ResQVision 2.0 — Reports API
--------------------------------

Handles:
    GET    /api/v1/reports/
    POST   /api/v1/reports/generate
    GET    /api/v1/reports/{report_id}
    GET    /api/v1/reports/download/{report_id}
    GET    /api/v1/reports/{report_id}/download
    DELETE /api/v1/reports/{report_id}

PDF generation is handled using ReportLab.

Generated PDFs are stored in:

    <project-root>/generated_reports/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.database import Base, get_db
from app.models.models import RelocationSite, Village


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


# ============================================================
# GENERATED PDF DIRECTORY
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

GENERATED_REPORTS_DIR = PROJECT_ROOT / "generated_reports"

GENERATED_REPORTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# DATABASE MODEL
# ============================================================

class Report(Base):
    """
    Database model for generated reports.

    This uses SQLAlchemy 2.x typed mappings so that
    Pylance understands:

        report.title       -> str
        report.status      -> str
        report.download_url -> Optional[str]

    instead of treating them as Column[str].
    """

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    report_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="full",
    )

    format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pdf",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="READY",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    district: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    period: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    download_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


# ============================================================
# DISPLAY HELPERS
# ============================================================

REPORT_TYPE_LABELS: dict[str, str] = {
    "hazard": "Hazard Report",
    "priority": "Relocation Priority Report",
    "capacity": "Relocation Capacity Report",
    "relocation": "Relocation Report",
    "full": "Situation Report",
}


def display_type(report_type: str) -> str:
    return REPORT_TYPE_LABELS.get(
        report_type,
        "Situation Report",
    )


def safe_filename(value: str) -> str:
    """
    Convert a report title into a safe filename.
    """

    value = value.strip()

    value = re.sub(
        r"[^a-zA-Z0-9_\-]+",
        "_",
        value,
    )

    value = re.sub(
        r"_+",
        "_",
        value,
    )

    value = value.strip("_")

    if not value:
        value = "resqvision_report"

    return value[:120]


def report_file_path(report_id: int) -> Path:
    """
    Returns the expected PDF path for a report.
    """

    return GENERATED_REPORTS_DIR / f"report_{report_id}.pdf"


def make_download_url(
    request: Request,
    report_id: int,
) -> str:
    """
    Build an absolute URL that works with localhost,
    LAN IP addresses, deployment servers, etc.
    """

    base_url = str(request.base_url).rstrip("/")

    return (
        f"{base_url}"
        f"/api/v1/reports/download/{report_id}"
    )


# ============================================================
# SERIALIZATION
# ============================================================

def serialize_report(
    report: Report,
    request: Request,
) -> dict:
    """
    Convert SQLAlchemy Report object into JSON-safe data.
    """

    download_url = report.download_url

    # Existing reports may have NULL download_url because
    # they were created before PDF generation was implemented.
    #
    # Give them a valid download endpoint anyway.
    if report.format.lower() == "pdf":
        download_url = make_download_url(
            request,
            report.id,
        )

    return {
        "id": report.id,
        "title": report.title,
        "type": display_type(report.report_type),
        "date": (
            report.created_at.strftime("%d %b %Y")
            if report.created_at
            else ""
        ),
        "status": report.status,
        "description": report.description or "",
        "report_type": report.report_type,
        "format": report.format,
        "district": report.district,
        "period": report.period,
        "download_url": download_url,
    }


# ============================================================
# PDF STYLES
# ============================================================

def get_pdf_styles():
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ResQTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        alignment=TA_CENTER,
        spaceAfter=8 * mm,
    )

    subtitle_style = ParagraphStyle(
        "ResQSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10 * mm,
    )

    heading_style = ParagraphStyle(
        "ResQHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=6 * mm,
        spaceAfter=3 * mm,
    )

    body_style = ParagraphStyle(
        "ResQBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=3 * mm,
    )

    small_style = ParagraphStyle(
        "ResQSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64748b"),
    )

    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "heading": heading_style,
        "body": body_style,
        "small": small_style,
    }


# ============================================================
# PDF TABLE HELPER
# ============================================================

def make_table(
    rows: list[list[str]],
    col_widths: Optional[list[float]] = None,
) -> Table:

    table = Table(
        rows,
        colWidths=col_widths,
        repeatRows=1,
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#0f172a"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "FONTNAME",
                    (0, 1),
                    (-1, -1),
                    "Helvetica",
                ),
                (
                    "BACKGROUND",
                    (0, 1),
                    (-1, -1),
                    colors.white,
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#f8fafc"),
                    ],
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.HexColor("#cbd5e1"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    return table


# ============================================================
# PDF HEADER / FOOTER
# ============================================================

def draw_page_header_footer(
    canvas,
    document,
):
    canvas.saveState()

    width, height = A4

    # Header line
    canvas.setStrokeColor(
        colors.HexColor("#e2e8f0")
    )

    canvas.line(
        18 * mm,
        height - 15 * mm,
        width - 18 * mm,
        height - 15 * mm,
    )

    canvas.setFont(
        "Helvetica-Bold",
        8,
    )

    canvas.setFillColor(
        colors.HexColor("#475569")
    )

    canvas.drawString(
        18 * mm,
        height - 11 * mm,
        "ResQVision 2.0",
    )

    # Footer
    canvas.line(
        18 * mm,
        15 * mm,
        width - 18 * mm,
        15 * mm,
    )

    canvas.setFont(
        "Helvetica",
        7.5,
    )

    canvas.setFillColor(
        colors.HexColor("#64748b")
    )

    canvas.drawString(
        18 * mm,
        9 * mm,
        "Ministry of Home Affairs — Disaster Management",
    )

    canvas.drawRightString(
        width - 18 * mm,
        9 * mm,
        f"Page {document.page}",
    )

    canvas.restoreState()


# ============================================================
# DATA HELPERS
# ============================================================

def get_village_query(
    db: Session,
    district: Optional[str],
):
    query = db.query(Village)

    if district:
        query = query.filter(
            Village.district == district
        )

    return query


def get_site_query(
    db: Session,
    district: Optional[str],
):
    query = db.query(RelocationSite)

    if district:
        query = query.filter(
            RelocationSite.district == district
        )

    return query


def safe_number(value, default=0):
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ============================================================
# HAZARD PDF CONTENT
# ============================================================

def build_hazard_content(
    story: list,
    db: Session,
    district: Optional[str],
    styles: dict,
):
    villages = (
        get_village_query(db, district)
        .order_by(Village.hazard_score.desc())
        .all()
    )

    total = len(villages)

    safe_count = sum(
        1
        for village in villages
        if str(village.hazard_zone or "").upper()
        == "SAFE"
    )

    warning_count = sum(
        1
        for village in villages
        if str(village.hazard_zone or "").upper()
        in {"WARNING", "WARN"}
    )

    red_count = sum(
        1
        for village in villages
        if str(village.hazard_zone or "").upper()
        == "RED"
    )

    avg_hazard = (
        sum(
            safe_number(v.hazard_score)
            for v in villages
        )
        / total
        if total
        else 0
    )

    story.append(
        Paragraph(
            "Hazard Overview",
            styles["heading"],
        )
    )

    overview_rows = [
        ["Metric", "Value"],
        ["Habitations assessed", str(total)],
        ["Safe zone", str(safe_count)],
        ["Warning zone", str(warning_count)],
        ["Red zone", str(red_count)],
        [
            "Average hazard score",
            f"{avg_hazard:.1f}",
        ],
    ]

    story.append(
        make_table(
            overview_rows,
            [100 * mm, 70 * mm],
        )
    )

    story.append(Spacer(1, 5 * mm))

    story.append(
        Paragraph(
            "Highest-Risk Habititations",
            styles["heading"],
        )
    )

    top_villages = villages[:10]

    rows = [
        [
            "Village",
            "District",
            "Score",
            "Zone",
            "Population",
        ]
    ]

    for village in top_villages:
        rows.append(
            [
                str(village.name or "-"),
                str(village.district or "-"),
                f"{safe_number(village.hazard_score):.1f}",
                str(village.hazard_zone or "-"),
                str(village.population or 0),
            ]
        )

    if len(rows) == 1:
        rows.append(
            [
                "No village data",
                "-",
                "-",
                "-",
                "0",
            ]
        )

    story.append(
        make_table(
            rows,
            [
                45 * mm,
                35 * mm,
                22 * mm,
                25 * mm,
                25 * mm,
            ],
        )
    )


# ============================================================
# PRIORITY PDF CONTENT
# ============================================================

def build_priority_content(
    story: list,
    db: Session,
    district: Optional[str],
    styles: dict,
):
    villages = (
        get_village_query(db, district)
        .order_by(Village.priority_score.desc())
        .all()
    )

    immediate = [
        v
        for v in villages
        if str(v.priority_category or "").upper()
        == "IMMEDIATE"
    ]

    short_term = [
        v
        for v in villages
        if str(v.priority_category or "").upper()
        in {"SHORT_TERM", "SHORT TERM"}
    ]

    medium_term = [
        v
        for v in villages
        if str(v.priority_category or "").upper()
        in {"MEDIUM_TERM", "MEDIUM TERM"}
    ]

    immediate_population = sum(
        int(v.population or 0)
        for v in immediate
    )

    story.append(
        Paragraph(
            "Relocation Priority Overview",
            styles["heading"],
        )
    )

    rows = [
        ["Priority Category", "Habitations", "Population"],
        [
            "Immediate",
            str(len(immediate)),
            str(immediate_population),
        ],
        [
            "Short Term",
            str(len(short_term)),
            str(
                sum(
                    int(v.population or 0)
                    for v in short_term
                )
            ),
        ],
        [
            "Medium Term",
            str(len(medium_term)),
            str(
                sum(
                    int(v.population or 0)
                    for v in medium_term
                )
            ),
        ],
    ]

    story.append(
        make_table(
            rows,
            [70 * mm, 45 * mm, 45 * mm],
        )
    )

    story.append(Spacer(1, 5 * mm))

    story.append(
        Paragraph(
            "Highest Relocation Priority",
            styles["heading"],
        )
    )

    top_villages = villages[:10]

    rows = [
        [
            "Village",
            "District",
            "Priority Score",
            "Category",
            "Population",
        ]
    ]

    for village in top_villages:
        rows.append(
            [
                str(village.name or "-"),
                str(village.district or "-"),
                f"{safe_number(village.priority_score):.1f}",
                str(village.priority_category or "-"),
                str(village.population or 0),
            ]
        )

    if len(rows) == 1:
        rows.append(
            [
                "No village data",
                "-",
                "-",
                "-",
                "0",
            ]
        )

    story.append(
        make_table(
            rows,
            [
                42 * mm,
                32 * mm,
                28 * mm,
                32 * mm,
                25 * mm,
            ],
        )
    )


# ============================================================
# CAPACITY PDF CONTENT
# ============================================================

def build_capacity_content(
    story: list,
    db: Session,
    district: Optional[str],
    styles: dict,
):
    sites = (
        get_site_query(db, district)
        .order_by(
            RelocationSite.suitability_score.desc()
        )
        .all()
    )

    total_capacity = sum(
        int(site.capacity or 0)
        for site in sites
    )

    current_population = sum(
        int(site.current_population or 0)
        for site in sites
    )

    available_capacity = max(
        total_capacity - current_population,
        0,
    )

    story.append(
        Paragraph(
            "Relocation Capacity Overview",
            styles["heading"],
        )
    )

    rows = [
        ["Metric", "Value"],
        [
            "Relocation sites",
            str(len(sites)),
        ],
        [
            "Total capacity",
            str(total_capacity),
        ],
        [
            "Current population",
            str(current_population),
        ],
        [
            "Available capacity",
            str(available_capacity),
        ],
    ]

    story.append(
        make_table(
            rows,
            [100 * mm, 70 * mm],
        )
    )

    story.append(Spacer(1, 5 * mm))

    story.append(
        Paragraph(
            "Relocation Sites",
            styles["heading"],
        )
    )

    rows = [
        [
            "Site",
            "District",
            "Capacity",
            "Occupied",
            "Available",
            "Suitability",
        ]
    ]

    for site in sites[:15]:
        capacity = int(site.capacity or 0)
        occupied = int(
            site.current_population or 0
        )
        available = max(
            capacity - occupied,
            0,
        )

        rows.append(
            [
                str(site.name or "-"),
                str(site.district or "-"),
                str(capacity),
                str(occupied),
                str(available),
                f"{safe_number(site.suitability_score):.1f}",
            ]
        )

    if len(rows) == 1:
        rows.append(
            [
                "No relocation sites",
                "-",
                "0",
                "0",
                "0",
                "0",
            ]
        )

    story.append(
        make_table(
            rows,
            [
                40 * mm,
                30 * mm,
                22 * mm,
                22 * mm,
                22 * mm,
                25 * mm,
            ],
        )
    )


# ============================================================
# RELOCATION PDF CONTENT
# ============================================================

def build_relocation_content(
    story: list,
    db: Session,
    district: Optional[str],
    styles: dict,
):
    villages = (
        get_village_query(db, district)
        .order_by(Village.priority_score.desc())
        .all()
    )

    sites = get_site_query(
        db,
        district,
    ).all()

    immediate = [
        v
        for v in villages
        if str(v.priority_category or "").upper()
        == "IMMEDIATE"
    ]

    total_population = sum(
        int(v.population or 0)
        for v in villages
    )

    immediate_population = sum(
        int(v.population or 0)
        for v in immediate
    )

    capacity = sum(
        int(s.capacity or 0)
        for s in sites
    )

    occupied = sum(
        int(s.current_population or 0)
        for s in sites
    )

    available = max(
        capacity - occupied,
        0,
    )

    story.append(
        Paragraph(
            "Relocation Situation",
            styles["heading"],
        )
    )

    rows = [
        ["Metric", "Value"],
        [
            "Habitations",
            str(len(villages)),
        ],
        [
            "Total population",
            str(total_population),
        ],
        [
            "Immediate relocation habitations",
            str(len(immediate)),
        ],
        [
            "Immediate relocation population",
            str(immediate_population),
        ],
        [
            "Available relocation capacity",
            str(available),
        ],
    ]

    story.append(
        make_table(
            rows,
            [110 * mm, 60 * mm],
        )
    )

    story.append(Spacer(1, 5 * mm))

    story.append(
        Paragraph(
            "Priority Relocation List",
            styles["heading"],
        )
    )

    rows = [
        [
            "Village",
            "District",
            "Population",
            "Risk",
            "Priority",
            "Category",
        ]
    ]

    for village in villages[:15]:
        rows.append(
            [
                str(village.name or "-"),
                str(village.district or "-"),
                str(village.population or 0),
                f"{safe_number(village.hazard_score):.1f}",
                f"{safe_number(village.priority_score):.1f}",
                str(village.priority_category or "-"),
            ]
        )

    if len(rows) == 1:
        rows.append(
            [
                "No relocation data",
                "-",
                "0",
                "0",
                "0",
                "-",
            ]
        )

    story.append(
        make_table(
            rows,
            [
                38 * mm,
                28 * mm,
                23 * mm,
                20 * mm,
                23 * mm,
                30 * mm,
            ],
        )
    )


# ============================================================
# FULL SITUATION REPORT CONTENT
# ============================================================

def build_full_content(
    story: list,
    db: Session,
    district: Optional[str],
    styles: dict,
):
    villages = (
        get_village_query(
            db,
            district,
        )
        .all()
    )

    sites = (
        get_site_query(
            db,
            district,
        )
        .all()
    )

    total_population = sum(
        int(v.population or 0)
        for v in villages
    )

    safe_count = sum(
        1
        for v in villages
        if str(v.hazard_zone or "").upper()
        == "SAFE"
    )

    warning_count = sum(
        1
        for v in villages
        if str(v.hazard_zone or "").upper()
        in {"WARNING", "WARN"}
    )

    red_count = sum(
        1
        for v in villages
        if str(v.hazard_zone or "").upper()
        == "RED"
    )

    immediate_count = sum(
        1
        for v in villages
        if str(v.priority_category or "").upper()
        == "IMMEDIATE"
    )

    capacity = sum(
        int(s.capacity or 0)
        for s in sites
    )

    occupied = sum(
        int(s.current_population or 0)
        for s in sites
    )

    available = max(
        capacity - occupied,
        0,
    )

    story.append(
        Paragraph(
            "Current Situation Overview",
            styles["heading"],
        )
    )

    rows = [
        ["Metric", "Value"],
        [
            "Vulnerable habitations",
            str(len(villages)),
        ],
        [
            "Population represented",
            str(total_population),
        ],
        [
            "Safe zone",
            str(safe_count),
        ],
        [
            "Warning zone",
            str(warning_count),
        ],
        [
            "Red zone",
            str(red_count),
        ],
        [
            "Immediate relocation",
            str(immediate_count),
        ],
        [
            "Relocation sites",
            str(len(sites)),
        ],
        [
            "Available relocation capacity",
            str(available),
        ],
    ]

    story.append(
        make_table(
            rows,
            [110 * mm, 60 * mm],
        )
    )

    story.append(Spacer(1, 5 * mm))

    # Include hazard section
    build_hazard_content(
        story,
        db,
        district,
        styles,
    )

    # Include relocation/capacity information
    build_capacity_content(
        story,
        db,
        district,
        styles,
    )


# ============================================================
# PDF GENERATOR
# ============================================================

def generate_pdf(
    report: Report,
    db: Session,
) -> Path:
    """
    Generate the physical PDF file for a report.

    Returns:
        Path to generated PDF.
    """

    output_path = report_file_path(
        report.id
    )

    styles = get_pdf_styles()

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
        title=report.title,
        author="ResQVision 2.0",
        subject=report.description or "",
    )

    story: list = []

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "ResQVision 2.0",
            styles["title"],
        )
    )

    story.append(
        Paragraph(
            report.title,
            styles["subtitle"],
        )
    )

    # --------------------------------------------------------
    # REPORT INFORMATION
    # --------------------------------------------------------

    report_date = (
        report.created_at.strftime(
            "%d %B %Y, %H:%M"
        )
        if report.created_at
        else datetime.utcnow().strftime(
            "%d %B %Y, %H:%M"
        )
    )

    info_rows = [
        ["Report Type", display_type(report.report_type)],
        ["Status", report.status],
        ["Generated", report_date],
        [
            "District",
            report.district or "All Maharashtra",
        ],
        [
            "Reporting Period",
            report.period or "Not specified",
        ],
    ]

    story.append(
        make_table(
            [["Report Information", ""]]
            + info_rows,
            [65 * mm, 105 * mm],
        )
    )

    story.append(Spacer(1, 5 * mm))

    if report.description:
        story.append(
            Paragraph(
                report.description,
                styles["body"],
            )
        )

    # --------------------------------------------------------
    # REPORT TYPE CONTENT
    # --------------------------------------------------------

    report_type = (
        str(report.report_type or "full")
        .lower()
    )

    if report_type == "hazard":
        build_hazard_content(
            story,
            db,
            report.district,
            styles,
        )

    elif report_type == "priority":
        build_priority_content(
            story,
            db,
            report.district,
            styles,
        )

    elif report_type == "capacity":
        build_capacity_content(
            story,
            db,
            report.district,
            styles,
        )

    elif report_type == "relocation":
        build_relocation_content(
            story,
            db,
            report.district,
            styles,
        )

    else:
        build_full_content(
            story,
            db,
            report.district,
            styles,
        )

    # --------------------------------------------------------
    # DISCLAIMER
    # --------------------------------------------------------

    story.append(Spacer(1, 8 * mm))

    story.append(
        Paragraph(
            "This report is generated by the ResQVision "
            "2.0 disaster-management platform. Data may "
            "include simulated or system-generated values "
            "for demonstration and decision-support purposes.",
            styles["small"],
        )
    )

    # --------------------------------------------------------
    # BUILD PDF
    # --------------------------------------------------------

    document.build(
        story,
        onFirstPage=draw_page_header_footer,
        onLaterPages=draw_page_header_footer,
    )

    return output_path


# ============================================================
# LIST REPORTS
# ============================================================

@router.get("/")
def list_reports(
    request: Request,
    report_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List generated reports.
    """

    if limit < 1:
        limit = 1

    if limit > 100:
        limit = 100

    if offset < 0:
        offset = 0

    query = db.query(Report)

    if report_type:
        query = query.filter(
            Report.report_type == report_type
        )

    total = query.count()

    reports = (
        query
        .order_by(
            Report.created_at.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "success": True,
        "data": {
            "items": [
                serialize_report(
                    report,
                    request,
                )
                for report in reports
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


# ============================================================
# GENERATE REPORT
# ============================================================

@router.post("/generate")
def generate_report(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Generate a new report and its PDF.
    """

    if not isinstance(payload, dict):
        payload = {}

    report_type = str(
        payload.get(
            "report_type",
            "full",
        )
    ).lower()

    report_format = str(
        payload.get(
            "format",
            "pdf",
        )
    ).lower()

    filters = payload.get(
        "filters",
        {},
    )

    if not isinstance(filters, dict):
        filters = {}

    district = filters.get(
        "district"
    )

    period = filters.get(
        "period"
    )

    if district in (
        "",
        "All Maharashtra",
        None,
    ):
        district = None
    else:
        district = str(district)

    if period:
        period = str(period)

    allowed_report_types = {
        "hazard",
        "priority",
        "capacity",
        "relocation",
        "full",
    }

    if report_type not in allowed_report_types:
        report_type = "full"

    # This implementation generates PDFs.
    # Keep the format as PDF regardless of what the frontend sends.
    report_format = "pdf"

    report_name = display_type(
        report_type
    )

    if district:
        title = (
            f"{report_name} - "
            f"{district}"
        )
    else:
        title = report_name

    description_parts = [
        f"{report_name} generated by "
        "the RESQVision backend."
    ]

    if district:
        description_parts.append(
            f"District: {district}."
        )

    if period:
        description_parts.append(
            f"Reporting period: {period}."
        )

    description = " ".join(
        description_parts
    )

    # --------------------------------------------------------
    # CREATE DATABASE RECORD
    # --------------------------------------------------------

    report = Report(
        title=title,
        report_type=report_type,
        format=report_format,
        status="GENERATING",
        description=description,
        district=district,
        period=period,
        download_url=None,
        created_at=datetime.utcnow(),
    )

    db.add(report)

    db.commit()

    db.refresh(report)

    # --------------------------------------------------------
    # GENERATE PDF
    # --------------------------------------------------------

    try:
        pdf_path = generate_pdf(
            report,
            db,
        )

        if not pdf_path.exists():
            raise RuntimeError(
                "PDF generation completed but "
                "the generated file does not exist."
            )

        report.status = "READY"

        report.download_url = make_download_url(
            request,
            report.id,
        )

        db.commit()

        db.refresh(report)

    except Exception as exc:
        report.status = "FAILED"
        report.download_url = None

        db.commit()

        print(
            f"[REPORT ERROR] "
            f"Failed to generate report "
            f"{report.id}: {exc}"
        )

        return {
            "success": False,
            "data": {
                "report_id": report.id,
                "status": "failed",
                "message": (
                    "The report could not be generated."
                ),
                "error": str(exc),
            },
        }

    return {
        "success": True,
        "data": {
            "report_id": report.id,
            "status": "ready",
            "report_type": report.report_type,
            "format": report.format,
            "download_url": report.download_url,
            "estimated_ready_seconds": 0,
        },
    }


# ============================================================
# DOWNLOAD REPORT
# ============================================================

@router.get("/download/{report_id}")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
):
    """
    Download a report PDF.

    IMPORTANT:
    If the PDF does not exist yet, this endpoint automatically
    regenerates it.

    This makes older reports such as Report #12 downloadable
    even if they were created before PDF generation was added.
    """

    report = (
        db.query(Report)
        .filter(
            Report.id == report_id
        )
        .first()
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report {report_id} not found.",
        )

    if (
        str(report.format or "pdf").lower()
        != "pdf"
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "This report is not stored "
                "as a PDF."
            ),
        )

    pdf_path = report_file_path(
        report.id
    )

    # --------------------------------------------------------
    # EXISTING PDF
    # --------------------------------------------------------

    if not pdf_path.exists():
        try:
            report.status = "GENERATING"

            db.commit()

            generate_pdf(
                report,
                db,
            )

            if not pdf_path.exists():
                raise RuntimeError(
                    "PDF file was not created."
                )

            report.status = "READY"

            db.commit()

        except Exception as exc:
            report.status = "FAILED"

            db.commit()

            print(
                f"[REPORT DOWNLOAD ERROR] "
                f"Could not generate PDF "
                f"for report {report.id}: {exc}"
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "The PDF could not be generated. "
                    f"Error: {exc}"
                ),
            )

    # --------------------------------------------------------
    # RETURN PDF
    # --------------------------------------------------------

    filename = (
        f"{safe_filename(report.title)}"
        f"_Report_{report.id}.pdf"
    )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
    )


# ============================================================
# ALTERNATIVE DOWNLOAD URL
# ============================================================

@router.get("/{report_id}/download")
def download_report_alternative(
    report_id: int,
    db: Session = Depends(get_db),
):
    """
    Alternative download route.

    Supports:

        /api/v1/reports/{id}/download
    """

    report = (
        db.query(Report)
        .filter(
            Report.id == report_id
        )
        .first()
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report {report_id} not found.",
        )

    if (
        str(report.format or "pdf").lower()
        != "pdf"
    ):
        raise HTTPException(
            status_code=400,
            detail="This report is not a PDF.",
        )

    pdf_path = report_file_path(
        report.id
    )

    if not pdf_path.exists():
        try:
            generate_pdf(
                report,
                db,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Could not generate the PDF: "
                    f"{exc}"
                ),
            )

    if not pdf_path.exists():
        raise HTTPException(
            status_code=500,
            detail="PDF file was not created.",
        )

    filename = (
        f"{safe_filename(report.title)}"
        f"_Report_{report.id}.pdf"
    )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
    )


# ============================================================
# GET REPORT STATUS
# ============================================================

@router.get("/{report_id}")
def get_report_status(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get report status.
    """

    report = (
        db.query(Report)
        .filter(
            Report.id == report_id
        )
        .first()
    )

    if report is None:
        return {
            "success": False,
            "data": {
                "report_id": report_id,
                "status": "not_found",
                "download_url": None,
            },
        }

    download_url = None

    if (
        str(report.format or "").lower()
        == "pdf"
    ):
        download_url = make_download_url(
            request,
            report.id,
        )

    return {
        "success": True,
        "data": {
            "report_id": report.id,
            "status": str(
                report.status or ""
            ).lower(),
            "download_url": download_url,
            "report_type": report.report_type,
            "format": report.format,
        },
    }


# ============================================================
# DELETE REPORT
# ============================================================

@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
):
    """
    Delete report and its generated PDF.
    """

    report = (
        db.query(Report)
        .filter(
            Report.id == report_id
        )
        .first()
    )

    if report is None:
        return {
            "success": False,
            "data": {
                "message": (
                    f"Report {report_id} "
                    "not found."
                ),
            },
        }

    pdf_path = report_file_path(
        report.id
    )

    # Delete physical PDF if it exists.
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except OSError as exc:
            print(
                f"[REPORT DELETE WARNING] "
                f"Could not delete PDF "
                f"{pdf_path}: {exc}"
            )

    db.delete(report)

    db.commit()

    return {
        "success": True,
        "data": {
            "message": (
                f"Report {report_id} "
                "deleted successfully."
            ),
        },
    }