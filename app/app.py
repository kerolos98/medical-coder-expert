from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from fastapi.concurrency import run_in_threadpool
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from code_recommender import SemanticCodeRetrieval, Model_Data
from download_weights import download_weights
# -------------------------
# FastAPI & SlowAPI setup
# -------------------------
app = FastAPI(title="Medical Code Prediction API")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
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
@limiter.limit("20/minute")  # Limit 20 requests/min per IP
async def predict(request: Request, payload: PredictRequest):
    model_type = payload.model_type.lower()
    
    if model_type not in models:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown model_type '{payload.model_type}'. Choose from: {list(models.keys())}"
        )
    
    base_model = models[model_type]
    result = await run_in_threadpool(predict_model, payload.text, base_model, core)
    return {"model_type": model_type, "prediction": result}

# -------------------------
# Health check endpoint
# -------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Medical Code Prediction API running"}