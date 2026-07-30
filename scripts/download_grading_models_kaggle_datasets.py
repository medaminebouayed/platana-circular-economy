import os
import shutil
import dotenv
import kagglehub

datasets = [
    "axondata/cracked-and-intact-smartphone-images-dataset",
    "dataclusterlabs/mobile-phone-image-dataset",
    "girish17019/mobile-phone-defect-segmentation-dataset",
]

# 1. Charger le fichier d'environnement
print(dotenv.load_dotenv("./.env.template"))

# 2. Récupérer le dossier de destination
datasets_path = os.getenv("DATASETS_PATH", "../../data/external/")

# Vérifier si le dossier existe
if not os.path.exists(datasets_path):
    os.makedirs(datasets_path, exist_ok=True)
else:
    print("Le dossier existe déjà")

for dataset in datasets:
    try:
        print(f"Téléchargement de {dataset}...")
        # Télécharge le dataset dans le cache local de Kaggle
        cache_path = kagglehub.dataset_download(dataset)
        
        # Copier les fichiers du cache vers votre dossier local cible
        dataset_name = dataset.split("/")[-1]
        target_dir = os.path.join(datasets_path, dataset_name)
        
        if not os.path.exists(target_dir):
            shutil.copytree(cache_path, target_dir)
            print(f"Dataset sauvegardé dans : {target_dir}")
        else:
            print(f"Le dossier {target_dir} existe déjà.")

    except Exception as e:
        print(f"Erreur lors du téléchargement de {dataset} : {e}")

print("All datasets processed successfully")