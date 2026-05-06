import os
import json
import argparse
from google.cloud import bigquery
from dotenv import load_dotenv

# We import kanoa instead of the raw GenAI SDK
from kanoa import AnalyticsInterpreter

# Load .env file (to pick up GEMINI_API_KEY if present, and EBIRD_API_KEY)
load_dotenv()

PROJECT_ID = os.environ.get("GCP_PROJECT", "longhorizon")
DATASET_ID = "field_journal"

# Initialize BigQuery (still relies on Application Default Credentials for BQ)
bq_client = bigquery.Client(project=PROJECT_ID)

def fetch_recent_data_from_bq(hotspots, days_back=7):
    """
    Fetches the deduplicated, latest state of observations 
    from the current_ebird_observations view.
    """
    if not hotspots:
        raise ValueError("At least one hotspot ID must be provided.")

    query = f"""
        SELECT 
            speciesCode,
            comName,
            MAX(obsDt) as last_seen,
            SUM(howMany) as total_count,
            COUNT(DISTINCT subId) as checklist_count
        FROM `{PROJECT_ID}.{DATASET_ID}.current_ebird_observations`
        WHERE locId IN UNNEST(@hotspots)
          AND obsDt >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL @days DAY)
        GROUP BY speciesCode, comName
        ORDER BY total_count DESC
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("hotspots", "STRING", hotspots),
            bigquery.ScalarQueryParameter("days", "INT64", days_back)
        ]
    )
    
    results = bq_client.query(query, job_config=job_config).result()
    return [dict(row) for row in results]

def generate_blog_post(bird_data, days_back=7, theme="field_journal"):
    """
    Uses the kanoa AnalyticsInterpreter to generate the entry.
    """
    with open("prompts.json", "r") as f:
        prompts = json.load(f)
        
    theme_prompts = prompts.get(theme)
    if not theme_prompts:
        raise ValueError(f"Theme '{theme}' not found in prompts.json")
    
    system_prompt = theme_prompts["system_prompt"]
    user_prompt_template = theme_prompts["user_prompt_template"]

    print(f"Initializing kanoa AnalyticsInterpreter (Theme: {theme})...")
    
    # Initialize kanoa using Google AI Studio via the 'gemini' backend
    # Note: kanoa will automatically pick up GEMINI_API_KEY from the environment
    interp = AnalyticsInterpreter(
        backend="gemini",
        model="gemini-3.1-flash-lite-preview"
    )
    
    # Override kanoa's default prompts with our specialized ones
    interp.set_prompts(
        system_prompt=system_prompt,
        user_prompt=user_prompt_template
    )
    
    print("Generating interpretation...")
    
    try:
        # kanoa handles data serialization and prompt assembly internally
        result = interp.interpret(
            data=bird_data,
            context=f"Sighting data from the sanctuary over the last {days_back} days.",
            stream=False,
            display_result=False
        )
        return result.text
    except Exception as e:
        print(f"kanoa Generation Failed: {e}")
        return "Generation failed due to API configuration or kanoa error."

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Field Journal from BigQuery eBird Data")
    parser.add_argument("--hotspots", nargs="+", required=True, help="List of eBird Hotspot IDs (e.g. L619821 L3562597)")
    parser.add_argument("--days", type=int, default=7, help="Number of days back to query (default: 7)")
    parser.add_argument("--theme", type=str, default="field_journal", help="Theme prompt to use from prompts.json")
    
    args = parser.parse_args()

    print(f"Fetching curated data from BigQuery for hotspots: {args.hotspots}...")
    recent_birds = fetch_recent_data_from_bq(hotspots=args.hotspots, days_back=args.days)
    
    if not recent_birds:
        print(f"No birds observed in the last {args.days} days for these hotspots. Exiting.")
    else:
        print(f"Found {len(recent_birds)} unique species in the last week.")
        
        post = generate_blog_post(recent_birds, days_back=args.days, theme=args.theme)
        
        print("\n" + "="*50)
        print(f"GENERATED {args.theme.replace('_', ' ').upper()} ENTRY")
        print("="*50 + "\n")
        print(post)
