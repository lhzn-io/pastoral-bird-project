import os
import json
import hashlib
import requests
from google.cloud import bigquery
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Initialize BigQuery Client
bq_client = bigquery.Client(project="longhorizon")
PROJECT_ID = "longhorizon"
DATASET_ID = "field_journal"

def setup_bigquery():
    """Creates dataset and tables based on the SQL schema."""
    print(f"Setting up BigQuery Dataset: {DATASET_ID}")
    
    # Create dataset if it doesn't exist
    dataset = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
    dataset.location = "US"
    try:
        dataset = bq_client.create_dataset(dataset, exists_ok=True)
        print(f"Dataset {dataset.dataset_id} is ready.")
    except Exception as e:
        print(f"Error creating dataset: {e}")
        return False

    # Execute schema SQL
    with open("bigquery_schema.sql", "r") as f:
        sql = f.read()
    
    try:
        print("Executing schema DDL...")
        # Split by empty lines to run table creation individually, or run as a script.
        # BigQuery Python client supports script execution.
        query_job = bq_client.query(sql)
        query_job.result()
        print("Schema execution successful.")
        return True
    except Exception as e:
        print(f"Error executing schema: {e}")
        return False

def generate_unique_id(obs):
    return f"{obs['subId']}_{obs['speciesCode']}"

def generate_payload_hash(obs):
    payload_str = json.dumps(obs, sort_keys=True)
    return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

def fetch_ebird_data(api_key: str, hotspot_ids: list, days_back: int = 7):
    all_observations = []
    headers = {"x-ebirdapitoken": api_key}
    params = {"back": days_back, "includeProvisional": "true", "hotspot": "true"}

    for hotspot_id in hotspot_ids:
        url = f"https://api.ebird.org/v2/data/obs/{hotspot_id}/recent"
        try:
            print(f"Fetching data from eBird for hotspot {hotspot_id}...")
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status() 
            
            observations = response.json()
            if observations:
                all_observations.extend(observations)
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data for {hotspot_id}: {e}")

    unique_obs = {obs['subId'] + obs['speciesCode']: obs for obs in all_observations}.values()
    return list(unique_obs)

def ingest_to_bigquery():
    api_key = os.environ.get("EBIRD_API_KEY")
    hotspots = ["L619821", "L3562597"] 
    
    observations = fetch_ebird_data(api_key, hotspots, days_back=30)
    
    if not observations:
        print("No data fetched")
        return

    rows_to_insert = []
    for obs in observations:
        rows_to_insert.append({
            "obs_id": generate_unique_id(obs),
            "payload_hash": generate_payload_hash(obs),
            "subId": obs["subId"],
            "locId": obs["locId"],
            "speciesCode": obs["speciesCode"],
            "comName": obs.get("comName", ""),
            "obsDt": obs["obsDt"] if len(obs["obsDt"]) > 16 else obs["obsDt"] + ":00", 
            "howMany": obs.get("howMany"),
            "ingestedAt": datetime.utcnow().isoformat(),
            "rawPayload": json.dumps(obs)
        })

    target_table = f"{PROJECT_ID}.{DATASET_ID}.raw_ebird_observations_ledger"
    temp_table_id = f"{PROJECT_ID}.{DATASET_ID}.temp_ingest_{int(datetime.utcnow().timestamp())}"
    
    # 1. Load data to temp table
    job_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("obs_id", "STRING"),
            bigquery.SchemaField("payload_hash", "STRING"),
            bigquery.SchemaField("subId", "STRING"),
            bigquery.SchemaField("locId", "STRING"),
            bigquery.SchemaField("speciesCode", "STRING"),
            bigquery.SchemaField("comName", "STRING"),
            bigquery.SchemaField("obsDt", "DATETIME"),
            bigquery.SchemaField("howMany", "INTEGER"),
            bigquery.SchemaField("ingestedAt", "TIMESTAMP"),
            bigquery.SchemaField("rawPayload", "STRING"),
        ],
        write_disposition="WRITE_TRUNCATE",
    )
    
    try:
        print(f"Loading data to temp table {temp_table_id}...")
        load_job = bq_client.load_table_from_json(rows_to_insert, temp_table_id, job_config=job_config)
        load_job.result()
    except Exception as e:
        print(f"Failed to load temp table: {e}")
        return

    # 2. Execute MERGE from temp table
    query = f"""
    MERGE `{target_table}` T
    USING `{temp_table_id}` S
    ON T.obs_id = S.obs_id AND T.payload_hash = S.payload_hash
    
    WHEN NOT MATCHED THEN
      INSERT (obs_id, payload_hash, subId, locId, speciesCode, comName, obsDt, howMany, ingestedAt, rawPayload)
      VALUES (S.obs_id, S.payload_hash, S.subId, S.locId, S.speciesCode, S.comName, S.obsDt, S.howMany, S.ingestedAt, PARSE_JSON(S.rawPayload))
    """

    try:
        print(f"Executing MERGE into {target_table} with {len(rows_to_insert)} records...")
        query_job = bq_client.query(query)
        query_job.result()
        print(f"Successfully ran ingestion MERGE.")
    except Exception as e:
        print(f"BigQuery insertion failed: {e}")
    finally:
        # Cleanup temp table
        bq_client.delete_table(temp_table_id, not_found_ok=True)
        print("Cleaned up temp table.")

if __name__ == "__main__":
    if not os.environ.get("EBIRD_API_KEY"):
        print("Please set EBIRD_API_KEY")
    else:
        if setup_bigquery():
            ingest_to_bigquery()
