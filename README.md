# Building Inspection Assistant

AI-powered building facade inspection system with:
- image-based inspection
- report generation with Ollama LLM
- history management
- statistics dashboard
- Q&A based on latest report

## Project Structure

```text
agent/
├── agent/
│   ├── graph.py
│   ├── nodes.py
│   └── state.py
├── predictors/
│   ├── base.py
│   ├── floor.py
│   ├── floor_recognition.py
│   ├── added_floor.py
│   ├── material.py
│   └── hidden_danger.py
├── db/
│   ├── models.py
│   ├── database.py
│   └── crud.py
├── api/
│   └── main.py
├── app.py
├── main.py
└── requirements.txt
```

## Requirements

- Python 3.10+
- Optional MySQL (default DB is local SQLite)
- Optional CUDA
- Ollama with model `qwen2:1.5b`

## Install

```bash
pip install -r requirements.txt
ollama pull qwen2:1.5b
```

## Configuration

Environment variables:

- `INSPECTION_DB_URL` (default: `sqlite:///./inspection.db`)
- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `OLLAMA_MODEL` (default: `qwen2:1.5b`)
- `INIT_ADMIN_USERNAME` (default: `admin`)
- `INIT_ADMIN_PASSWORD` (required only for first-time admin bootstrap)

Examples:

```bash
# PowerShell
$env:INSPECTION_DB_URL="mysql+pymysql://user:pass@localhost:3306/building_inspection"
$env:INIT_ADMIN_PASSWORD="StrongPassword123!"

# Linux / macOS
export INSPECTION_DB_URL="mysql+pymysql://user:pass@localhost:3306/building_inspection"
export INIT_ADMIN_PASSWORD="StrongPassword123!"
```

## Run

Gradio UI:

```bash
python app.py
```

CLI:

```bash
python main.py
```

FastAPI:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

- `POST /predict`
- `GET /history`
- `GET /history/{record_id}`
- `GET /statistics`

Authentication uses HTTP Basic.

## Notes

- If no users exist and `INIT_ADMIN_PASSWORD` is set, the app creates the initial admin account.
- If `INIT_ADMIN_PASSWORD` is not set, no default admin account is created.
