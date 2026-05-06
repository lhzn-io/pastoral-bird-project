import time
import pandas as pd
import matplotlib.pyplot as plt
from kanoa import AnalyticsInterpreter

kanoa_config = {
    "backend": "openai",
    "model": "gemma4:26b",
    "api_base": "http://192.168.64.53:11434/v1",
    "api_key": "ollama"
}

interp = AnalyticsInterpreter(**kanoa_config)
interp.set_prompts(system_prompt="You are a data analyst.", user_prompt="{focus_block}")

# Dummy data
df = pd.DataFrame({"Species": ["Robin", "Jay"], "Count": [10, 5]})
data_dict = {"current_window": df.to_dict(orient="records")}

# Generate plot
fig, ax = plt.subplots()
ax.bar(df["Species"], df["Count"])
plt.tight_layout()

print("Test 1: Tabular Data Only (No Vision)")
start = time.time()
try:
    res1 = interp.interpret(data=data_dict, fig=None, focus="What are the top species?", stream=False, display_result=False)
    print(f"Success! Latency: {time.time() - start:.2f} seconds")
    print(f"Response: {res1.text[:50]}...")
except Exception as e:
    print(f"Failed: {e}")

print("\nTest 2: Tabular Data + Matplotlib Figure (Multimodal)")
start = time.time()
try:
    res2 = interp.interpret(data=data_dict, fig=fig, focus="What are the top species based on the chart?", stream=False, display_result=False)
    print(f"Success! Latency: {time.time() - start:.2f} seconds")
    print(f"Response: {res2.text[:50]}...")
except Exception as e:
    print(f"Failed: {e}")
