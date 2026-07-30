"""
Génère des données factices pour tester le pipeline multi-vues
sans avoir de vrai dataset.
"""

import json
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def generate_dummy_dataset(output_dir: str = "data/processed", num_products: int = 100):
    """
    Génère un dataset factice de produits avec 1-5 vues et grades A/B/C/D.
    
    Usage: python scripts/generate_dummy_data.py
    """
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Créer les splits
    (output_path / "train").mkdir(exist_ok=True)
    (output_path / "val").mkdir(exist_ok=True)
    
    annotations = {"train": {}, "val": {}}
    
    grades = ["A", "B", "C", "D"]
    categories = ["smartphone", "laptop", "tablet", "headphones"]
    brands = ["Apple", "Samsung", "Sony", "Dell"]
    
    print(f"[INFO] Génération de {num_products} produits factices...")
    
    for i in range(num_products):
        split = "train" if i < int(num_products * 0.8) else "val"
        product_id = f"product_{i:04d}"
        product_dir = output_path / split / product_id
        product_dir.mkdir(parents=True, exist_ok=True)
        
        # Générer des métadonnées aléatoires
        grade = random.choice(grades)
        num_views = random.randint(1, 5)  # 1 à 5 vues (variable!)
        category = random.choice(categories)
        brand = random.choice(brands)
        
        # Générer les images
        for v in range(num_views):
            # Créer une image avec un "défaut" visuel selon le grade
            img = _generate_product_image(grade, v, category)
            img.save(product_dir / f"view_{v:02d}.jpg")
        
        # Annotations
        annotations[split][product_id] = {
            "grade": grade,
            "num_views": num_views,
            "category": category,
            "brand": brand,
            "model": f"{brand}-{random.randint(1, 20)}",
            "defects": _generate_defects(grade),
            "original_price": random.randint(200, 1500),
            "age_days": random.randint(30, 1000)
        }
    
    # Sauvegarder les annotations
    for split in ["train", "val"]:
        with open(output_path / f"annotations_{split}.json", "w") as f:
            json.dump(annotations[split], f, indent=2)
    
    print(f"[OK] Dataset généré dans {output_path}")
    print(f"  Train: {len(annotations['train'])} produits")
    print(f"  Val: {len(annotations['val'])} produits")
    print(f"  Vues: 1-5 par produit (variable)")


def _generate_product_image(grade: str, view_idx: int, category: str) -> Image.Image:
    """Génère une image factice avec des défauts visuels selon le grade."""
    
    # Couleur de base selon la catégorie
    colors = {
        "smartphone": (100, 150, 200),
        "laptop": (150, 150, 150),
        "tablet": (200, 180, 150),
        "headphones": (180, 100, 100)
    }
    base_color = colors.get(category, (128, 128, 128))
    
    # Créer l'image
    img = Image.new('RGB', (400, 400), base_color)
    draw = ImageDraw.Draw(img)
    
    # Ajouter un "produit" (rectangle arrondi)
    draw.rounded_rectangle([50, 50, 350, 350], radius=20, fill=(220, 220, 220))
    
    # Ajouter des défauts selon le grade
    if grade == "A":
        # Aucun défaut
        pass
    elif grade == "B":
        # Légères rayures
        for _ in range(2):
            x1, y1 = random.randint(60, 340), random.randint(60, 340)
            x2, y2 = x1 + random.randint(20, 80), y1 + random.randint(-10, 10)
            draw.line([(x1, y1), (x2, y2)], fill=(150, 150, 150), width=1)
    elif grade == "C":
        # Rayures + éraflures
        for _ in range(5):
            x1, y1 = random.randint(60, 340), random.randint(60, 340)
            x2, y2 = x1 + random.randint(30, 100), y1 + random.randint(-20, 20)
            draw.line([(x1, y1), (x2, y2)], fill=(100, 100, 100), width=2)
        # Petit choc
        cx = random.randint(200, 300)
        cy = random.randint(200, 300)
        cr = random.randint(10, 20)
        draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(80, 80, 80))
    elif grade == "D":
        # Dommages importants
        # Fissure
        draw.line([(100, 100), (300, 300)], fill=(50, 50, 50), width=4)
        # Grand choc
        draw.ellipse([150, 150, 250, 250], fill=(60, 60, 60))
        # Tache
        draw.ellipse([50, 250, 150, 350], fill=(120, 100, 80))
    
    # Ajouter le texte de la vue
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
    draw.text((10, 10), f"View {view_idx} - Grade {grade}", fill=(0, 0, 0), font=font)
    
    return img


def _generate_defects(grade: str) -> list:
    """Génère une liste de défauts selon le grade."""
    defects = {
        "A": [],
        "B": ["scratch_light"],
        "C": ["scratch_deep", "dent_small", "discoloration"],
        "D": ["crack", "dent_large", "missing_part", "water_damage"]
    }
    return defects.get(grade, [])


if __name__ == "__main__":
    import sys
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    generate_dummy_dataset(num_products=num)