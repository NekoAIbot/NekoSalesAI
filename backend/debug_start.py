#!/usr/bin/env python3
"""Start the NekoSalesAI server with verbose error output."""
import sys
import os
sys.path.insert(0, '/root/NekoSalesAI/backend')
os.environ['PYTHONPATH'] = '.venv/lib/python3.13/site-packages'

import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    stream=sys.stdout,
)

try:
    from app.main import app
    print("App imported successfully", file=sys.stderr, flush=True)
except Exception as e:
    print(f"FAILED to import app: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
