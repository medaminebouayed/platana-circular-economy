import os
import json
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from fpdf import FPDF

class ProductSheetGenerator:
    def __init__(self):
        repo_root = Path(__file__).resolve().parents[2]
        load_dotenv(repo_root / ".env")
        
        # On supprime le chargement du JSON, on n'en a plus besoin !
        
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            self.client = Groq(api_key=api_key)
            self.use_real_api = True
            print("GenAI : Client Groq initialisé avec succès.")
        else:
            print("Warning: GROQ_API_KEY non trouvée dans le .env. Utilisation du mode simulé.")
            self.use_real_api = False

    def _get_fallback_text(self, repaired_defects):
        """Fallback basique si l'API Groq ne fonctionne pas."""
        if not repaired_defects or repaired_defects == ["no_defect"]:
            return "Aucune réparation majeure. Produit testé et nettoyé."
        clean_defects = [d.replace("_", " ").capitalize() for d in repaired_defects]
        return "Réparations effectuées : " + ", ".join(clean_defects) + "."

    def generate_sheet_text(self, model_name, grade, repaired_defects, price):
        """Génère le texte de la fiche produit via Groq (Llama 3.3)."""
        
        # Préparer la liste brute des défauts pour le prompt
        if not repaired_defects or repaired_defects == ["no_defect"]:
            raw_defects_str = "Aucune (Produit fonctionnel, simple nettoyage)"
        else:
            raw_defects_str = ", ".join(repaired_defects)
        
        if self.use_real_api:
            prompt = f"""
            Tu es un expert en reconditionnement de produits électroniques. Rédige une fiche produit pour la vente en ligne.
            L'annonce doit être honnête, optimisée SEO, rassurante et rédigée en français.
            
            Données Produit:
            - Modèle: {model_name}
            - Grade: {grade} (A=Parfait état, B=Très bon état, C=Bon état avec micro-rayures visibles, D=État correct avec défauts esthétiques marqués)
            - Liste technique des réparations effectuées par l'atelier: {raw_defects_str}
            - Prix de revente: {price}€
            
            INSTRUCTION IMPORTANTE: 
            La liste des réparations est donnée en format technique informatique (ex: "screen_crack", "cosmetic_scratch").
            Tu DOIS traduire dynamiquement ces termes techniques en français commercial humain et rassurant dans la description (ex: "Écran remplacé par nos soins", "Coque arrière polie"). 
            Intègre ces réparations naturellement dans la description.
            
            Retourne UNIQUEMENT un objet JSON valide avec exactement ce format:
            {{
                "title": "Titre accrocheur et SEO (max 60 caractères)",
                "description": "Description commerciale de 3 à 4 phrases",
                "highlights": ["Point fort 1", "Point fort 2", "Point fort 3"],
                "warnings": ["Point d'attention ou défaut esthétique à signaler"]
            }}
            """
            
            try:
                response = self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                print(f"Erreur API Groq: {e}. Bascule sur le mode simulé.")
                self.use_real_api = False
        
        # Mode simulé (fallback) - Utilise la fonction de secours
        if not self.use_real_api:
            repair_info = self._get_fallback_text(repaired_defects)
            return {
                "title": f"{model_name} Reconditionné - Grade {grade}",
                "description": f"Ce {model_name} a été entièrement inspecté et reconditionné par nos techniciens. Profitez d'un produit performant à prix réduit, couvert par notre garantie de 6 mois. {repair_info}.",
                "highlights": ["Testé et certifié par nos ateliers", "Garantie 6 mois incluse", f"Économie de {price}€ par rapport au neuf"],
                "warnings": [f"Présence de micro-traces d'usage liées au Grade {grade}"]
            }

    def _clean_text_for_pdf(self, text):
        """Nettoie le texte pour le rendre compatible avec la police Helvetica de FPDF."""
        if not isinstance(text, str):
            return text
        text = text.replace("€", " EUR")
        text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
        text = text.replace("—", "-").replace("…", "...")
        
        return text.encode("latin-1", "ignore").decode("latin-1")
    
    def generate_pdf(self, sheet_data, output_path):
        """Génère un PDF professionnel à partir des données de la fiche."""
        
        # Nettoyer toutes les valeurs du dictionnaire pour FPDF
        clean_data = {
            "title": self._clean_text_for_pdf(sheet_data.get("title", "")),
            "description": self._clean_text_for_pdf(sheet_data.get("description", "")),
            "highlights": [self._clean_text_for_pdf(h) for h in sheet_data.get("highlights", [])],
            "warnings": [self._clean_text_for_pdf(w) for w in sheet_data.get("warnings", [])]
        }
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15) # Gérer les sauts de page automatiques
        
        # Marges sécurisées
        pdf.set_left_margin(10)
        pdf.set_right_margin(10)
        
        # En-tête
        pdf.set_font("Helvetica", 'B', 16)
        pdf.set_text_color(33, 150, 243) # Bleu professionnel
        pdf.multi_cell(0, 10, clean_data.get("title", "Fiche Produit"), align='C')
        pdf.ln(5)
        
        # Ligne de séparation
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(10)
        
        # Description
        pdf.set_font("Helvetica", 'B', 12)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, "Description du produit :", ln=True)
        pdf.set_font("Helvetica", '', 11)
        pdf.multi_cell(0, 7, clean_data.get("description", ""))
        pdf.ln(5)
        
        # Points forts
        pdf.set_font("Helvetica", 'B', 12)
        pdf.set_text_color(0, 100, 0) # Vert
        pdf.cell(0, 10, "Points forts :", ln=True)
        pdf.set_font("Helvetica", '', 11)
        pdf.set_text_color(0, 0, 0)
        
        # Pour les puces, on fixe la marge gauche et on donne une largeur fixe au multi_cell
        for highlight in clean_data.get("highlights", []):
            if not highlight: continue # Ignorer les lignes vides
            pdf.set_x(15) # Décaler un peu pour la puce
            pdf.cell(5, 7, "-")
            pdf.multi_cell(180, 7, highlight) # 180 est la largeur totale sûre
        pdf.ln(5)
        
        # Points d'attention (Transparence)
        pdf.set_font("Helvetica", 'B', 12)
        pdf.set_text_color(200, 100, 0) # Orange
        pdf.cell(0, 10, "Points d'attention :", ln=True)
        pdf.set_font("Helvetica", '', 11)
        pdf.set_text_color(0, 0, 0)
        
        for warning in clean_data.get("warnings", []):
            if not warning: continue
            pdf.set_x(15)
            pdf.cell(5, 7, "-")
            pdf.multi_cell(180, 7, warning)
            
        # Pied de page
        pdf.ln(10)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        pdf.set_font("Helvetica", 'I', 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 5, "Document genere automatiquement par Circular Economy Intelligence Engine", align='C')
        
        # Sauvegarde
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))