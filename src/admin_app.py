import os
import json
import uuid
import streamlit as st
import pandas as pd
from google.cloud import bigquery
from dotenv import load_dotenv
from kanoa import AnalyticsInterpreter
import matplotlib.pyplot as plt

# Load Environment Variables
load_dotenv()
PROJECT_ID = os.environ.get("GCP_PROJECT", "longhorizon")
DATASET_ID = "field_journal"

st.set_page_config(page_title="Field Journal Pipeline Builder", layout="wide")

@st.cache_resource
def get_bq_client():
    return bigquery.Client(project=PROJECT_ID)

def fetch_bq_data(hotspots, days_back=7):
    client = get_bq_client()
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
    return client.query(query, job_config=job_config).to_dataframe()

st.title("🪶 Field Journal Pipeline Builder")
st.markdown("Design automated analytical pipelines using sequential data, execution, and synthesis steps.")

# Sidebar Settings
st.sidebar.header("1. Global AI Routing")
# Made Mac Studio the default per request
backend_choice = st.sidebar.radio("AI Provider", ["Lab Mac Studio (Ollama)", "Google AI Studio"], index=0)

kanoa_config = {}
if backend_choice == "Google AI Studio":
    kanoa_config["backend"] = "gemini"
    kanoa_config["model"] = "gemini-3.1-flash-lite-preview"
else:
    kanoa_config["backend"] = "openai"
    kanoa_config["model"] = "gemma4:26b"
    kanoa_config["api_base"] = "http://192.168.64.53:11434/v1"
    kanoa_config["api_key"] = "ollama"

# Initialize Pipeline Steps in State
if "steps" not in st.session_state:
    st.session_state.steps = [
        {
            "id": str(uuid.uuid4()),
            "type": "Data Extraction",
            "hotspots": "L619821, L3562597",
            "days_back": 7
        },
        {
            "id": str(uuid.uuid4()),
            "type": "Code Execution",
            "nl_prompt": "Plot the top 5 most common species by total_count.",
            "code": "import matplotlib.pyplot as plt\n\ntop_5 = df.head(5)\nfig, ax = plt.subplots()\nax.bar(top_5['comName'], top_5['total_count'])\nplt.xticks(rotation=45)\nplt.title('Top 5 Species')\nplt.tight_layout()"
        },
        {
            "id": str(uuid.uuid4()),
            "type": "kanoa Synthesis",
            "theme": "trend_analysis",
            "preamble": "You are the resident naturalist for the Edith Read Wildlife Sanctuary. Your task is to produce the weekly Field Notes journal.",
            "focus": "Analyze the provided chart and data. What are the key takeaways?"
        }
    ]

def move_step(index, direction):
    if direction == "up" and index > 0:
        st.session_state.steps[index - 1], st.session_state.steps[index] = st.session_state.steps[index], st.session_state.steps[index - 1]
    elif direction == "down" and index < len(st.session_state.steps) - 1:
        st.session_state.steps[index + 1], st.session_state.steps[index] = st.session_state.steps[index], st.session_state.steps[index + 1]

def delete_step(index):
    st.session_state.steps.pop(index)

# Load Prompts for Synthesis
with open(os.path.join(os.path.dirname(__file__), "prompts.json"), "r") as f:
    prompts = json.load(f)
theme_options = list(prompts.keys())

# Render Pipeline Builder UI
st.header("Pipeline Designer")

for i, step in enumerate(st.session_state.steps):
    with st.expander(f"Step {i+1}: {step['type']}", expanded=True):
        col1, col2 = st.columns([0.9, 0.1])
        
        with col1:
            if step["type"] == "Data Extraction":
                step["hotspots"] = st.text_input("Hotspot IDs (comma separated)", step["hotspots"], key=f"hotspots_{step['id']}")
                step["days_back"] = st.slider("Days Back", 1, 30, step["days_back"], key=f"days_{step['id']}")
                
            elif step["type"] == "Code Execution":
                step["nl_prompt"] = st.text_area("AI Translation: Describe your analysis to generate Python", step["nl_prompt"], key=f"nl_{step['id']}")
                if st.button("✨ Generate Code from Prompt", key=f"gen_{step['id']}"):
                    with st.spinner("Translating..."):
                        codegen_interp = AnalyticsInterpreter(**kanoa_config)
                        codegen_interp.set_prompts(
                            system_prompt="You are a Python data scientist. Your input data is a pandas dataframe `df` with columns: speciesCode, comName, last_seen, total_count, checklist_count. Write python code using pandas and matplotlib to fulfill the user request. Create a figure and save it to the variable `fig`. Return ONLY the raw python code inside ```python blocks.",
                            user_prompt="{focus_block}"
                        )
                        try:
                            code_result = codegen_interp.interpret(data=None, focus=step["nl_prompt"], stream=False, display_result=False)
                            code_text = code_result.text
                            if "```python" in code_text:
                                code_text = code_text.split("```python")[1].split("```")[0].strip()
                            elif "```" in code_text:
                                code_text = code_text.split("```")[1].strip()
                            step["code"] = code_text
                            st.rerun()
                        except Exception as e:
                            st.error(f"Code Generation Failed: {e}")
                
                step["code"] = st.text_area("Python Sandbox", step["code"], height=150, key=f"code_{step['id']}")
                
            elif step["type"] == "kanoa Synthesis":
                try:
                    theme_idx = theme_options.index(step["theme"])
                except ValueError:
                    theme_idx = 0
                step["theme"] = st.selectbox("Interpretation Theme (Base Prompt)", theme_options, index=theme_idx, key=f"theme_{step['id']}")
                step["preamble"] = st.text_area("System Preamble (Persona & Context)", step.get("preamble", "You are the resident naturalist for the Edith Read Wildlife Sanctuary. Your task is to produce the weekly Field Notes journal."), key=f"preamble_{step['id']}")
                step["focus"] = st.text_area("Multimodal Focus Instructions", step["focus"], key=f"focus_{step['id']}")

        with col2:
            st.button("⬆", key=f"up_{step['id']}", on_click=move_step, args=(i, "up"), disabled=(i == 0))
            st.button("⬇", key=f"down_{step['id']}", on_click=move_step, args=(i, "down"), disabled=(i == len(st.session_state.steps)-1))
            st.button("❌", key=f"del_{step['id']}", on_click=delete_step, args=(i,))

