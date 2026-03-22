import os
import datetime
import sqlite3
import secrets
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2 import service_account
from model_input_files_config import API_KEYS_DB_PATH, CREDENTIALS_JSON
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = CREDENTIALS_JSON
FOLDER_ID = os.getenv("WEIGHTS_URL").split("/")[-1].split("?")[0]


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def upload_file_to_drive(file_path=API_KEYS_DB_PATH, file_name="api_keys.db"):
    service = get_drive_service()

    # 1. Check if the file already exists in that specific folder
    query = f"name='{file_name}' and '{FOLDER_ID}' in parents and trashed=false"
    response = service.files().list(
        q=query,
        spaces='drive',
        fields='nextPageToken, files(id, name, parents)', # Get more info for debugging
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        driveId=None, # Leave as None unless using a Shared Drive (Team Drive)
    ).execute()
    
    files = response.get('files', [])
    media = MediaFileUpload(file_path, resumable=True)

    try:
        if files:
            # 2. UPDATE: This modifies the file already in YOUR storage
            file_id = files[0]['id']
            file = service.files().update(
                fileId=file_id,
                media_body=media,
                supportsAllDrives=True
            ).execute()
            print(f"✅ Existing DB updated: {file_id}")
        else:
            # 3. CREATE: Explicitly set the parent to YOUR shared folder
            file_metadata = {
                'name': file_name,
                'parents': [FOLDER_ID] 
            }
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            ).execute()
            file_id = file.get('id')
            print(f"✅ New DB created in shared folder")
            
        return file_id

    except Exception as e:
        print(f"❌ Upload logic failed: {e}")
        raise e

class APIKeys:
    def __init__(self, db_path=API_KEYS_DB_PATH):
        self.APIKeys_db = sqlite3.connect(db_path)

    def save_to_db(self, key, owner_name=None, usage_limit=1000, created_at=None, expires_at=None):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        INSERT INTO api_keys (key, owner_name, usage_limit, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """, (key, owner_name, usage_limit, created_at, expires_at))
        self.APIKeys_db.commit()
        

    def get_key_info(self, key):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("SELECT * FROM api_keys WHERE key = ?", (key,))
        return cursor.fetchone()
    
    def check_key_validity(self, key):
        key_info = self.get_key_info(key)
        if not key_info:
            return False, "Key not found"
        
        id, key, owner_name, usage_limit, requests_made, created_at, expires_at = key_info
        
        if expires_at and expires_at < datetime.datetime.now():
            return False, "Key expired"
        
        if requests_made >= usage_limit:
            return False, "Usage limit exceeded"
        
        return True, "Key is valid"
    
    def update_requests_made(self, key, requests_made):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        UPDATE api_keys
        SET requests_made = ?
        WHERE key = ?
        """, (requests_made, key))
        self.APIKeys_db.commit()
        

    def delete_key(self, key):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("DELETE FROM api_keys WHERE key = ?", (key,))
        self.APIKeys_db.commit()
        

    def set_usage_limit(self, key, usage_limit):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        UPDATE api_keys
        SET usage_limit = ?
        WHERE key = ?
        """, (usage_limit, key))
        self.APIKeys_db.commit()
        
    def increment_requests(self, key):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
            UPDATE api_keys
            SET requests_made = requests_made + 1
            WHERE key = ?
        """, (key,))
        self.APIKeys_db.commit()

    def add_regular_user(self, owner_name=None, usage_limit=100, expires_at=None):
        new_key = self.generate_api_key()
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        INSERT INTO api_keys (key, owner_name, usage_limit, expires_at)
        VALUES (?, ?, ?, ?)
        """, (new_key, owner_name, usage_limit, expires_at))
        self.APIKeys_db.commit()
        return new_key
    
    def add_batch_requests(self, key, batch_length):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        INSERT INTO batch_requests (api_key, date, number_of_cases)
        VALUES (?, ?, ?)
        """, (key, datetime.datetime.now(), batch_length))
        self.APIKeys_db.commit()
        

    def get_batch_requests(self, key):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        SELECT date, number_of_cases FROM batch_requests
        WHERE api_key = ?
        """, (key,))
        return cursor.fetchall()
    
    def add_single_request(self, key):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        INSERT INTO single_requests (api_key, date)
        VALUES (?, ?)
        """, (key, datetime.datetime.now()))
        self.APIKeys_db.commit()
        
    
    def get_single_requests(self, key):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        SELECT date FROM single_requests
        WHERE api_key = ?
        """, (key,))
        return cursor.fetchall()
    
    def get_rate_limit(self, key):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("SELECT usage_limit FROM api_keys WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result[0] if result else None    
    
    def generate_api_key(self):
        return secrets.token_hex(16)
