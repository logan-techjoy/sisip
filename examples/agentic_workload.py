"""Run from the repository root after `python -m pip install -e .`."""
from sisip.demo import run_demo

result, history = run_demo()
labels = {0: "task", 1: "update", 2: "result", 3: "handoff"}
for message in history:
    print(f"During execution: validated {labels[message[5]]}; {len(message[9])} graph nodes")
print("Final-output gate opened after the worker result passed validation.")
print("Observation: temperature difference +5 degrees Celsius; confidence 0.82.")
print("Period unspecified. This demo validates supplied data, not live weather.")
