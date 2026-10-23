from io import BytesIO, StringIO
from decimal import Decimal, ROUND_HALF_UP
import csv

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A3
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    LongTable,
    TableStyle,
    Paragraph,
)

from backend.services.dashboard_service import DashboardService


class ExportService:

    COLUMNS = [
        ("Date", "shift_date"),
        ("Vessel", "vessel_name"),
        ("Shift", "shift_name"),
        ("Opening Fuel (L)", "opening_fuel"),
        ("Received Fuel (L)", "received_fuel"),
        ("Transfer In (L)", "transfer_in"),
        ("ME Consumption (L)", "me_consumption"),
        ("ME Hours", "me_hours"),
        ("AUX Consumption (L)", "aux_consumption"),
        ("AUX Hours", "aux_hours"),
        ("DG Consumption (L)", "dg_consumption"),
        ("DG Hours", "dg_hours"),
        ("Total Engine Consumption (L)", "total_engine_consumption"),
        ("Transfer Out (L)", "transfer_out"),
        ("Fuel Issues Out (L)", "issue_out"),
        ("Adjustment In (L)", "adjustment_in"),
        ("Adjustment Out (L)", "adjustment_out"),
        ("Closing Fuel (L)", "closing_fuel"),
        ("Fuel Threshold (L)", "fuel_threshold_litres"),
        ("Flags", "flags"),
    ]

    PDF_COLUMNS = [
        ("Date", "shift_date"),
        ("Vessel", "vessel_name"),
        ("Shift", "shift_name"),
        ("Opening Fuel (L)", "opening_fuel"),
        ("Received Fuel (L)", "received_fuel"),
        ("Transfer In (L)", "transfer_in"),
        ("ME Consumption (L)", "me_consumption"),
        ("ME Hours", "me_hours"),
        ("AUX Consumption (L)", "aux_consumption"),
        ("AUX Hours", "aux_hours"),
        ("DG Consumption (L)", "dg_consumption"),
        ("DG Hours", "dg_hours"),
        ("Total Engine Consumption (L)", "total_engine_consumption"),
        ("Transfer Out (L)", "transfer_out"),
        ("Closing Fuel (L)", "closing_fuel"),
    ]

    @staticmethod
    def get_rows(
        db,
        *,
        from_date,
        to_date,
        vessel_ids=None,
        vessel_id=None,
        shift_name=None,
    ) -> list[dict]:

        if vessel_id is not None:
            vessel_ids = [vessel_id]

        if vessel_ids:
            rows = []

            for vessel_id in vessel_ids:
                vessel_rows = DashboardService.get_fuel_dashboard(
                    db=db,
                    from_date=from_date,
                    to_date=to_date,
                    vessel_id=vessel_id,
                    shift_name=shift_name,
                )

                rows.extend(vessel_rows)

        else:
            rows = DashboardService.get_fuel_dashboard(
                db=db,
                from_date=from_date,
                to_date=to_date,
                shift_name=shift_name,
            )

        shift_order = {"MORNING": 0, "EVENING": 1}
        rows.sort(
            key=lambda row: (
                row["shift_date"],
                shift_order.get(str(row["shift_name"] or "").upper(), 2),
                row["vessel_name"].casefold(),
                row["shift_id"],
            )
        )
        return rows

    @staticmethod
    def _format_value(value):
        if value is None:
            return ""

        if isinstance(value, list):
            return ", ".join(str(item) for item in value)

        if isinstance(value, (Decimal, int, float)) and not isinstance(value, bool):
            return str(
                Decimal(str(value)).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )
            )

        return str(value)

    @staticmethod
    def create_csv(rows: list[dict]) -> BytesIO:
        output = StringIO()

        writer = csv.writer(output)

        writer.writerow(
            [column_name for column_name, _ in ExportService.COLUMNS]
        )

        for row in rows:
            writer.writerow(
                [
                    ExportService._format_value(row[field])
                    for _, field in ExportService.COLUMNS
                ]
            )

        result = BytesIO(
            output.getvalue().encode("utf-8-sig")
        )

        result.seek(0)

        return result

    @staticmethod
    def create_excel(rows: list[dict]) -> BytesIO:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Fuel Dashboard"

        headers = [
            column_name
            for column_name, _ in ExportService.COLUMNS
        ]

        worksheet.append(headers)

        for row in rows:
            worksheet.append(
                [
                    ExportService._format_value(row[field])
                    for _, field in ExportService.COLUMNS
                ]
            )

        # Header formatting
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        # Reasonable column widths
        for column_cells in worksheet.columns:
            column_letter = column_cells[0].column_letter

            max_length = 0

            for cell in column_cells:
                value = str(cell.value or "")
                max_length = max(
                    max_length,
                    len(value),
                )

            worksheet.column_dimensions[
                column_letter
            ].width = min(max(max_length + 2, 12), 35)

        output = BytesIO()

        workbook.save(output)

        output.seek(0)

        return output

    @staticmethod
    def create_pdf(rows: list[dict]) -> BytesIO:
        output = BytesIO()

        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A3),
            rightMargin=20,
            leftMargin=20,
            topMargin=20,
            bottomMargin=20,
        )

        styles = getSampleStyleSheet()
        table_header_style = ParagraphStyle(
            "FuelDashboardHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=9,
        )
        table_cell_style = ParagraphStyle(
            "FuelDashboardCell",
            parent=styles["Normal"],
            fontSize=8,
            leading=9,
        )

        title = Paragraph(
            "InsiteFuel V3 - Fuel Dashboard",
            styles["Title"],
        )

        headers = [column_name for column_name, _ in ExportService.PDF_COLUMNS]

        data = [[Paragraph(header, table_header_style) for header in headers]]

        for row in rows:
            data.append(
                [
                    Paragraph(ExportService._format_value(row[field]), table_cell_style)
                    for _, field in ExportService.PDF_COLUMNS
                ]
            )

        table = LongTable(
            data,
            repeatRows=1,
            colWidths=[52, 110, 58, 75, 75, 75, 75, 60, 75, 60, 75, 60, 85, 75, 75],
            splitByRow=1,
            splitInRow=1,
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.lightgrey,
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.black,
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
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                ]
            )
        )

        document.build(
            [
                title,
                table,
            ]
        )

        output.seek(0)

        return output
