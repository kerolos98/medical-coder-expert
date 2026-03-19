import os
import subprocess
WEIGHTS_PATH = "/data/embeddings"
DRIVE_URL = os.getenv("WEIGHTS_URL")

def download_weights():
    if not os.path.exists(WEIGHTS_PATH):
        os.makedirs(WEIGHTS_PATH, exist_ok=True)
        subprocess.run([
            "gdown",
            "--fuzzy",
            "--folder",  # use only if downloading a folder
            DRIVE_URL,
            "-O",
            WEIGHTS_PATH
        ], check=True)
        print("Download complete.")
    else:
        print("Weights already exist.")