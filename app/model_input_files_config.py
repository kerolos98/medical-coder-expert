import os
BASE_PATH = os.path.dirname(os.path.realpath(__file__))
FOLDER_NAME = "/data/embeddings"
FOLDER_PATH = os.path.join(BASE_PATH, FOLDER_NAME)

EMBEDDINGS_MODEL = f"{FOLDER_PATH}/sapbert"
SNOMED_EMBEDDINGS = f"{FOLDER_PATH}/sapbert_snomed_embeddings.h5"
SNOMED_PCA = f"{FOLDER_PATH}/pca_768_to_256_SNOMED.json"
ICD10_EMBEDDINGS = f"{FOLDER_PATH}/SapBERT_diag_embeddings.h5"
ICD10_PCA = f"{FOLDER_PATH}/pca_768_to_256_diag.json"
RX_EMBEDDINGS = f"{FOLDER_PATH}/sapbert_rx_embeddings_95var.h5"
RX_PCA = f"{FOLDER_PATH}/pca_768_to_95var_rx.json"
WEIGHTS_DIR = "/data/embeddings"
API_KEYS_DB_PATH = "/data/embeddings/api_keys.db"