# Add Step Widget
st.markdown("---")
new_step_type = st.selectbox("Add a new step to the pipeline", ["Data Extraction", "Code Execution", "kanoa Synthesis"])
if st.button("➕ Append Step"):
    new_step = {"id": str(uuid.uuid4()), "type": new_step_type}
    if new_step_type == "Data Extraction":
        new_step["hotspots"] = "L619821"
        new_step["days_back"] = 7
    elif new_step_type == "Code Execution":
        new_step["nl_prompt"] = ""
        new_step["code"] = ""
    elif new_step_type == "kanoa Synthesis":
        new_step["theme"] = theme_options[0]
        new_step["preamble"] = "You are the resident naturalist for the Edith Read Wildlife Sanctuary. Your task is to produce the weekly Field Notes journal."
        new_step["focus"] = ""
    st.session_state.steps.append(new_step)
    st.rerun()

st.markdown("---")

# Execution Engine
if st.button("▶ Run Full Pipeline", type="primary"):
    sandbox_env = {"pd": pd, "plt": plt, "fig": None, "df": None}
    
    for i, step in enumerate(st.session_state.steps):
        with st.status(f"Executing Step {i+1}: {step['type']}..."):
            if step["type"] == "Data Extraction":
                hotspots_list = [h.strip() for h in step["hotspots"].split(",") if h.strip()]
                df = fetch_bq_data(hotspots_list, step["days_back"])
                sandbox_env["df"] = df
                st.write(f"Fetched {len(df)} rows.")
                st.dataframe(df)
                
            elif step["type"] == "Code Execution":
                if sandbox_env.get("df") is None:
                    st.warning("No DataFrame 'df' found in sandbox. Ensure a Data Extraction step ran first.")
                try:
                    exec(step["code"], sandbox_env)
                    st.write("Executed Python successfully.")
                    fig = sandbox_env.get("fig")
                    if fig:
                        # Save the figure locally
                        fig_path = "latest_generated_plot.png"
                        fig.savefig(fig_path, bbox_inches="tight")
                        st.success(f"Plot saved locally to {fig_path}")
                        
                        # Display in Streamlit feed
                        st.pyplot(fig)
                        
                        # Provide a download button
                        with open(fig_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Download Plot Image",
                                data=f,
                                file_name="field_journal_plot.png",
                                mime="image/png"
                            )
                except Exception as e:
                    st.error(f"Sandbox Error: {e}")
                    st.stop()
                    
            elif step["type"] == "kanoa Synthesis":
                theme_prompts = prompts.get(step["theme"])
                interp = AnalyticsInterpreter(**kanoa_config)
                
                # Combine the custom preamble with the base theme system prompt
                combined_system_prompt = f"{step.get('preamble', '')}\n\n{theme_prompts['system_prompt']}"
                
                interp.set_prompts(
                    system_prompt=combined_system_prompt,
                    user_prompt=theme_prompts["user_prompt_template"]
                )
                
                # Use current state of df and fig
                current_df = sandbox_env.get("df")
                data_dict = {"current_window": current_df.to_dict(orient="records")} if current_df is not None else None
                current_fig = sandbox_env.get("fig")
                
                try:
                    result = interp.interpret(
                        data=data_dict,
                        fig=current_fig,
                        context=f"Pipeline execution step {i+1}",
                        focus=step["focus"] if step["focus"] else None,
                        stream=False,
                        display_result=False
                    )
                    st.subheader("Synthesis Output")
                    st.markdown(result.text)
                except Exception as e:
                    st.error(f"kanoa Error: {e}")
                    st.stop()
