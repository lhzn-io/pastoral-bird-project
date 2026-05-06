import os
import json
import requests
from google.cloud import bigquery
from datetime import datetime

# Initialize BigQuery Client
bq_client = bigquery.Client()
PROJECT_ID = os.environ.get("GCP_PROJECT", "your_project")
DATASET_ID = "field_journal"
TABLE_ID = "raw_ebird_observations"

def generate_unique_id(obs):
    """
    eBird doesn't provide a unique ID per *sighting*, only per checklist (subId).
    A unique sighting is the combination of the checklist ID and the species code.
    """
    return f"{obs['subId']}_{obs['speciesCode']}"

def fetch_ebird_data(api_key, loc_ids, days_back=7):
    # (Implementation remains the same as our previous script)
    # Returns a list of observation dictionaries
    pass

import hashlib

def generate_payload_hash(obs):
    """
    Creates a deterministic SHA256 hash of the JSON payload.
    Used to detect if the data has changed since we last saw it.
    """
    # Sort keys to ensure deterministic hashing
    payload_str = json.dumps(obs, sort_keys=True)
    return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

def ingest_to_bigquery(request):
    """
    HTTP Cloud Function entrypoint.
    Executes an Append-Only Ledger Insert (Bitemporal pattern).
    """
    api_key = os.environ.get("EBIRD_API_KEY")
    hotspots = ["L619821", "L3562597"] 
    
    observations = fetch_ebird_data(api_key, hotspots, days_back=7)
    
    if not observations:
        return "No data fetched", 200

    rows_to_insert = []
    for obs in observations:
        rows_to_insert.append({
            "obs_id": generate_unique_id(obs),
            "payload_hash": generate_payload_hash(obs),
            "subId": obs["subId"],
            "locId": obs["locId"],
            "speciesCode": obs["speciesCode"],
            "comName": obs.get("comName"),
            "obsDt": obs["obsDt"], 
            "howMany": obs.get("howMany"),
            "ingestedAt": datetime.utcnow().isoformat(),
            "rawPayload": json.dumps(obs)
        })

    # 2. The Append-Only Ledger Strategy
    # We MERGE on both obs_id AND payload_hash. If the hash has changed 
    # (e.g. an eBird reviewer updated 'howMany'), this is evaluated as NOT MATCHED
    # and we INSERT the new row, preserving the old version in the ledger.
    
    target_table = f"{PROJECT_ID}.{DATASET_ID}.raw_ebird_observations_ledger"
    
    query = f"""
    MERGE `{target_table}` T
    USING (
      SELECT * FROM UNNEST(@new_data)
    ) S
    ON T.obs_id = S.obs_id AND T.payload_hash = S.payload_hash
    
    -- We NEVER UPDATE in a ledger pattern. We only append net-new states.
    WHEN NOT MATCHED THEN
      INSERT (obs_id, payload_hash, subId, locId, speciesCode, comName, obsDt, howMany, ingestedAt, rawPayload)
      VALUES (S.obs_id, S.payload_hash, S.subId, S.locId, S.speciesCode, S.comName, S.obsDt, S.howMany, S.ingestedAt, S.rawPayload)
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter(
                "new_data",
                "STRUCT<obs_id STRING, payload_hash STRING, subId STRING, locId STRING, speciesCode STRING, comName STRING, obsDt STRING, howMany INT64, ingestedAt TIMESTAMP, rawPayload STRING>",
                rows_to_insert
            )
        ]
    )

    try:
        query_job = bq_client.query(query, job_config=job_config)
        query_job.result()  # Wait for the job to complete
        
        return f"Successfully merged {len(rows_to_insert)} records.", 200
    except Exception as e:
        print(f"BigQuery insertion failed: {e}")
        return "Internal Server Error", 500
