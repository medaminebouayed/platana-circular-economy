"""
Professional PDF evaluation report generator for Platana products.

Builds a printable evaluation report (A4, French) from a MongoDB product
document: product metadata, AI predictions and, when available, the final
admin review. Output is written to the ``data/reports`` directory and the
relative path is stored on the product document so the admin can download it.
"""
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

# FPDF core fonts are Latin-1; strip any char that cannot be encoded.
def _clean(text) -> str:
    if not isinstance(text, str):
        text = str(text or "")
    text = text.replace("€", " EUR")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = text.replace("—", "-").replace("…", "...")
    return text.encode("latin-1", "ignore").decode("latin-1")


class EvaluationReportPDF:
    """A4 professional report: product info + AI evaluation + admin review."""

    MARGIN = 12
    FOOTER = "Platana Circular Economy — Rapport d'evaluation genere automatiquement"

    def __init__(self):
        self.pdf = FPDF(orientation="P", unit="mm", format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=18)
        self.pdf.set_margins(self.MARGIN, 16, self.MARGIN)
        self.pdf.add_page()

    # ── low-level helpers ─────────────────────────────────────────
    def _header_bar(self, title: str):
        self.pdf.set_font("Helvetica", "B", 15)
        self.pdf.set_text_color(17, 24, 39)
        self.pdf.cell(0, 10, _clean(title), ln=True)
        self.pdf.set_draw_color(33, 150, 243)
        self.pdf.set_line_width(0.8)
        self.pdf.line(self.MARGIN, self.pdf.get_y(), 198, self.pdf.get_y())
        self.pdf.ln(4)

    def _section(self, label: str):
        self.pdf.set_font("Helvetica", "B", 11)
        self.pdf.set_text_color(33, 150, 243)
        self.pdf.cell(0, 8, _clean(label), ln=True)
        self.pdf.ln(1)

    def _row(self, label: str, value, bold_value=False):
        value = _clean(value)
        self.pdf.set_font("Helvetica", "B", 9.5)
        self.pdf.set_text_color(90, 90, 90)
        self.pdf.cell(55, 6, _clean(label))
        self.pdf.set_font("Helvetica", "B" if bold_value else "", 10)
        self.pdf.set_text_color(17, 24, 39)
        self.pdf.multi_cell(0, 6, value, ln=True)

    def _bullet(self, text: str):
        self.pdf.set_x(20)
        self.pdf.cell(5, 6, "-")
        self.pdf.multi_cell(161, 6, _clean(text), ln=True)

    # ── report build ──────────────────────────────────────────────
    def build(self, product: dict) -> "EvaluationReportPDF":
        ai = (product.get("ai_predictions") or {}) or {}
        review = (product.get("admin_review") or {}) or {}

        product_id = product.get("_id", "")
        try:
            product_id = str(product_id)
        except Exception:
            product_id = ""

        # Header
        self._header_bar("Platana — Rapport d'evaluation produit")

        # Product identity
        self._section("Informations produit")
        self._row("Reference", product_id, bold_value=True)
        self._row("Produit", f"{product.get('brand', '')} {product.get('model', '')}")
        self._row("Annee", product.get("year", ""))
        self._row("Prix d'origine", f"{product.get('original_price', 0)} EUR")
        created = product.get("created_at")
        if created:
            self._row("Depot le", created.strftime("%d/%m/%Y %H:%M") if hasattr(created, "strftime") else _clean(created))
        self.pdf.ln(2)

        # AI evaluation
        self._section("Evaluation IA (Dify / CV + Pricing)")
        if ai:
            self._row("Grade estime", ai.get("grade", ""), bold_value=True)
            self._row("Prix de marche", f"{ai.get('market_price', 0)} EUR")
            self._row("Cout de reparation", f"{ai.get('refurb_cost', 0)} EUR")
            self._row("Profit estime", f"{ai.get('profit', 0)} EUR")
            self._row("Decision recommandee", ai.get("decision", ""), bold_value=True)
            defects = ai.get("defects") or []
            if defects:
                self._row("Defauts detectes", ", ".join(defects))
            if ai.get("title"):
                self._row("Titre fiche", ai.get("title"))
            if ai.get("description"):
                self._row("Description", ai.get("description"))
            predicted = ai.get("predicted_at")
            if predicted:
                self._row("Evalue le", predicted.strftime("%d/%m/%Y %H:%M") if hasattr(predicted, "strftime") else _clean(predicted))
        else:
            self.pdf.set_text_color(120, 120, 120)
            self.pdf.cell(0, 6, "Aucune evaluation IA disponible.", ln=True)
        self.pdf.ln(2)

        # Admin review
        self._section("Validation administrateur")
        if review:
            self._row("Grade final", review.get("grade", ""), bold_value=True)
            self._row("Prix final", f"{review.get('market_price', 0)} EUR")
            self._row("Cout de reparation", f"{review.get('refurb_cost', 0)} EUR")
            self._row("Decision finale", review.get("decision", ""), bold_value=True)
            review_defects = review.get("defects") or []
            if review_defects:
                self._row("Defauts retenus", ", ".join(review_defects))
            if review.get("title"):
                self._row("Titre final", review.get("title"))
            if review.get("description"):
                self._row("Description finale", review.get("description"))
            reviewed_at = review.get("reviewed_at")
            if reviewed_at:
                self._row("Revu le", reviewed_at.strftime("%d/%m/%Y %H:%M") if hasattr(reviewed_at, "strftime") else _clean(reviewed_at))
            self._row("Valide par", review.get("reviewed_by", ""))
        else:
            self.pdf.set_text_color(120, 120, 120)
            self.pdf.cell(0, 6, "Aucune validation administrateur pour le moment.", ln=True)

        # Footer
        self.pdf.set_y(-16)
        self.pdf.set_draw_color(200, 200, 200)
        self.pdf.line(self.MARGIN, self.pdf.get_y(), 198, self.pdf.get_y())
        self.pdf.set_font("Helvetica", "I", 7.5)
        self.pdf.set_text_color(150, 150, 150)
        self.pdf.cell(0, 5, _clean(self.FOOTER), align="C", ln=True)
        self.pdf.cell(0, 5, _clean(f"Genere le {datetime.now().strftime('%d/%m/%Y %H:%M')}"), align="C")

        return self

    def output(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(str(path))


def generate_product_report(product: dict, output_path: Path) -> None:
    """Generate the evaluation report PDF for a product document."""
    report = EvaluationReportPDF()
    report.build(product)
    report.output(output_path)
