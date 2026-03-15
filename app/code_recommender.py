import numpy as np
import re 
import math
import faiss
import h5py
import torch
from transformers import AutoTokenizer, AutoModel
from sklearn.decomposition import PCA
from typing import Union
import json
import model_input_files_config as Model_Data

ICD10_REGEX = re.compile(
    r'\b[A-TV-Z][0-9]{2}(?:\.[0-9A-Z]{1,4}|[0-9A-Z]{1,2})?\b',
    re.IGNORECASE
)

def get_code_recommendation(text: str) -> bool:
    """
    Return True if any ICD-10 code exists in the text.
    """
    if not text.strip():
        return True # Empty text treated as containing ICD-10 to skip it anyway

    return bool(ICD10_REGEX.search(text))

class SemanticCodeRetrieval:
    def __init__(self, 
                 model_path: str = None,
                 embeddings_path: str = None,
                 pca_json_path: str = None,
                 rank: int = 5,
                 nlist: int = 100,
                 nprobe: int = 10,
                 confidence_threshold: float = 50.0):
        self.model_path = model_path
        self.embeddings_path = embeddings_path
        self.rank = rank
        self.confidence_threshold = confidence_threshold
        self.device = torch.device("cpu")  # CPU-only
        self.embedding_model = None
        self.tokenizer = None
        self.pca_path = pca_json_path
        self.pca = None
        self.embeddings = None
        self.index_embeddings = None
        self.code_to_disc = {}

        # IVF parameters
        self.nlist = nlist
        self.nprobe = nprobe

    def load_pca_from_json(self, json_path):
        with open(json_path, "r") as f:
            data = json.load(f)
        pca = PCA(n_components=len(data["components"]))
        pca.components_ = np.array(data["components"])
        pca.mean_ = np.array(data["mean"])
        pca.explained_variance_ = np.array(data["explained_variance"])
        pca.explained_variance_ratio_ = np.array(data["explained_variance_ratio"])
        return pca

    def load_model(self):
        """Lazy loading with quantization for CPU speed."""
        if (not self.tokenizer or not self.embedding_model) and self.model_path:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            model = AutoModel.from_pretrained(self.model_path).eval()
            # Dynamic quantization for CPU
            self.embedding_model = torch.quantization.quantize_dynamic(
                model, {torch.nn.Linear}, dtype=torch.qint8
            )

    def load_embedding_model_and_embeddings(self):
        """Loads quantized SapBERT and PCA-reduced embeddings."""
        self.load_model()
        self.pca = self.load_pca_from_json(self.pca_path)
        with h5py.File(self.embeddings_path, 'r') as f:
            sentences = [x.decode('utf-8') for x in f['sentences'][:]]  
            codes = [x.decode('utf-8') for x in f['codes'][:]] 
            embeddings = f['embeddings'][:]  # Already PCA-reduced
            self.code_to_disc = dict(zip(codes,sentences))
            self.embeddings = {'embeddings': embeddings, 'codes': codes, 'sentences': sentences}
        self.create_index()

    def embed_sapbert(self, texts: list) -> np.ndarray:
        """Generate quantized SapBERT embeddings for texts."""
        self.embedding_model.eval()
        all_embeddings = []
        batch_size = 16
        texts = [text.lower().replace("risk", "").replace("moderate", "").strip() for text in texts]
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            enc = self.tokenizer(batch, padding=True, truncation=True, max_length=128, return_tensors='pt')
            input_ids = enc['input_ids']
            attention_mask = enc['attention_mask']
            with torch.no_grad():
                output = self.embedding_model(input_ids=input_ids, attention_mask=attention_mask)
                cls_embeddings = output.last_hidden_state[:, 0, :].numpy()
            reduced = self.pca.transform(cls_embeddings)  # Apply PCA
            all_embeddings.append(reduced)
        return np.vstack(all_embeddings).astype(np.float32)

    def create_index(self):
        """Create FAISS IVF index for fast similarity search."""
        dim = self.embeddings['embeddings'].shape[1]
        quantizer = faiss.IndexFlatL2(dim)
        index = faiss.IndexIVFFlat(quantizer, dim, self.nlist)
        
        vectors = np.array(self.embeddings['embeddings']).astype(np.float32)
        index.train(vectors)
        index.add(vectors)
        index.nprobe = self.nprobe  # How many clusters to search

        self.index_embeddings = index

    def calculate_confidence(self, distance: float, sigma: float = 1000) -> float:
        confidence = math.exp(-distance / sigma)
        return round(confidence * 100, 2)
    
    
    def get_code(self, text: list, top_k: int = 100) -> list:
        """
        Recommend top-1 ICD-10 code for each input text using
        top-k nearest neighbors to compute softmax-based confidence.
        """
        predictions = []
        query_embeddings = self.embed_sapbert(text)

        # Ensure top_k does not exceed the number of embeddings
        actual_k = min(top_k, len(self.embeddings['embeddings']))

        distances, indices = self.index_embeddings.search(query_embeddings, actual_k)

        for idx, (dist_row, idx_row) in enumerate(zip(distances, indices)):
            # Numerically stable conversion to similarity
            shifted = dist_row - np.min(dist_row)  # shift so min distance = 0
            similarities = np.exp(-shifted)
            sum_sim = similarities.sum()
            if get_code_recommendation(text[idx]):
                predictions.append({
                    "input": text[idx],
                    "sentence": None,
                    "code": None,
                    "distance": None,
                    "confidence": 100.0,
                    "rank": 1,
                    "note": "Input may not be a valid diagnosis"
                })
                continue
            if sum_sim < 1e-8:  # all distances too large → treat as unknown
                confidence = 0.0
            else:
                confidences = similarities / sum_sim * 100
                confidence = float(round(float(confidences[0]), 2))  # only top-1

            # Only take the top-1 ICD-10
            top_idx = idx_row[0]
            top_distance = float(dist_row[0])
            top_icd10 = self.embeddings['codes'][top_idx]
            top_sentence = self.embeddings['sentences'][top_idx]

            # Optionally, apply a confidence threshold
            if confidence >= self.confidence_threshold:
                predictions.append({
                    "input": text[idx],
                    "sentence": top_sentence,
                    "code": top_icd10,
                    "distance": top_distance,
                    "confidence": confidence,
                    "rank": 1
                })
            else:
                predictions.append({
                    "input": text[idx],
                    "sentence": None,
                    "code": None,
                    "distance": None,
                    "confidence": confidence,
                    "rank": 1,
                    "note": "Input may not be a valid diagnosis"
                })

        return predictions

    def get_code_recommendation(self, text: Union[str, list]) -> list:
        if isinstance(text, str):
            return self.get_code([text])
        elif isinstance(text, list):
            return self.get_code(text)


if __name__ == "__main__":
    print("Select model to use:")
    print("1. ICD-10 Diagnosis")
    print("2. CPT Procedures")
    print("3. RX Medications")
    print("4. LOINC labs")
    choice = input("Model> ")

    if choice == "1":
        recommender = SemanticCodeRetrieval(
            Model_Data.EMBEDDINGS_MODEL,
            Model_Data.ICD10_EMBEDDINGS,
            Model_Data.ICD10_PCA
        )
    elif choice == "3":
        recommender = SemanticCodeRetrieval(
            Model_Data.EMBEDDINGS_MODEL,
            Model_Data.RX_EMBEDDINGS,
            Model_Data.RX_PCA
        )


    recommender.load_embedding_model_and_embeddings()

    while True:
        text = input("Text to lookup > ")
        predictions = recommender.get_code_recommendation(text)
        for entry in predictions:
            print(f"  Sentence   : {entry['sentence']}")
            print(f"  ICD-10     : {entry['code']}")
            print(f"  Confidence : {entry['confidence']}%")
