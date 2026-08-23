# start.ps1
# ---------
# Use this script instead of running uvicorn directly.
#
# WHY THIS EXISTS:
# Uvicorn's --reload flag watches the ENTIRE project directory by default.
# When a push webhook fires, the repository is cloned/synced into repositories/.
# Uvicorn then detects the new .py files inside repositories/ and restarts itself,
# killing the documentation pipeline mid-execution.
#
# This script restricts the watch to ONLY source code directories,
# so repositories/, generated_docs/, logs/, and rag/storage/ never
# trigger an unwanted reload.
#
# USAGE:
#   .\.venv\Scripts\activate
#   .\start.ps1

.venv\Scripts\uvicorn app.main:app --reload `
  --reload-dir app `
  --reload-dir agents `
  --reload-dir services `
  --reload-dir rag `
  --reload-dir workflow `
  --reload-dir utils `
  --reload-dir prompts `
  --host 0.0.0.0 `
  --port 8000
