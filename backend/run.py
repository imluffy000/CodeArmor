import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import uvicorn

if __name__ == "__main__":
    print("Starting AI PR Reviewer...")
    print("  Home:    http://127.0.0.1:8000/")
    print("  Health:  http://127.0.0.1:8000/health")
    print("  Review:  POST http://127.0.0.1:8000/review")
    print()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
