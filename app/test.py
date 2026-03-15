import requests

# Base URL of your API
BASE_URL = "http://127.0.0.1:8000"

def test_model(model_type, text):
    """
    model_type: 'icd10', 'snomed', or 'rx'
    text: text to send to the model
    """
    url = f"{BASE_URL}/predict"
    data = {"text": text, "model_type": model_type}
    
    response = requests.post(url, json=data)
    if response.status_code == 200:
        print(f"--- {model_type.upper()} ---")
        print(response.json())
    else:
        print(f"Error {response.status_code} for {model_type}: {response.text}")


# Example usage
test_model("icd10", "Patient has type 2 diabetes with neuropathy.")
test_model("snomed", "Patient presents with high blood pressure and dizziness.")
test_model("rx", "Prescribe metformin 500mg twice daily.")