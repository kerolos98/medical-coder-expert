import os
import subprocess
WEIGHTS_PATH = "/data/embeddings"
DRIVE_URL = os.getenv("WEIGHTS_URL")

def download_weights():
    if not os.path.exists(WEIGHTS_PATH):
        os.makedirs(WEIGHTS_PATH, exist_ok=True)
        subprocess.run([
        "gdown",
        "--folder",
        "URL",
        "-O",
        WEIGHTS_PATH
    ])
        print("Download complete.")
    else:
        print("Weights already exist.")
