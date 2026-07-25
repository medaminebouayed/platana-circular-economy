"""
Script Python de téléchargement de MVTec AD (alternative au batch).
"""

import os
import urllib.request
import tarfile
from pathlib import Path


def download_mvtec(data_root: str = "data/external"):
    """Télécharge et extrait MVTec AD."""
    
    mvtec_dir = Path(data_root) / "mvtec_ad"
    mvtec_dir.mkdir(parents=True, exist_ok=True)
    
    url = "https://www.mydrive.ch/shares/150996/b52ecdcbf521176e9db9c731f2304b27/download/420938113-1629960298/mvtec_anomaly_detection.tar.xz"
    archive_path = mvtec_dir / "mvtec.tar.xz"
    
    if (mvtec_dir / "bottle").exists():
        print("[INFO] MVTec AD déjà présent.")
        return str(mvtec_dir)
    
    print("[INFO] Téléchargement de MVTec AD (~4.9 GB)...")
    urllib.request.urlretrieve(url, archive_path)
    print(f"[OK] Téléchargé: {archive_path.stat().st_size / 1024 / 1024 / 1024:.1f} GB")
    
    print("[INFO] Extraction...")
    with tarfile.open(archive_path, "r:xz") as tar:
        tar.extractall(mvtec_dir)
    
    archive_path.unlink()
    print("[OK] Extraction terminée")
    
    # Vérification
    categories = [
        "bottle", "cable", "capsule", "carpet", "grid", "hazelnut",
        "leather", "metal_nut", "pill", "screw", "tile", "toothbrush",
        "transistor", "wood", "zipper"
    ]
    found = sum(1 for c in categories if (mvtec_dir / c).exists())
    print(f"[INFO] Catégories trouvées: {found}/15")
    
    return str(mvtec_dir)


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "data/external"
    download_mvtec(root)