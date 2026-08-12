import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

def generate_market_dataset():
    np.random.seed(42)
    data = []
    
    products = {
        "iPhone 13": {"brand": "Apple", "category": "smartphone", "price": 800},
        "iPhone 11": {"brand": "Apple", "category": "smartphone", "price": 500},
        "Galaxy S21": {"brand": "Samsung", "category": "smartphone", "price": 600},
        "MacBook Pro 2020": {"brand": "Apple", "category": "laptop", "price": 1500},
        "Dell XPS 13": {"brand": "Dell", "category": "laptop", "price": 1200},
        "iPad Air": {"brand": "Apple", "category": "tablet", "price": 600},
        "Bravia 50\"": {"brand": "Sony", "category": "tv", "price": 800}
    }
    
    # Banque de défauts exacts et leur impact économique de base
    defect_bank = {
        "screen_crack": {"cost": 120, "penalty": 0.80},
        "battery_swollen": {"cost": 80, "penalty": 0.90},
        "port_broken": {"cost": 60, "penalty": 0.85},
        "microphone_dead": {"cost": 40, "penalty": 0.85},
        "cosmetic_scratch": {"cost": 20, "penalty": 0.95},
        "hinge_broken": {"cost": 200, "penalty": 0.70},
        "no_power": {"cost": 150, "penalty": 0.65}
    }
    
    for _ in range(2000):
        model_name = np.random.choice(list(products.keys()))
        info = products[model_name]
        
        sale_date = datetime.now() - timedelta(days=np.random.randint(0, 730))
        age_days = np.random.randint(180, 365*4)
        grade = np.random.choice(["A", "B", "C", "D"], p=[0.3, 0.35, 0.25, 0.1])
        
        # Génération des défauts (liste de 0 à 3 défauts)
        if grade == "A":
            defects_list = []
        elif grade == "B":
            defects_list = [np.random.choice(["cosmetic_scratch", "microphone_dead"])]
        else:
            num_defects = np.random.randint(1, 4) # 1 à 3 défauts
            defects_list = np.random.choice(list(defect_bank.keys()), size=num_defects, replace=False).tolist()
            
        # Calcul du coût total et de la pénalité moyenne
        total_repair_cost = 5.0
        avg_penalty = 1.0
        
        if defects_list:
            total_repair_cost = sum(defect_bank[d]["cost"] for d in defects_list)
            avg_penalty = np.mean([defect_bank[d]["penalty"] for d in defects_list])
            
        # Formatage en chaîne de caractères (ex: "screen_crack,battery_swollen")
        exact_defects_str = ",".join(defects_list) if defects_list else "no_defect"
        defect_count = len(defects_list)
        
        base_price = info["price"]
        depreciation = min(age_days / 365 * 0.15, 0.60)
        grade_mult = {"A": 0.90, "B": 0.75, "C": 0.60, "D": 0.40}[grade]
        
        # Le prix de vente subit la dépréciation, le grade, la pénalité de marché et le coût de réparation
        sale_price = (base_price * (1 - depreciation) * grade_mult * avg_penalty) - total_repair_cost
        sale_price *= np.random.uniform(0.95, 1.05) # Bruit de marché
        
        data.append({
            "brand": info["brand"],
            "model": model_name,
            "category": info["category"],
            "grade": grade,
            "original_price": base_price,
            "sale_price": round(max(sale_price, 20), 2),
            "age_days": age_days,
            "date": sale_date.strftime("%Y-%m-%d"),
            "market_avg_price": round(base_price * 0.6, 2),
            "repair_cost": round(total_repair_cost, 2), 
            "defect_count": defect_count,
            "exact_defects": exact_defects_str  # La feature texte qui sera Target Encodée
        })
        
    df = pd.DataFrame(data)
    output_path = Path("data/processed/pricing_dataset.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Dataset généré avec défauts multiples : {output_path}")

if __name__ == "__main__":
    generate_market_dataset()