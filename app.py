from pathlib import Path
import os
import runpy

APP_DIR = Path(__file__).resolve().parent / "Basketball_AI_Shooting_Coach_V1_6_PDF_Export_and_Communication_Automation_Prep"
os.chdir(APP_DIR)
runpy.run_path("app.py", run_name="__main__")
