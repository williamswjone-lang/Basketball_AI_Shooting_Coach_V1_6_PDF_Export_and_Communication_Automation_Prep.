# Render Deploy Runbook (Basketball AI V1.6)

Use this when deploy is stuck, returns 503, or builds the wrong stack.

## Current Source of Truth
- Repo root blueprint: `render.yaml`
- App root dir: `Basketball_AI_Shooting_Coach_V1_6_PDF_Export_and_Communication_Automation_Prep`
- App start command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --server.fileWatcherType none`

## 1) Quick Recovery (Existing Service)
1. Open Render service settings.
2. Verify Runtime is Python.
3. Verify Root Directory is `Basketball_AI_Shooting_Coach_V1_6_PDF_Export_and_Communication_Automation_Prep`.
4. Verify Build Command:
   `pip install --upgrade pip && pip install -r requirements.txt`
5. Verify Start Command:
   `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --server.fileWatcherType none`
6. Save settings.
7. Manual Deploy -> Deploy latest commit.

## 2) Clean Recovery (Recommended if stack mismatch persists)
1. Create a new Render Web Service from the same GitHub repo.
2. Choose Blueprint deploy (reads root `render.yaml`).
3. Confirm service name and deploy.

## 3) What to Check in Logs
- Good signs:
  - Python dependency installation starts.
  - Streamlit launch line appears.
- Bad signs:
  - `cargo build --release` appears.
  - `could not find Cargo.toml` appears.
  - Build checks out an old commit unexpectedly.

## 4) 503 Troubleshooting
1. Wait 30-120 seconds for cold start.
2. If still 503 after 3-5 minutes:
   - Check latest deploy status.
   - Check events for failed health checks.
   - Re-run Manual Deploy.
3. If still failing, create a fresh service using blueprint.

## 5) Team Testing Readiness Check
- Public URL opens app UI.
- Sidebar and player flow load.
- Upload flow reachable.
- PDF generation route reachable.

If all pass, send the team email draft from:
`Basketball_AI_Shooting_Coach_V1_6_PDF_Export_and_Communication_Automation_Prep/TEAM_TEST_EMAIL_DRAFT.txt`
