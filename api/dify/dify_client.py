import os
import mimetypes
import httpx
from typing import List

DIFY_API_URL = os.getenv("DIFY_API_URL", "https://api.dify.ai/v1")
DIFY_EVAL_API_KEY = os.getenv("DIFY_EVAL_API_KEY")
DIFY_PUBLISH_API_KEY = os.getenv("DIFY_PUBLISH_API_KEY")
DIFY_USER = "fastapi-backend-admin"


async def upload_file_to_dify(file_path: str, file_name: str) -> str:
    """Upload a local file to Dify and return its file_id.

    Dify's /files/upload endpoint requires:
    - Authorization header
    - multipart field 'file'  → the binary content with a valid mime type
    - multipart field 'user'  → an arbitrary string identifier (required by Dify)

    Without the 'user' field, Dify returns {"code":"invalid_param","message":"Invalid upload file","status":400}.
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith("image/"):
        # Dify only accepts image types in the evaluation workflow
        mime_type = "image/jpeg"

    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {DIFY_EVAL_API_KEY}"}
        with open(file_path, "rb") as f:
            response = await client.post(
                f"{DIFY_API_URL}/files/upload",
                headers=headers,
                data={"user": DIFY_USER},          # ← required field
                files={"file": (file_name, f, mime_type)},
                timeout=30.0,
            )
        response.raise_for_status()
        return response.json()["id"]


async def run_eval_workflow(
    brand: str,
    model: str,
    year: int,
    original_price: float,
    dify_file_ids: List[str],
) -> dict:
    """Call Workflow 1 (Evaluation) passing Dify file IDs."""
    dify_files_array = [
        {"transfer_method": "local_file", "upload_file_id": fid, "type": "image"}
        for fid in dify_file_ids
    ]
    payload = {
        "inputs": {
            "brand": brand,
            "model": model,
            "year": year,
            "original_price": original_price,
            "images": dify_files_array,
        },
        "response_mode": "blocking",
        "user": DIFY_USER,
    }
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {DIFY_EVAL_API_KEY}",
            "Content-Type": "application/json",
        }
        response = await client.post(
            f"{DIFY_API_URL}/workflows/run",
            headers=headers,
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()["data"]["outputs"]


async def run_publish_workflow(
    title: str,
    description: str,
    price: float,
    grade: str,
) -> dict:
    """Call Workflow 2 (Shopify publication)."""
    payload = {
        "inputs": {
            "title": title,
            "description": description,
            "price": price,
            "grade": grade,
        },
        "response_mode": "blocking",
        "user": DIFY_USER,
    }
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {DIFY_PUBLISH_API_KEY}",
            "Content-Type": "application/json",
        }
        response = await client.post(
            f"{DIFY_API_URL}/workflows/run",
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["data"]["outputs"]