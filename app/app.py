from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.concurrency import run_in_threadpool
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from code_recommender import SemanticCodeRetrieval, Model_Data
from download_weights import download_weights
from database_manager import APIKeys  
# -------------------------
# FastAPI & SlowAPI setup
# -------------------------
api_keys_manager = APIKeys()
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
# -------------------------
# Request schema
# -------------------------
class PredictRequest(BaseModel):
    text: str
    model_type: str  # "icd10", "snomed", or "rx"

# -------------------------
# Placeholders for models
# -------------------------
core = icd10_model = snomed_model = rx_model = None
models = {}
async def validate_api_key(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key missing")
    
    is_valid, msg = api_keys_manager.check_key_validity(x_api_key)
    if not is_valid:
        raise HTTPException(status_code=403, detail=msg)
    
    # Increment usage
    key_info = api_keys_manager.get_key_info(x_api_key)
    current_requests = key_info[4]  # requests_made column
    api_keys_manager.update_requests_made(x_api_key, current_requests + 1)
    
    return x_api_key 

def user_rate_limit(request: Request):
    api_key = request.headers.get("x-api-key")
    if not api_key:
        return "0/minute"  # block requests without key
    limit = api_keys_manager.get_rate_limit(api_key)
    if not limit:
        return "0/minute"
    return f"{limit}/minute"  # e.g., "15/minute"

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
        embeddings_path=Model_Data.ICD10_EMBEDDINGS, 
        pca_json_path=Model_Data.ICD10_PCA
    )
    icd10_model.load_embedding_model_and_embeddings()

    # SNOMED model
    snomed_model = SemanticCodeRetrieval(
        embeddings_path=Model_Data.SNOMED_EMBEDDINGS, 
        pca_json_path=Model_Data.SNOMED_PCA
    )
    snomed_model.load_embedding_model_and_embeddings()

    # RX model
    rx_model = SemanticCodeRetrieval(
        embeddings_path=Model_Data.RX_EMBEDDINGS, 
        pca_json_path=Model_Data.RX_PCA
    )
    rx_model.load_embedding_model_and_embeddings()

    # Map model_type strings to instances
    models = {
        "icd10": icd10_model,
        "snomed": snomed_model,
        "rx": rx_model
    }

# -------------------------
# Prediction function
# -------------------------
def predict_model(text: str, base_model: SemanticCodeRetrieval, core_model: SemanticCodeRetrieval):
    # Use core embedding model for consistency
    base_model.embedding_model = core_model.embedding_model
    base_model.tokenizer = core_model.tokenizer
    return base_model.get_code_recommendation(text)

# -------------------------
# API endpoint
# -------------------------
@app.post("/predict")
@limiter.limit(user_rate_limit)  # dynamic per-user rate
async def predict(payload: PredictRequest, api_key: str = Depends(validate_api_key)):
    try:
        model_type = payload.model_type.lower()

        if model_type not in models:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model_type '{payload.model_type}'. Choose from: {list(models.keys())}"
            )

        base_model = models[model_type]
        # Run prediction in threadpool
        result = await run_in_threadpool(predict_model, payload.text, base_model, core)

        # If we reached here, the request is successful
        api_keys_manager.add_single_request(api_key)  # Log usage

        return {"model_type": model_type, "prediction": result}

    except HTTPException:
        # Do not increment usage if request failed
        raise

    except Exception as e:
        # Optionally log the error for debugging
        print(f"Error during prediction: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
# -------------------------
# Health check endpoint
# -------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/usage")
async def usage(api_key: str = Depends(validate_api_key)):
    key_info = api_keys_manager.get_key_info(api_key)
    if not key_info:
        raise HTTPException(status_code=404, detail="API key not found")
    
    _, _, owner_name, usage_limit, requests_made, last_used, created_at, expires_at = key_info
    return {
        "owner_name": owner_name,
        "usage_limit": usage_limit,
        "requests_made": requests_made,
        "last_used": last_used,
        "created_at": created_at,
        "expires_at": expires_at
    }

@app.get("/")
async def root():
    return {"message": "Medical Code Prediction API running"}