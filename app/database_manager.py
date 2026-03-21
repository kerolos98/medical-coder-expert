import os
import datetime
import sqlite3
import secrets
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from model_input_files_config import API_KEYS_DB_PATH, CREDENTIALS_JSON, API_KEYS_DB_PATH

def upload_db_to_drive():
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile(CREDENTIALS_JSON)
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()  # only if first time
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()
    gauth.SaveCredentialsFile(CREDENTIALS_JSON)

    drive = GoogleDrive(gauth)

    # overwrite existing DB if exists
    file_list = drive.ListFile({'q': "title='api_keys.db' and trashed=false"}).GetList()
    if file_list:
        file_drive = file_list[0]
        file_drive.SetContentFile(API_KEYS_DB_PATH)
        file_drive.Upload()
    else:
        file_drive = drive.CreateFile({'title': 'api_keys.db'})
        file_drive.SetContentFile(API_KEYS_DB_PATH)
        file_drive.Upload()

    print("✅ DB uploaded to Google Drive successfully")

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
        upload_db_to_drive()  

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
        upload_db_to_drive()

    def delete_key(self, key):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("DELETE FROM api_keys WHERE key = ?", (key,))
        self.APIKeys_db.commit()
        upload_db_to_drive()

    def set_usage_limit(self, key, usage_limit):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        UPDATE api_keys
        SET usage_limit = ?
        WHERE key = ?
        """, (usage_limit, key))
        self.APIKeys_db.commit()
        upload_db_to_drive()
    
    def add_regular_user(self, owner_name=None, usage_limit=100, expires_at=None):
        new_key = self.generate_api_key()
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        INSERT INTO api_keys (key, owner_name, usage_limit, expires_at)
        VALUES (?, ?, ?, ?)
        """, (new_key, owner_name, usage_limit, expires_at))
        self.APIKeys_db.commit()
        upload_db_to_drive()
        return new_key
    
    def add_batch_requests(self, key, batch_length):
        cursor = self.APIKeys_db.cursor()
        cursor.execute("""
        INSERT INTO batch_requests (api_key, date, number_of_cases)
        VALUES (?, ?, ?)
        """, (key, datetime.datetime.now(), batch_length))
        self.APIKeys_db.commit()
        upload_db_to_drive()

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
        upload_db_to_drive()
    
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
