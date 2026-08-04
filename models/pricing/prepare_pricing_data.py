import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

def generate_market_dataset():
    np.random.seed(42)
    data = []
    
    models = {
        "iPhone 13": {"brand": "Apple", "category": "smartphone", "price": 800},
        "iPhone 11": {"brand": "Apple", "category": "smartphone", "price": 500},
        "Samsung S21": {"brand": "Samsung", "category": "smartphone", "price": 600}
    }
    
    for _ in range(1500):
        model_name = np.random.choice(list(models.keys()))
        info = models[model_name]
        
        # Date de vente aléatoire dans les 2 dernières années
        sale_date = datetime.now() - timedelta(days=np.random.randint(0, 730))
        
        # Age du produit en jours (ex: acheté il y a 1 à 3 ans)
        age_days = np.random.randint(365, 365*4)
        
        grade = np.random.choice(["A", "B", "C", "D"], p=[0.25, 0.35, 0.25, 0.15])
        
        # Calcul du prix de revente
        base_price = info["price"]
        depreciation = age_days / 365 * 0.15  # 15% par an
        grade_mult = {"A": 0.85, "B": 0.70, "C": 0.55, "D": 0.35}[grade]
        
        sale_price = base_price * (1 - depreciation) * grade_mult
        sale_price *= np.random.uniform(0.95, 1.05) # Bruit

        defect_count = {"A": 0, "B": 1, "C": 2, "D": 3}[grade]
        repair_cost = {"A": 5, "B": 20, "C": 60, "D": 120}[grade]
        
        data.append({
            "brand": info["brand"],
            "model": model_name,
            "category": info["category"],
            "grade": grade,
            "original_price": base_price,
            "sale_price": round(max(sale_price, 20), 2),
            "age_days": age_days,
            "date": sale_date.strftime("%Y-%m-%d"),
            "market_avg_price": round(base_price * 0.6, 2), # Prix moyen du marché
            "repair_cost": repair_cost,                     # Coût de réparation simulé
            "defect_count": defect_count                    # Nombre de défauts
        })
        
    df = pd.DataFrame(data)
    output_path = Path("data/processed/pricing_dataset.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Dataset de pricing généré : {output_path}")

if __name__ == "__main__":
    generate_market_dataset()