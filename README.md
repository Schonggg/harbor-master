# Monash Hackathon

Project lives in [`harbormaster/`](harbormaster/).

```powershell
cd harbormaster
copy .env.example .env
py -3 -m pip install -e ".[dev]"
py -3 scripts/demo_reset.py
py -3 -m uvicorn harbormaster.api.main:app --reload --port 8000
```
