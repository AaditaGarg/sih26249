# SustainIQ frontend
React + Vite dashboard for the SustainIQ backend (synthetic data).
```bash
# terminal 1: backend
cd ../backend && uvicorn app.main:app --reload
# terminal 2: frontend
cd frontend && npm install && npm run dev      # http://localhost:5173
```
Backend URL defaults to `http://localhost:8000/api/v1`; override with `VITE_API_URL`.
