#!/usr/bin/env python3
import json
from pathlib import Path

def load_model_year_data(repo_dir, make, model):
    """Load model year PID support data if it exists."""
    model_years_path = repo_dir / 'service01' / 'modelyears.json'
    if not model_years_path.exists():
        return None

    try:
        with open(model_years_path) as f:
            data = json.load(f)

        # Add make and model information to the data
        return {
            'make': make,
            'model': model,
            'modelYears': data
        }
    except Exception as e:
        print(f"Error loading model year data for {make}-{model}: {e}")
        return None

class CompactJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to format arrays on single lines."""
    def encode(self, obj):
        if isinstance(obj, list) and all(isinstance(x, str) for x in obj):
            # For arrays of strings (PID arrays), keep them on one line
            parts = [self.encode(item) for item in obj]
            return "[" + ", ".join(parts) + "]"
        return super().encode(obj)

def save_model_year_data(model_year_data, output_path):
    """Save model year data with custom formatting."""
    if not model_year_data:
        print("No model year data found.")
        return False

    with open(output_path, 'w') as f:
        json_str = json.dumps(model_year_data, cls=CompactJSONEncoder, indent=2, sort_keys=True)
        # Further compact ECU command arrays by regex replacing multi-line arrays
        import re
        json_str = re.sub(r'\[\n\s+("[0-9A-F]{2}",?\s*)+\n\s+\]',
                         lambda m: m.group(0).replace('\n', ' ').replace('  ', ''),
                         json_str)
        f.write(json_str)

    print(f"Saved model year data to {output_path} ({len(model_year_data)} vehicles)")
    return True