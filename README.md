# Pastoral Collective Field Journal

An AI-driven automated ingestion-to-synthesis pipeline for generating dynamic, multimodal "Field Notes" using eBird sighting data and the `kanoa` engine.

## Admin Pipeline Builder

The core R&D interface is the Streamlit-based **Field Journal Pipeline Builder**. It allows non-technical administrators to design multi-step data transformations and synthesis tasks using LLM-driven text-to-code generation, local Python execution sandboxing, and multimodal synthesis.

### Running the Admin UI
Ensure your virtual environment is active, then run:
```bash
uv run streamlit run admin_app.py
```

**Local URL:** [http://localhost:8501](http://localhost:8501)

### Features
* **AI Provider Routing:** Toggle between Google AI Studio (`gemini-3.1-flash-lite-preview`) and a local Mac Studio Ollama instance (`gemma4:26b`).
* **Text-to-Code Translation:** Admins can type English prompts, which the LLM translates into Python Pandas/Matplotlib scripts.
* **Execution Sandbox:** The generated code is safely executed locally against the downloaded BigQuery dataframe.
* **Multimodal Synthesis:** The resulting plot and data are fed into `kanoa` to generate structured Markdown field notes (e.g., trend analyses, weekly roundups).

## Backend Ingestion
The eBird data ingestion pipeline runs automatically via `test_ingestion.py`. It pulls the last 30 days of data and inserts it into a bitemporal BigQuery ledger using atomic MERGE operations to prevent duplication.
