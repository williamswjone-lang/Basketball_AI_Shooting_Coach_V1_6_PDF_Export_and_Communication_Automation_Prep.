# Basketball AI Shooting Coach V1.6

V1.6 is the PDF export and communication automation layer built on top of the V1.5.1 stabilized business workflow.

## What V1.6 Adds
- PDF report-card export
- PDF invoice export
- PDF weekly briefing export
- PDF practice script export
- Email-ready parent messages
- SMS-ready parent messages
- Communication follow-up queue
- Backup and export ZIP bundle
- Generated PDF registry

## What Stays from V1.5.1
- Skill Coach mode and Team mode
- Manual evaluation and score tracking
- Training package tracking
- Payment and invoice tracking
- Attendance and calendar workflows
- Parent communication workflows
- Business dashboard and report exports

## Run Locally
1. Create environment: python -m venv .venv
2. Activate environment: .venv\Scripts\activate
3. Install dependencies: pip install -r requirements.txt
4. Start app: streamlit run app.py
5. Open: http://localhost:8501

## Team Can Test Quickly
- Simple guide: TEAM_TEST_QUICKSTART.md
- One-page checklist: TEAM_TEST_ONE_PAGE_CHECKLIST.md
- Copy/paste team message: TEAM_TEST_MESSAGE_TEMPLATE.txt
- Same-network launcher: run_team_preview_windows.bat
- Cloud share setup: render.yaml

## V1.6.1 AI Restoration
The AI pose evaluation is restored in V1.6.1. In this workspace, Python 3.14 with current mediapipe may not expose the classic Pose API required by the seven-step evaluator.

Use this environment for reliable AI:
- Python 3.10, 3.11, or 3.12
- mediapipe 0.10.x
- opencv-python 4.8+
- numpy 1.24+

Quick restore steps:
1. Install Python 3.11 (recommended).
2. Recreate venv using Python 3.11.
3. Activate venv and run pip install -r requirements.txt.
4. Start app and open AI Shooting Evaluation tab.
5. Upload a clear 45-degree shooting video and run evaluation.
6. Save AI session and confirm Report Card shows Manual vs AI comparison.

## First Validation Pass
1. Click Load Demo Data.
2. Generate Report Card PDF.
3. Generate Invoice PDF.
4. Generate Weekly Briefing PDF.
5. Generate Parent Email and SMS message.
6. Save communication follow-up.
7. Create backup ZIP.
8. Export Generated PDFs, Communication Followups, and System Backups.

## Team Feedback System (V2.9)
Use the structured feedback toolkit in `team_feedback` to run a high-quality team validation cycle.

- Master playbook: `team_feedback/TEAM_FEEDBACK_PLAYBOOK_V29.md`
- Rollout schedule: `team_feedback/TEAM_FEEDBACK_ROLLOUT_PLAN.md`
- Scenario script: `team_feedback/scenarios/V29_UAT_SCENARIOS.md`
- Templates:
	- `team_feedback/templates/bug_report_template.md`
	- `team_feedback/templates/ux_feedback_template.md`
	- `team_feedback/templates/session_summary_template.md`
- Trackers:
	- `team_feedback/tracker/feedback_log.csv`
	- `team_feedback/tracker/daily_summary.csv`

Recommended order:
1. Start with Wave 1 using the scenario script.
2. File all bugs and UX notes with templates.
3. Run daily triage using severity and SLA rules from the playbook.
4. Promote to next wave only when exit criteria are met.
