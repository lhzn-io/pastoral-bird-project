import os
from kanoa import AnalyticsInterpreter

kanoa_config = {
    "backend": "openai",
    "model": "gemma4:26b",
    "api_base": "http://192.168.64.53:11434/v1",
    "api_key": "ollama"
}

interp = AnalyticsInterpreter(**kanoa_config)
interp.set_prompts(system_prompt="You are an AI.", user_prompt="{focus_block}")

try:
    print("Sending request to Ollama...")
    # Passing only text, no image, to see if the network connection works
    res = interp.interpret(data=None, fig=None, focus="Hello", stream=False, display_result=False)
    print("Response:", res.text)
except Exception as e:
    print("Error:", e)
