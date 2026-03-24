import threading
import time
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.concurrency import run_in_threadpool
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from code_recommender import SemanticCodeRetrieval, Model_Data
from download_weights import download_weights
from database_manager import APIKeys, upload_file_to_drive, get_drive_service
from limiter import RateLimiter

# -------------------------
# FastAPI & SlowAPI setup
# -------------------------

app = FastAPI(title="Medical Code Prediction API")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

download_weights()  # Ensure weights are downloaded at startup
api_keys_manager = APIKeys()


def periodic_upload():
    while True:
        time.sleep(240)
        try:
            # Pass the authorized instance to the function
            upload_file_to_drive()
        except Exception as e:
            print(f"Thread Error: {e}")


threading.Thread(target=periodic_upload, daemon=True).start()


# -------------------------
# Request schema
# -------------------------
class PredictRequest(BaseModel):
    text: Optional[str, list]  # Accept either a single string or a list of strings
    model_type: str  # "icd10", "snomed", or "rx"


# -------------------------
# Placeholders for models
# -------------------------
core = icd10_model = snomed_model = rx_model = None
models = {}


async def validate_api_key(request: Request, x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key missing")

    is_valid, msg = api_keys_manager.check_key_validity(x_api_key)
    if not is_valid:
        raise HTTPException(status_code=403, detail=msg)

    # OPTIONAL: attach to request state (very useful)
    request.state.api_key = x_api_key

    return x_api_key


def get_api_key_from_request(request: Request):
    """Extract API key - this identifies WHO is making the request"""
    api_key = request.headers.get("x-api-key")
    if not api_key:
        return "anonymous"
    return api_key


# -------------------------
# Load models at startup
# -------------------------
@app.on_event("startup")
async def load_models():
    global core, icd10_model, snomed_model, rx_model, models

    # Core embedding model
    core = SemanticCodeRetrieval(model_path=Model_Data.EMBEDDINGS_MODEL)
    core.load_model()

    # ICD10 model
    icd10_model = SemanticCodeRetrieval(
        embeddings_path=Model_Data.ICD10_EMBEDDINGS, pca_json_path=Model_Data.ICD10_PCA
    )
    icd10_model.load_embedding_model_and_embeddings()

    # SNOMED model
    snomed_model = SemanticCodeRetrieval(
        embeddings_path=Model_Data.SNOMED_EMBEDDINGS,
        pca_json_path=Model_Data.SNOMED_PCA,
    )
    snomed_model.load_embedding_model_and_embeddings()

    # RX model
    rx_model = SemanticCodeRetrieval(
        embeddings_path=Model_Data.RX_EMBEDDINGS, pca_json_path=Model_Data.RX_PCA
    )
    rx_model.load_embedding_model_and_embeddings()

    # Map model_type strings to instances
    models = {"icd10": icd10_model, "snomed": snomed_model, "rx": rx_model}


# -------------------------
# Prediction function
# -------------------------
def predict_model(
    text: str, base_model: SemanticCodeRetrieval, core_model: SemanticCodeRetrieval
):
    # Use core embedding model for consistency
    base_model.embedding_model = core_model.embedding_model
    base_model.tokenizer = core_model.tokenizer
    return base_model.get_code_recommendation(text)


# -------------------------
# API endpoint
# -------------------------
custom_limiter = RateLimiter()


@app.post("/predict")
async def predict(
    request: Request, payload: PredictRequest, api_key: str = Depends(validate_api_key)
):
    # Get the user's rate limit
    user_limit = api_keys_manager.get_rate_limit(api_key)

    if not user_limit:
        raise HTTPException(
            status_code=403, detail="No rate limit configured for this API key"
        )

    # Check rate limit - this maintains separate counters per api_key
    custom_limiter.check_limit(api_key, user_limit, window_seconds=60)

    # Process the request
    model_type = payload.model_type.lower()

    if model_type not in models:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model_type '{payload.model_type}'. Choose from: {list(models.keys())}",
        )

    base_model = models[model_type]
    result = await run_in_threadpool(predict_model, payload.text, base_model, core)
    if isinstance(result, Exception):
        raise HTTPException(status_code=500, detail=str(result))
    if isinstance(payload.text, list):
        api_keys_manager.add_bulk_requests(api_key, len(payload.text))
    else:
        api_keys_manager.add_single_request(api_key)
    api_keys_manager.increment_requests(api_key)
    return {"model_type": model_type, "prediction": result}


# -------------------------
# Health check endpoint
# -------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/usage")
@limiter.limit("5/minute")
async def usage(request: Request, api_key: str = Depends(validate_api_key)):
    key_info = api_keys_manager.get_key_info(api_key)
    if not key_info:
        raise HTTPException(status_code=404, detail="API key not found")

    _, _, owner_name, usage_limit, requests_made, last_used, created_at, expires_at = (
        key_info
    )
    return {
        "owner_name": owner_name,
        "usage_limit": usage_limit,
        "requests_made": requests_made,
        "last_used": last_used,
        "created_at": created_at,
        "expires_at": expires_at,
    }


@app.get("/")
async def root():
    return {"message": "Medical Code Prediction API running"}
