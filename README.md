# genAI_experiments

CSV comparison dashboard for Data Testers built with **Streamlit + pandas**.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run csv_compare_dashboard.py
```

## Deploy from GitHub (recommended)

### Option A: Streamlit Community Cloud (fastest)
1. Push this repo to GitHub.
2. Go to https://share.streamlit.io/ and sign in.
3. Click **Create app** and pick:
   - Repository: `your-org/your-repo`
   - Branch: `main`
   - Main file path: `csv_compare_dashboard.py`
4. Deploy.

### Option B: Render using GitHub + GitHub Actions
This repo includes:
- `Dockerfile` for container deployment.
- `.github/workflows/deploy.yml` that:
  - runs syntax checks on push to `main`
  - triggers Render deploy when secret is configured

#### Steps
1. Create a **Web Service** on Render connected to this GitHub repo.
2. In Render service settings, copy the **Deploy Hook URL**.
3. In GitHub repo settings, add secret:
   - `RENDER_DEPLOY_HOOK_URL` = your Render deploy hook URL
4. Push to `main` (or run workflow manually). GitHub Actions will trigger deploy.

## CI/CD workflow included
- File: `.github/workflows/deploy.yml`
- Trigger: `push` to `main`, `workflow_dispatch`
- Checks: `python -m py_compile csv_compare_dashboard.py`
- Deploy: Render deploy hook (if configured)
