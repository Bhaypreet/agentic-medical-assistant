import os
import googlemaps
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_MAPS_API_KEY")

print("Key loaded:", bool(api_key), "| length:", len(api_key) if api_key else 0)

gmaps = googlemaps.Client(key=api_key)

try:
    result = gmaps.places(query="Cardiologist near Delhi")
    print("STATUS:", result.get("status"))
    print("ERROR MESSAGE:", result.get("error_message"))
    print("RESULTS COUNT:", len(result.get("results", [])))
except Exception as e:
    print("EXCEPTION:", type(e).__name__, "-", str(e))