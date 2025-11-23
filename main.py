import os
import json
import tempfile
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import gspread
from dotenv import load_dotenv
from cachetools import TTLCache, cached

# Load local environment variables from .env
load_dotenv()

app = FastAPI(title="Dog Profiles API")

# Environment variables
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "30"))

# Ensure env vars are set
if not SPREADSHEET_ID:
    raise RuntimeError("Missing SPREADSHEET_ID environment variable")


# Cache to avoid hitting Google Sheets on every request
cache = TTLCache(maxsize=1, ttl=CACHE_TTL_SECONDS)

# Pydantic model (optional, helps with validation / docs)
class DogProfile(BaseModel):
    dog_id: str
    dog: dict
    owner: dict
    feeding: dict
    walks: dict
    behavior: dict

# Create gspread client from service account JSON
def get_gspread_client():
    try:
        service_json = os.getenv("GOOGLE_SERVICE_KEY")
    
        if not service_json:
            raise RuntimeError("Missing GOOGLE_SERVICE_KEY environment variable")
    
        # Convert JSON string → Python dict
        credentials_dict = json.loads(service_json)
    
        # Write credentials to a temporary file (gspread requires a filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp:
            temp.write(json.dumps(credentials_dict).encode("utf-8"))
            temp_path = temp.name
    
        return gspread.service_account(filename=temp_path)
    except Exception as e:
        print("ERROR in get_gspread_client:", repr(e))  # Logs full error
        raise RuntimeError(f"Failed to create gspread client: {repr(e)}")

# Read all rows from sheet with caching
@cached(cache)
def get_all_rows():
    client = get_gspread_client()
    sheet = client.open_by_key(SPREADSHEET_ID)
    ws = sheet.sheet1  # first sheet
    return ws.get_all_records()

# Map a row from Google Sheet into structured JSON
def map_row_to_dog(row, idx):
    return {
        "dog_id": row.get("dog_id") or str(idx),
        "dog": {
            "name": row.get("Name"),
            "age": row.get("Age"),
            "sex": row.get("Sex"),
            "photo_url": row.get("Photo")
        },
        "owner": {
            "name": row.get("Pet owner's name"),
            "phone": row.get("Pet owner's phone"),
            "preferred_contact": row.get("Preferred contact method")
        },
        "feeding": {
            "times": row.get("Feeding times (you can choose more than one answer)"),
            "amount": row.get("  Amount of food per meal  "),
            "allergies": row.get("Food or environmental intolerances "),
            "allergies_detail": row.get("If yes, please details of any food or environmental intolerances:")
        },
        "walks": {
            "frequency": row.get("Going for walks (you can choose more than one answer)"),
            "duration": row.get("Approximate duration of each walk (in minutes): ")
        },
        "behavior": {
            "barks_in_reaction_to": row.get("Barks in reaction to (If none, please just write 'None'):"),
            "afraid_of": row.get("Is afraid of (If none, please just write 'None'):"),
            "owners_remark": row.get("Some remarks we need to know:"),
            "medical_conditions": row.get("Medical conditions / needs (optional)")
        }
    }

# Endpoint: return all dogs
@app.get("/dogs")
def get_dogs(dog_name: str | None = Query(None), owner_name: str | None = Query(None)):
    """
    Optional query parameters:
    - dog_name: filter by dog name (case-insensitive substring)
    - owner_name: filter by owner name (case-insensitive substring)
    """
    try:
        rows = get_all_rows()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read sheet: {str(e)}")

    filtered = []
    for idx, row in enumerate(rows, start=1):
        dog_obj = map_row_to_dog(row, idx)

        # Filter by dog_name if provided
        if dog_name and dog_name.lower() not in (dog_obj["dog"]["name"] or "").lower():
            continue

        # Filter by owner_name if provided
        if owner_name and owner_name.lower() not in (dog_obj["owner"]["name"] or "").lower():
            continue

        filtered.append(dog_obj)

    return filtered

# Endpoint: return one dog by dog_id
@app.get("/dogs/{dog_id}")
def get_dog(dog_id: str):
    try:
        rows = get_all_rows()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read sheet: {str(e)}")

    for idx, row in enumerate(rows, start=1):
        row_id = row.get("dog_id") or str(idx)
        if str(row_id) == dog_id:
            return map_row_to_dog(row, idx)

    raise HTTPException(status_code=404, detail="Dog not found")
