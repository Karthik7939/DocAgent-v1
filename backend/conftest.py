"""
conftest.py
-----------
Adds the backend root directory to sys.path so all modules
(agents, prompts, rag, utils) are importable during pytest runs.
"""

import sys
from pathlib import Path

# Insert the backend root (the directory containing this file) at the front of sys.path
sys.path.insert(0, str(Path(__file__).parent))
