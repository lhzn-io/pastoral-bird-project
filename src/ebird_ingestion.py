import os
import requests
import json
from datetime import datetime

# Hotspot IDs for the sanctuary (e.g., Fishers Island main hotspot + others)
HOTSPOT_IDS = ["L619821", "L3562597"]

def fetch_recent_observations(api_key: str, hotspot_ids: list, days_back: int = 7):
    """
    Fetches recent bird observations for a list of eBird hotspots.
    """
    all_observations = []
    
    headers = {
        "x-ebirdapitoken": api_key
    }
    
    params = {
        "back": days_back,
        "includeProvisional": "true",
        "hotspot": "true" 
    }

    for hotspot_id in hotspot_ids:
        url = f"https://api.ebird.org/v2/data/obs/{hotspot_id}/recent"
        try:
            print(f"Fetching data from eBird for hotspot {hotspot_id} (last {days_back} days)...")
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status() 
            
            observations = response.json()
            if observations:
                all_observations.extend(observations)
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data for {hotspot_id}: {e}")

    # Deduplicate by observation ID (obsId) if needed
    # (eBird assigns unique obsIds to sightings)
    unique_obs = {obs['subId'] + obs['speciesCode']: obs for obs in all_observations}.values()
    return list(unique_obs)

def process_and_save(observations):
    """
    Processes the raw observations and saves them locally for inspection.
    In the final GCP architecture, this would stream to BigQuery.
    """
    if not observations:
        print("No observations found or API error.")
        return

    print(f"Successfully retrieved {len(observations)} unique observations across all hotspots.")
    
    if len(observations) > 0:
        print("\n--- Sample Observation Data ---")
        print(json.dumps(observations[0], indent=2))
        print("-------------------------------\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"observations_group_{timestamp}.json"
    
    with open(filename, "w") as f:
        json.dump(observations, f, indent=4)
        
    print(f"Saved complete dataset to {filename}")

if __name__ == "__main__":
    EBIRD_API_KEY = os.environ.get("EBIRD_API_KEY")
    
    if not EBIRD_API_KEY:
        print("ERROR: EBIRD_API_KEY environment variable not set.")
        print("Please get a key from https://ebird.org/api/keygen")
        print("Run the script like this: EBIRD_API_KEY='your_key' python ebird_ingestion.py")
    else:
        obs = fetch_recent_observations(EBIRD_API_KEY, HOTSPOT_IDS, days_back=7)
        process_and_save(obs)
