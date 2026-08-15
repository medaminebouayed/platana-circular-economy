import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)

db = client.platana_circular_economy
products_collection = db.products
users_collection = db.users
workshops_collection = db.workshops
product_catalog_collection = db.product_catalog
pricing_training_samples_collection = db.pricing_training_samples
