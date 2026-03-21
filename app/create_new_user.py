from database_manager import APIKeys
import datetime
if __name__ == "__main__":
    api_keys_manager = APIKeys()
    owner_name = input("Enter the owner's email (optional): ")
    usage_limit = int(input("Enter the usage limit (default 100): ") or 100)
    created_at = datetime.datetime.now()
    expires_at_input = input("Enter the expiration date (YYYY-MM-DD) (optional): ")
    expires_at = None
    if expires_at_input:
        try:
            expires_at = datetime.datetime.strptime(expires_at_input, "%Y-%m-%d")
        except ValueError:
            print("Invalid date format. Expiration date will be set to None.")
    
    new_key = api_keys_manager.add_regular_user(owner_name, usage_limit, expires_at)
    user_data = api_keys_manager.get_key_info(new_key)
    print(f"New API key created: {new_key}")
    print(f"User data: {user_data}")
    
    