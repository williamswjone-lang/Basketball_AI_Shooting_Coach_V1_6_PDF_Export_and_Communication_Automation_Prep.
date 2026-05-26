import streamlit as st
import pandas as pd
import sqlite3
import json
import csv
from pathlib import Path
from datetime import date, datetime, timedelta
import zipfile
import os
import tempfile
import math
import urllib.request

try:
    import cv2
    import mediapipe as mp
    import numpy as np
    CV_AVAILABLE = True
except Exception:
    CV_AVAILABLE = False

MP_POSE_AVAILABLE = bool(
    CV_AVAILABLE
    and hasattr(mp, "solutions")
    and hasattr(mp.solutions, "pose")
    and hasattr(mp.solutions.pose, "Pose")
)

MP_TASKS_POSE_AVAILABLE = False
if CV_AVAILABLE and hasattr(mp, "tasks"):
    try:
        from mediapipe.tasks import python as mp_tasks_python
        from mediapipe.tasks.python import vision as mp_tasks_vision
        MP_TASKS_POSE_AVAILABLE = True
    except Exception:
        MP_TASKS_POSE_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

try:
    import qrcode
    QR_AVAILABLE = True
except Exception:
    QR_AVAILABLE = False

st.set_page_config(page_title="Basketball AI Shooting Coach V2.9", page_icon="🏀", layout="wide")
DATA_DIR = Path("data")
REPORT_DIR = DATA_DIR / "generated_pdfs"
BACKUP_DIR = DATA_DIR / "backups"
MODEL_DIR = DATA_DIR / "models"
V27_DRILL_DIR = DATA_DIR / "drills"
V27_DRILL_LIBRARY_CSV = V27_DRILL_DIR / "drill_library.csv"
V27_PRACTICE_PLAN_DIR = DATA_DIR / "practice_plans"
V27_PRACTICE_HISTORY_DIR = DATA_DIR / "practice_history"
V27_PRACTICE_HISTORY_CSV = V27_PRACTICE_HISTORY_DIR / "practice_completion_history.csv"
V27_OUTPUT_DIR = Path("outputs")
V27_PRACTICE_PDF_DIR = V27_OUTPUT_DIR / "practice_plans"
V28_DRILL_VIDEO_DIR = DATA_DIR / "drill_videos"
V28_COACH_DEMO_DIR = DATA_DIR / "coach_demos"
V28_HOMEWORK_ASSIGNMENTS_DIR = DATA_DIR / "homework_assignments"
V28_HOMEWORK_HISTORY_CSV = V28_HOMEWORK_ASSIGNMENTS_DIR / "homework_history.csv"
# Compatibility alias for existing helpers/usages.
V28_HOMEWORK_ASSIGNMENTS_CSV = V28_HOMEWORK_HISTORY_CSV
V28_INSTRUCTION_CARD_DIR = V27_OUTPUT_DIR / "instruction_cards"
V28_QR_CODE_DIR = V27_OUTPUT_DIR / "qr_codes"
V28_HOMEWORK_REPORT_DIR = V27_OUTPUT_DIR / "homework_reports"
V29_HOMEWORK_SUBMISSIONS_DIR = DATA_DIR / "homework_submissions"
V29_HOMEWORK_SUBMISSION_VIDEO_DIR = V29_HOMEWORK_SUBMISSIONS_DIR / "videos"
V29_HOMEWORK_SUBMISSIONS_CSV = V29_HOMEWORK_SUBMISSIONS_DIR / "homework_submissions.csv"
V29_PARENT_PROGRESS_DIR = V27_OUTPUT_DIR / "parent_progress"
DATA_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)
MODEL_DIR.mkdir(exist_ok=True)
V27_DRILL_DIR.mkdir(exist_ok=True)
V27_PRACTICE_PLAN_DIR.mkdir(exist_ok=True)
V27_PRACTICE_HISTORY_DIR.mkdir(exist_ok=True)
V27_OUTPUT_DIR.mkdir(exist_ok=True)
V27_PRACTICE_PDF_DIR.mkdir(parents=True, exist_ok=True)
V28_DRILL_VIDEO_DIR.mkdir(exist_ok=True)
V28_COACH_DEMO_DIR.mkdir(exist_ok=True)
V28_HOMEWORK_ASSIGNMENTS_DIR.mkdir(exist_ok=True)
V28_INSTRUCTION_CARD_DIR.mkdir(parents=True, exist_ok=True)
V28_QR_CODE_DIR.mkdir(parents=True, exist_ok=True)
V28_HOMEWORK_REPORT_DIR.mkdir(parents=True, exist_ok=True)
V29_HOMEWORK_SUBMISSIONS_DIR.mkdir(exist_ok=True)
V29_HOMEWORK_SUBMISSION_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
V29_PARENT_PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "basketball_ai_shooting_coach_v1_6.db"

SHOOTING_STEPS = ["Feet & Stance", "Balance & Load", "Shot Pocket / Ball Prep", "Elbow & Arm Alignment", "Set Point & Eyes", "Release & Extension", "Follow-Through & Landing"]
DRILL_MAP = {"Feet & Stance":"Base Balance Form Shooting", "Balance & Load":"Chair Load to Shot", "Shot Pocket / Ball Prep":"Pocket Repeat Catch-and-Rise", "Elbow & Arm Alignment":"One-Hand Alignment Form Shooting", "Set Point & Eyes":"Eyes-Early Set Point Drill", "Release & Extension":"High-Finish Extension Drill", "Follow-Through & Landing":"Hold-the-Finish Landing Drill"}
STEP_TIPS = {s: "Score this fundamental based on current shooting form and consistency." for s in SHOOTING_STEPS}

def conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def execute(sql, params=()):
    c = conn(); cur = c.cursor(); cur.execute(sql, params); c.commit(); rid = cur.lastrowid; c.close(); return rid

def q(sql, params=()):
    c = conn()
    try:
        df = pd.read_sql_query(sql, c, params=params)
    except Exception:
        df = pd.DataFrame()
    c.close(); return df

def now():
    return datetime.now().isoformat(timespec="seconds")

def full_name(row):
    first = row.get("first_name", "") or ""; last = row.get("last_name", "") or ""; nick = row.get("nickname", "") or ""
    name = f"{first} {last}".strip()
    return f"{name} ({nick})" if nick else name

def safe_filename(text):
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in str(text)).strip("_") or "file"

def _migrate_columns(additions):
    c = conn(); cur = c.cursor()
    for table, column in additions:
        existing = [row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    c.commit(); c.close()

def init_db():
    schema = [
        """CREATE TABLE IF NOT EXISTS teams(team_id INTEGER PRIMARY KEY AUTOINCREMENT, team_name TEXT NOT NULL, age_group TEXT, coach_name TEXT, season TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS players(player_id INTEGER PRIMARY KEY AUTOINCREMENT, team_id INTEGER, first_name TEXT NOT NULL, last_name TEXT, nickname TEXT, age_group TEXT, position TEXT, shooting_hand TEXT, height TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS skill_players(skill_player_id INTEGER PRIMARY KEY AUTOINCREMENT, first_name TEXT NOT NULL, last_name TEXT, nickname TEXT, parent_guardian TEXT, contact_email TEXT, contact_phone TEXT, school TEXT, graduation_year TEXT, age_group TEXT, position TEXT, shooting_hand TEXT, height TEXT, skill_level TEXT, training_goal TEXT, package_type TEXT, status TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS sessions(session_id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER, skill_player_id INTEGER, team_id INTEGER, session_date TEXT, session_type TEXT, session_context TEXT, coach_name TEXT, location TEXT, analysis_mode TEXT, overall_score REAL, make_miss TEXT, shot_context TEXT, homework_assigned TEXT, next_session_focus TEXT, coach_notes TEXT, package_counted TEXT, package_update_status TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS evaluations(evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, fundamental TEXT, score REAL, rating TEXT, recommendation TEXT)""",
        """CREATE TABLE IF NOT EXISTS drills(drill_id INTEGER PRIMARY KEY AUTOINCREMENT, drill_name TEXT, target_fundamental TEXT, description TEXT, reps TEXT, coaching_cues TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS practice_plans(plan_id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER, skill_player_id INTEGER, team_id INTEGER, plan_date TEXT, focus_area TEXT, duration_minutes INTEGER, plan_body TEXT, homework TEXT, next_focus TEXT, status TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS practice_plan_drills(plan_drill_id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, drill_name TEXT, target_fundamental TEXT, duration_minutes INTEGER, reps TEXT, drill_order INTEGER, completed INTEGER DEFAULT 0, completion_notes TEXT, completed_at TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS generated_reports(report_id INTEGER PRIMARY KEY AUTOINCREMENT, report_type TEXT, report_scope TEXT, player_id INTEGER, skill_player_id INTEGER, team_id INTEGER, report_title TEXT, report_body TEXT, pdf_path TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS training_packages(package_id INTEGER PRIMARY KEY AUTOINCREMENT, skill_player_id INTEGER, package_name TEXT, package_type TEXT, sessions_purchased INTEGER, sessions_used INTEGER, sessions_remaining INTEGER, price REAL, start_date TEXT, expiration_date TEXT, status TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS attendance(attendance_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, player_id INTEGER, skill_player_id INTEGER, team_id INTEGER, attendance_date TEXT, attendance_status TEXT, reason TEXT, makeup_required TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS payments(payment_id INTEGER PRIMARY KEY AUTOINCREMENT, skill_player_id INTEGER, team_id INTEGER, package_id INTEGER, invoice_number TEXT, payment_date TEXT, amount_due REAL, amount_paid REAL, balance REAL, payment_method TEXT, payment_status TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS parent_messages(message_id INTEGER PRIMARY KEY AUTOINCREMENT, skill_player_id INTEGER, player_id INTEGER, team_id INTEGER, message_type TEXT, recipient_name TEXT, recipient_contact TEXT, subject TEXT, message_body TEXT, sms_body TEXT, status TEXT, follow_up_date TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS practice_scripts(script_id INTEGER PRIMARY KEY AUTOINCREMENT, team_id INTEGER, skill_player_id INTEGER, script_date TEXT, script_type TEXT, focus_area TEXT, duration_minutes INTEGER, intensity_level TEXT, script_body TEXT, pdf_path TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS coach_calendar(calendar_id INTEGER PRIMARY KEY AUTOINCREMENT, skill_player_id INTEGER, team_id INTEGER, event_date TEXT, event_time TEXT, event_type TEXT, event_title TEXT, location TEXT, status TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS communication_followups(followup_id INTEGER PRIMARY KEY AUTOINCREMENT, skill_player_id INTEGER, player_id INTEGER, team_id INTEGER, followup_date TEXT, followup_type TEXT, recipient_name TEXT, recipient_contact TEXT, subject TEXT, message_body TEXT, status TEXT, notes TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS generated_pdfs(pdf_id INTEGER PRIMARY KEY AUTOINCREMENT, pdf_type TEXT, subject_name TEXT, source_table TEXT, source_id INTEGER, file_path TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS at_home_assignments(assignment_id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, plan_drill_id INTEGER, skill_player_id INTEGER, assigned_date TEXT, due_date TEXT, reps_goal INTEGER, makes_goal INTEGER, status TEXT, notes TEXT, completed_at TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS homework_submissions(submission_id INTEGER PRIMARY KEY AUTOINCREMENT, assignment_id INTEGER, skill_player_id INTEGER, submission_date TEXT, submission_video_path TEXT, reps_completed INTEGER, makes_completed INTEGER, minutes_practiced INTEGER, confidence_score INTEGER, difficulty_score INTEGER, self_rating INTEGER, player_notes TEXT, coach_status TEXT, coach_feedback TEXT, effort_score REAL, self_report_score REAL, completion_score REAL, score_label TEXT, created_at TEXT, reviewed_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS system_backups(backup_id INTEGER PRIMARY KEY AUTOINCREMENT, backup_name TEXT, backup_path TEXT, created_at TEXT)""",
    ]
    c = conn(); cur = c.cursor()
    for statement in schema:
        cur.execute(statement)
    c.commit(); c.close()
    _migrate_columns([
        ("generated_reports", "pdf_path"),
        ("parent_messages",   "sms_body"),
        ("parent_messages",   "follow_up_date"),
        ("practice_scripts",  "pdf_path"),
        ("practice_plans",    "plan_scope"),
        ("practice_plans",    "skill_level"),
        ("practice_plans",    "plan_json_path"),
        ("practice_plans",    "plan_pdf_path"),
        ("drills",            "skill_levels"),
        ("drills",            "demo_video_path"),
        ("drills",            "coach_demo_video_path"),
        ("drills",            "demo_video_url"),
        ("drills",            "instruction_card_path"),
        ("drills",            "qr_code_path"),
        ("drills",            "homework_template"),
        ("drills",            "at_home_plan_template"),
        ("drills",            "coach_demo_notes"),
        ("practice_plan_drills", "video_link"),
        ("practice_plan_drills", "homework_assignment"),
        ("practice_plan_drills", "at_home_plan"),
        ("at_home_assignments", "assignment_pdf_path"),
        ("at_home_assignments", "minutes_goal"),
        ("homework_submissions", "assignment_id"),
        ("homework_submissions", "skill_player_id"),
        ("homework_submissions", "submission_date"),
        ("homework_submissions", "submission_video_path"),
        ("homework_submissions", "reps_completed"),
        ("homework_submissions", "makes_completed"),
        ("homework_submissions", "minutes_practiced"),
        ("homework_submissions", "confidence_score"),
        ("homework_submissions", "difficulty_score"),
        ("homework_submissions", "self_rating"),
        ("homework_submissions", "player_notes"),
        ("homework_submissions", "coach_status"),
        ("homework_submissions", "coach_feedback"),
        ("homework_submissions", "effort_score"),
        ("homework_submissions", "self_report_score"),
        ("homework_submissions", "completion_score"),
        ("homework_submissions", "score_label"),
        ("homework_submissions", "created_at"),
        ("homework_submissions", "reviewed_at"),
    ])
    if q("SELECT COUNT(*) AS n FROM drills").iloc[0]["n"] == 0:
        for step, drill in DRILL_MAP.items():
            execute("INSERT INTO drills(drill_name,target_fundamental,description,reps,coaching_cues,created_at,skill_levels) VALUES(?,?,?,?,?,?,?)", (drill, step, f"Drill for {step}", "5 spots x 10 makes", "Focus on clean, repeatable mechanics.", now(), "Beginner,Intermediate,Advanced,Elite"))

    execute("UPDATE drills SET skill_levels=COALESCE(skill_levels, '') WHERE skill_levels IS NULL")
    sync_drill_library_csv()
    sync_v28_homework_assignments_csv()
    sync_v29_homework_submissions_csv()

def rating(score):
    return "🟢 Strong" if score >= 85 else "🟡 Developing" if score >= 70 else "🟠 Needs Work" if score >= 55 else "🔴 Critical Focus"

def simple_rating(score):
    return "Strong" if score >= 85 else "Developing" if score >= 70 else "Needs Work" if score >= 55 else "Critical Focus"

def overall(scores):
    return round(sum(scores.values()) / len(scores), 1) if scores else 0

def weakest(scores, n=3):
    return sorted(scores.items(), key=lambda x: x[1])[:n] if scores else []

def strongest(scores, n=2):
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:n] if scores else []

def recommendation(step, score):
    return "Maintain and build game-speed reps." if score >= 85 else "Continue targeted consistency work." if score >= 70 else "Needs focused drill work." if score >= 55 else "Rebuild with slow-form reps."

def _angle(a, b, c):
    ab = (a[0] - b[0], a[1] - b[1])
    cb = (c[0] - b[0], c[1] - b[1])
    denom = math.hypot(*ab) * math.hypot(*cb)
    if denom == 0:
        return 180.0
    value = max(-1.0, min(1.0, (ab[0] * cb[0] + ab[1] * cb[1]) / denom))
    return math.degrees(math.acos(value))

def _score_from_error(error_value, scale):
    return round(max(1.0, min(10.0, 10.0 - (error_value * scale))), 1)

def _v1_classification(overall_100):
    if overall_100 >= 90:
        return "Elite Form"
    if overall_100 >= 80:
        return "Strong Form"
    if overall_100 >= 70:
        return "Good Form"
    if overall_100 >= 60:
        return "Developing Shooter"
    return "Foundation Needed"

def _ensure_pose_landmarker_model():
    model_path = MODEL_DIR / "pose_landmarker_heavy.task"
    if model_path.exists():
        return model_path, None
    url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
    try:
        urllib.request.urlretrieve(url, str(model_path))
        return model_path, None
    except Exception as exc:
        return None, f"Unable to download pose model: {exc}"

def run_ai_seven_step_evaluation(video_path, dominant_hand="Right"):
    if not CV_AVAILABLE:
        return {"error": "AI stack not installed. Install opencv-python, mediapipe, and numpy."}
    if not MP_POSE_AVAILABLE and not MP_TASKS_POSE_AVAILABLE:
        return {
            "error": "Mediapipe Pose runtime is unavailable in this environment. Install mediapipe with either solutions.pose or tasks vision PoseLandmarker support."
        }

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "Unable to open uploaded video."}

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0
    sample_every = max(1, int(fps // 6))

    if dominant_hand == "Right":
        s_idx, e_idx, w_idx = 12, 14, 16
        g_idx = 15
        h_idx, k_idx, a_idx = 24, 26, 28
    else:
        s_idx, e_idx, w_idx = 11, 13, 15
        g_idx = 16
        h_idx, k_idx, a_idx = 23, 25, 27

    stance_errors = []
    knee_angles = []
    hand_sep_values = []
    shot_pocket_values = []
    nose_align_values = []
    elbow_errors = []
    release_hits = 0
    hip_centers = []
    processed_frames = 0
    frame_index = 0

    def process_landmarks(lm):
        nonlocal release_hits, processed_frames
        req = [0, 11, 12, 23, 24, 27, 28, s_idx, e_idx, w_idx, g_idx, h_idx, k_idx, a_idx]
        if any(i >= len(lm) for i in req):
            return

        shoulder = (lm[s_idx].x, lm[s_idx].y)
        elbow = (lm[e_idx].x, lm[e_idx].y)
        wrist = (lm[w_idx].x, lm[w_idx].y)
        guide_wrist = (lm[g_idx].x, lm[g_idx].y)
        hip = (lm[h_idx].x, lm[h_idx].y)
        knee = (lm[k_idx].x, lm[k_idx].y)
        ankle = (lm[a_idx].x, lm[a_idx].y)

        shoulder_mid_x = (lm[11].x + lm[12].x) / 2.0
        hip_center_x = (lm[23].x + lm[24].x) / 2.0
        ankle_center_x = (lm[27].x + lm[28].x) / 2.0
        stance_errors.append(abs(hip_center_x - ankle_center_x))
        hip_centers.append(hip_center_x)

        knee_angles.append(_angle(hip, knee, ankle))
        hand_sep_values.append(abs(wrist[0] - guide_wrist[0]))
        shot_pocket_values.append(abs(wrist[1] - hip[1]))
        nose_align_values.append(abs(lm[0].x - shoulder_mid_x))
        elbow_errors.append(abs(elbow[0] - wrist[0]) + abs(shoulder[0] - elbow[0]))

        if wrist[1] < elbow[1] and elbow[1] < shoulder[1]:
            release_hits += 1

        processed_frames += 1

    if MP_POSE_AVAILABLE:
        with mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as pose:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                frame_index += 1
                if frame_index % sample_every != 0:
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = pose.process(rgb)
                if not result.pose_landmarks:
                    continue

                process_landmarks(result.pose_landmarks.landmark)
    else:
        model_path, model_error = _ensure_pose_landmarker_model()
        if model_error:
            cap.release()
            return {"error": model_error}

        options = mp_tasks_vision.PoseLandmarkerOptions(
            base_options=mp_tasks_python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_tasks_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        with mp_tasks_vision.PoseLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                frame_index += 1
                if frame_index % sample_every != 0:
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int((frame_index / fps) * 1000)
                result = landmarker.detect_for_video(mp_image, timestamp_ms)
                if not result.pose_landmarks:
                    continue

                process_landmarks(result.pose_landmarks[0])

    cap.release()

    if processed_frames < 5:
        return {"error": "Not enough pose frames detected. Use a clearer 45-degree shot video."}

    stance_score = (_score_from_error(float(np.mean(stance_errors)), 120.0) + _score_from_error(abs(float(np.mean(knee_angles)) - 150.0), 0.08)) / 2.0
    hand_score = _score_from_error(abs(float(np.mean(hand_sep_values)) - 0.12), 45.0)
    pocket_score = _score_from_error(abs(float(np.mean(shot_pocket_values)) - 0.18), 55.0)
    eyes_score = _score_from_error(float(np.mean(nose_align_values)), 140.0)
    elbow_score = _score_from_error(float(np.mean(elbow_errors)), 180.0)
    release_score = round(1.0 + (9.0 * (release_hits / processed_frames)), 1)

    tail_start = int(len(hip_centers) * 0.75)
    landing_std = float(np.std(hip_centers[tail_start:])) if tail_start < len(hip_centers) else float(np.std(hip_centers))
    hold_score = _score_from_error(landing_std, 300.0)

    step_scores = {
        "Stance and Balance": round(stance_score, 1),
        "Hand Placement": round(hand_score, 1),
        "Shot Pocket": round(pocket_score, 1),
        "Eyes on Target": round(eyes_score, 1),
        "Elbow Alignment": round(elbow_score, 1),
        "Release and Follow Through": round(release_score, 1),
        "Hold and Evaluate": round(hold_score, 1),
    }

    feedback = {
        "Stance and Balance": "Good base, slight forward lean" if step_scores["Stance and Balance"] >= 7 else "Base alignment drifts; stabilize load and landing line",
        "Hand Placement": "Guide hand is mostly neutral" if step_scores["Hand Placement"] >= 7 else "Guide hand appears to influence ball path",
        "Shot Pocket": "Shot pocket is fairly repeatable" if step_scores["Shot Pocket"] >= 7 else "Pocket start point varies before lift",
        "Eyes on Target": "Head direction stays aligned to rim" if step_scores["Eyes on Target"] >= 7 else "Head/eye alignment drifts during motion",
        "Elbow Alignment": "Elbow stays close to shooting line" if step_scores["Elbow Alignment"] >= 7 else "Elbow flare appears during lift",
        "Release and Follow Through": "Good extension and finish timing" if step_scores["Release and Follow Through"] >= 7 else "Finish higher and hold wrist snap longer",
        "Hold and Evaluate": "Landing balance remains controlled" if step_scores["Hold and Evaluate"] >= 7 else "Follow-through hold/landing stability needs work",
    }

    overall_100 = int(round(sum(step_scores.values()) / len(step_scores) * 10))
    return {
        "scores": step_scores,
        "feedback": feedback,
        "overall_score": overall_100,
        "classification": _v1_classification(overall_100),
    }

def add_skill_player(first,last,nick,parent,email,phone,school,grad_year,age,pos,hand,height,level,goal,package,status,notes):
    return execute("""INSERT INTO skill_players(first_name,last_name,nickname,parent_guardian,contact_email,contact_phone,school,graduation_year,age_group,position,shooting_hand,height,skill_level,training_goal,package_type,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (first,last,nick,parent,email,phone,school,grad_year,age,pos,hand,height,level,goal,package,status,notes,now()))

def add_team(name, age, coach, season, notes):
    return execute("INSERT INTO teams(team_name,age_group,coach_name,season,notes,created_at) VALUES(?,?,?,?,?,?)", (name,age,coach,season,notes,now()))

def add_team_player(team_id, first,last,nick,age,pos,hand,height,notes):
    return execute("""INSERT INTO players(team_id,first_name,last_name,nickname,age_group,position,shooting_hand,height,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""", (team_id,first,last,nick,age,pos,hand,height,notes,now()))

def update_active_package(skill_player_id):
    pk = q("SELECT * FROM training_packages WHERE skill_player_id=? AND status='Active' AND sessions_remaining>0 ORDER BY expiration_date ASC, package_id ASC LIMIT 1", (skill_player_id,))
    if pk.empty: return "No active package found or no remaining sessions."
    p = pk.iloc[0]; used = int(p["sessions_used"] or 0)+1; rem = max(0, int(p["sessions_remaining"] or 0)-1); status = "Completed" if rem == 0 else "Active"
    execute("UPDATE training_packages SET sessions_used=?,sessions_remaining=?,status=? WHERE package_id=?", (used,rem,status,int(p["package_id"])))
    return f"Updated package {int(p['package_id'])}: used {used}, remaining {rem}."

def save_session(player_id,skill_player_id,team_id,session_date,session_type,session_context,coach,location,mode,scores,notes,make_miss,shot_context,homework='',next_focus='',package_counted='No'):
    pkg_status = "Not counted"
    if package_counted == "Yes" and skill_player_id: pkg_status = update_active_package(skill_player_id)
    sid = execute("""INSERT INTO sessions(player_id,skill_player_id,team_id,session_date,session_type,session_context,coach_name,location,analysis_mode,overall_score,make_miss,shot_context,homework_assigned,next_session_focus,coach_notes,package_counted,package_update_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (player_id,skill_player_id,team_id,str(session_date),session_type,session_context,coach,location,mode,overall(scores),make_miss,shot_context,homework,next_focus,notes,package_counted,pkg_status,now()))
    for step, score in scores.items(): execute("INSERT INTO evaluations(session_id,fundamental,score,rating,recommendation) VALUES(?,?,?,?,?)", (sid,step,score,rating(score),recommendation(step,score)))
    return sid, pkg_status

def latest_scores(player_id=None, skill_player_id=None):
    if skill_player_id: s = q("SELECT * FROM sessions WHERE skill_player_id=? ORDER BY session_date DESC,session_id DESC LIMIT 1", (skill_player_id,))
    elif player_id: s = q("SELECT * FROM sessions WHERE player_id=? ORDER BY session_date DESC,session_id DESC LIMIT 1", (player_id,))
    else: return None
    if s.empty: return None
    ev = q("SELECT fundamental,score FROM evaluations WHERE session_id=?", (int(s.iloc[0]["session_id"]),))
    return {r["fundamental"]: float(r["score"]) for _, r in ev.iterrows()} if not ev.empty else None

def latest_scores_for_mode(player_id=None, skill_player_id=None, mode_label=None):
    sessions_df = sessions_for_subject(player_id, skill_player_id)
    if sessions_df.empty:
        return None

    if mode_label:
        filtered = sessions_df[
            sessions_df["analysis_mode"].fillna("").str.lower().str.contains(mode_label.lower())
        ]
    else:
        filtered = sessions_df

    if filtered.empty:
        return None

    sid = int(filtered.iloc[-1]["session_id"])
    ev = q("SELECT fundamental,score FROM evaluations WHERE session_id=?", (sid,))
    return {r["fundamental"]: float(r["score"]) for _, r in ev.iterrows()} if not ev.empty else None

def sessions_for_subject(player_id=None, skill_player_id=None):
    if skill_player_id: return q("SELECT * FROM sessions WHERE skill_player_id=? ORDER BY session_date ASC,session_id ASC", (skill_player_id,))
    if player_id: return q("SELECT * FROM sessions WHERE player_id=? ORDER BY session_date ASC,session_id ASC", (player_id,))
    return pd.DataFrame()

def invoice_number():
    t = datetime.now().strftime("%Y%m%d"); n = int(q("SELECT COUNT(*) AS n FROM payments WHERE invoice_number LIKE ?", (f"INV-{t}-%",)).iloc[0]["n"])+1; return f"INV-{t}-{n:03d}"

def outstanding_balance(skill_player_id):
    df = q("SELECT COALESCE(SUM(balance),0) AS balance FROM payments WHERE skill_player_id=?", (skill_player_id,)); return float(df.iloc[0]["balance"] or 0) if not df.empty else 0.0

def make_parent_report(subject, scores, sessions_df):
    if not scores: return "No evaluation data available yet. Save at least one evaluation first."
    weak = weakest(scores, 3); strong = strongest(scores, 2); latest = sessions_df.iloc[-1] if not sessions_df.empty else None; first = sessions_df.iloc[0] if len(sessions_df) > 1 else None
    change = f"\nOverall Change Since First Session: {latest['overall_score']-first['overall_score']:+.1f} points" if first is not None and latest is not None else ""
    body = f"# Player Progress Report\n\nPlayer: {subject['name']}\nReport Date: {date.today()}\nTraining Context: {subject['context']}\nCurrent Overall Score: {overall(scores)}/100{change}\n\n## Strengths\n"
    for k,v in strong: body += f"- {k}: {v:.1f}/100 - {simple_rating(v)}\n"
    body += "\n## Current Improvement Priorities\n"
    for k,v in weak: body += f"- {k}: {v:.1f}/100 - Recommended drill: {DRILL_MAP.get(k)}\n"
    body += f"\n## Coach Summary\n{subject['name']} is progressing through the shooting development framework.\n\n## Homework\n"
    body += latest["homework_assigned"] if latest is not None and latest.get("homework_assigned") else "Complete 100 focused form shots."
    body += "\n\n## Next Session Focus\n"
    body += latest["next_session_focus"] if latest is not None and latest.get("next_session_focus") else weak[0][0]
    return body

def make_invoice_text(payment_id):
    p = q("""SELECT py.*, sp.first_name || ' ' || COALESCE(sp.last_name,'') AS player_name, sp.parent_guardian, sp.contact_email, tp.package_name FROM payments py LEFT JOIN skill_players sp ON sp.skill_player_id=py.skill_player_id LEFT JOIN training_packages tp ON tp.package_id=py.package_id WHERE py.payment_id=?""", (payment_id,))
    if p.empty: return "Invoice not found."
    r = p.iloc[0]
    return f"# Basketball Training Invoice\n\nInvoice Number: {r['invoice_number']}\nPayment Date: {r['payment_date']}\nPlayer: {r['player_name']}\nParent/Guardian: {r['parent_guardian'] or ''}\nContact: {r['contact_email'] or ''}\nPackage: {r['package_name'] or 'N/A'}\n\n## Payment Summary\nAmount Due: ${float(r['amount_due'] or 0):.2f}\nAmount Paid: ${float(r['amount_paid'] or 0):.2f}\nBalance: ${float(r['balance'] or 0):.2f}\nPayment Method: {r['payment_method']}\nPayment Status: {r['payment_status']}\n\n## Notes\n{r['notes'] or ''}\n"

def make_weekly_brief(start_date, end_date):
    sessions = q("""SELECT s.*, COALESCE(sp.first_name || ' ' || COALESCE(sp.last_name,''), p.first_name || ' ' || COALESCE(p.last_name,'')) AS player_name FROM sessions s LEFT JOIN skill_players sp ON sp.skill_player_id=s.skill_player_id LEFT JOIN players p ON p.player_id=s.player_id WHERE s.session_date BETWEEN ? AND ? ORDER BY s.session_date ASC""", (str(start_date), str(end_date)))
    body = f"# Weekly Coach Briefing\n\nDate Range: {start_date} to {end_date}\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

    # --- Sessions ---
    if sessions.empty:
        body += "\n## Sessions\nNo sessions recorded for this date range.\n"
    else:
        body += f"\n## Sessions\n- Total sessions this week: {len(sessions)}\n- Average overall score: {sessions['overall_score'].mean():.1f}/100\n- Unique players: {sessions['player_name'].nunique()}\n\n### Session Log\n"
        for _, r in sessions.iterrows():
            body += f"- {r['session_date']} | {r['player_name']} | {r['session_context']} | Score: {r['overall_score']}/100 | Next focus: {r['next_session_focus'] or 'N/A'}\n"

    # --- Program-wide focus areas ---
    all_evals = q("""SELECT e.fundamental, AVG(e.score) AS avg_score FROM evaluations e JOIN sessions s ON s.session_id=e.session_id WHERE s.session_date BETWEEN ? AND ? GROUP BY e.fundamental ORDER BY avg_score ASC""", (str(start_date), str(end_date)))
    if not all_evals.empty:
        body += "\n## Program-Wide Focus Areas\n"
        body += "### Lowest Scoring Fundamentals This Week\n"
        for _, r in all_evals.head(3).iterrows():
            body += f"- {r['fundamental']}: {r['avg_score']:.1f}/100 avg — Drill: {DRILL_MAP.get(r['fundamental'], 'N/A')}\n"
        body += "\n### Highest Scoring Fundamentals This Week\n"
        for _, r in all_evals.tail(2).iloc[::-1].iterrows():
            body += f"- {r['fundamental']}: {r['avg_score']:.1f}/100 avg\n"

    # --- Upcoming calendar events ---
    lookahead = str(date.today() + timedelta(days=14))
    events = q("SELECT * FROM coach_calendar WHERE event_date BETWEEN ? AND ? ORDER BY event_date ASC, event_time ASC", (str(date.today()), lookahead))
    if events.empty:
        body += "\n## Upcoming Calendar Events\nNo events scheduled in the next 14 days.\n"
    else:
        body += "\n## Upcoming Calendar Events\n"
        for _, e in events.iterrows():
            body += f"- {e['event_date']} {e['event_time'] or ''} | {e['event_type']} | {e['event_title']} | {e['location'] or 'TBD'} | {e['status']}\n"

    # --- Payment follow-ups ---
    overdue = q("SELECT py.*, sp.first_name || ' ' || COALESCE(sp.last_name,'') AS player_name FROM payments py LEFT JOIN skill_players sp ON sp.skill_player_id=py.skill_player_id WHERE py.payment_status IN ('Unpaid','Partial','Overdue') AND py.balance>0 ORDER BY py.payment_date ASC")
    if overdue.empty:
        body += "\n## Payment Follow-Ups\nNo outstanding balances.\n"
    else:
        body += f"\n## Payment Follow-Ups ({len(overdue)} outstanding)\n"
        for _, p in overdue.head(10).iterrows():
            body += f"- {p.get('player_name','Unknown')} | Invoice {p['invoice_number']} | Balance: ${float(p['balance'] or 0):.2f} | Status: {p['payment_status']}\n"

    # --- Communication follow-ups due this week ---
    comm_fu = q("SELECT * FROM communication_followups WHERE followup_date BETWEEN ? AND ? AND status='Pending' ORDER BY followup_date ASC", (str(start_date), str(end_date)))
    if comm_fu.empty:
        body += "\n## Communication Follow-Ups\nNo pending follow-ups due this week.\n"
    else:
        body += f"\n## Communication Follow-Ups ({len(comm_fu)} pending)\n"
        for _, f in comm_fu.iterrows():
            body += f"- {f['followup_date']} | {f['followup_type']} | {f['recipient_name'] or 'N/A'} | {f['subject'] or ''}\n"

    # --- Coach action items ---
    action_items = ["Review session scores and update player homework assignments."]
    if not overdue.empty: action_items.append(f"Follow up on {len(overdue)} outstanding payment balance(s).")
    if not comm_fu.empty: action_items.append(f"Complete {len(comm_fu)} pending communication follow-up(s).")
    if not events.empty: action_items.append("Confirm all upcoming calendar events and locations.")
    action_items.append("Update coach calendar with any new sessions or meetings.")
    body += "\n## Coach Action Items\n"
    for item in action_items:
        body += f"- {item}\n"

    return body

def generate_parent_message(subject, msg_type, balance=0):
    raw = subject["raw"]; name = subject["name"]
    parent = raw.get("parent_guardian", "") or "Parent/Guardian"
    contact = raw.get("contact_email", "") or raw.get("contact_phone", "")
    scores = latest_scores(subject["player_id"], subject["skill_player_id"])
    focus = weakest(scores, 1)[0][0] if scores else "shooting consistency"
    score_val = overall(scores) if scores else None
    drill = DRILL_MAP.get(focus, "form shooting")
    ss = sessions_for_subject(subject["player_id"], subject["skill_player_id"])
    hw = ss.iloc[-1]["homework_assigned"] if not ss.empty and ss.iloc[-1].get("homework_assigned") else "100 focused form shots daily."
    next_focus = ss.iloc[-1]["next_session_focus"] if not ss.empty and ss.iloc[-1].get("next_session_focus") else focus

    if msg_type == "Progress Update":
        subj = f"Shooting Development Update — {name}"
        body = (
            f"Hi {parent},\n\n"
            f"I wanted to share a quick progress update for {name}.\n\n"
            f"Current Overall Score: {score_val}/100\n"
            f"Primary Focus Area: {focus}\n"
            f"Recommended Drill: {drill}\n\n"
            f"{'Your player is making solid progress and we will continue building on recent sessions.' if score_val and score_val >= 70 else 'We are actively working on targeted areas to build consistency and confidence.'}\n\n"
            f"Next session focus: {next_focus}\n\n"
            f"Please don't hesitate to reach out with any questions.\n\n"
            f"Thank you for your continued support,\nCoach"
        )
        sms = f"Hi {parent}, quick update on {name}: score {score_val}/100, focus: {focus}. Next session: {next_focus}. — Coach"

    elif msg_type == "Homework Reminder":
        subj = f"Shooting Homework Reminder — {name}"
        body = (
            f"Hi {parent},\n\n"
            f"Just a friendly reminder about {name}'s shooting homework before the next session.\n\n"
            f"Homework Assignment:\n{hw}\n\n"
            f"Consistent at-home reps are one of the fastest ways to lock in the fundamentals we are working on. "
            f"Even 10–15 minutes of focused practice each day makes a significant difference.\n\n"
            f"Current drill focus: {drill}\n\n"
            f"Please let me know if you have any questions about the assignment.\n\n"
            f"Thank you,\nCoach"
        )
        sms = f"Hi {parent}, reminder: {name}'s homework is — {hw[:120]}. — Coach"

    elif msg_type == "Payment Reminder":
        subj = f"Training Balance Reminder — {name}"
        body = (
            f"Hi {parent},\n\n"
            f"I hope things are going well! I wanted to send a quick reminder that {name}'s current training balance is ${balance:.2f}.\n\n"
            f"If you have any questions about your invoice or would like to discuss payment options, "
            f"please feel free to reach out at your convenience.\n\n"
            f"Thank you so much for your support of {name}'s development — it is truly appreciated.\n\n"
            f"Best regards,\nCoach"
        )
        sms = f"Hi {parent}, friendly reminder: {name}'s training balance is ${balance:.2f}. Thank you! — Coach"

    elif msg_type == "Schedule Reminder":
        cal = q("SELECT * FROM coach_calendar WHERE skill_player_id=? AND event_date>=? ORDER BY event_date ASC LIMIT 1",
                (subject["skill_player_id"], str(date.today()))) if subject["skill_player_id"] else pd.DataFrame()
        if not cal.empty:
            ev = cal.iloc[0]
            event_detail = f"{ev['event_date']} at {ev['event_time'] or 'TBD'} — {ev['event_title']} ({ev['location'] or 'location TBD'})"
        else:
            event_detail = "our next scheduled session (details to follow)"
        subj = f"Upcoming Session Reminder — {name}"
        body = (
            f"Hi {parent},\n\n"
            f"Just a quick reminder that {name}'s next session is scheduled for:\n\n"
            f"{event_detail}\n\n"
            f"Please arrive a few minutes early if possible so we can get started on time. "
            f"Make sure {name} has water, proper footwear, and a basketball if available.\n\n"
            f"Looking forward to working with {name}!\n\n"
            f"See you soon,\nCoach"
        )
        sms = f"Hi {parent}, reminder: {name}'s session — {event_detail}. See you there! — Coach"

    else:  # Report Card Note
        subj = f"Player Report Card Ready — {name}"
        body = (
            f"Hi {parent},\n\n"
            f"I have completed {name}'s latest player report card and wanted to share a summary.\n\n"
            f"Overall Shooting Score: {score_val}/100\n"
            f"Top Strength: {strongest(scores, 1)[0][0] if scores else 'See report'}\n"
            f"Current Priority: {focus}\n"
            f"Recommended Drill: {drill}\n\n"
            f"A full PDF report is available — please let me know if you would like me to send it directly.\n\n"
            f"It's a pleasure working with {name}, and I look forward to continued progress.\n\n"
            f"Thank you,\nCoach"
        )
        sms = f"Hi {parent}, {name}'s report card is ready. Score: {score_val}/100. Priority: {focus}. — Coach"

    return subj, body, sms, parent, contact

def generate_practice_script(subject, focus, script_type, duration, intensity, notes):
    return f"# Practice Script\n\nDate: {date.today()}\nType: {script_type}\nSubject: {subject['name']}\nFocus Area: {focus}\nDuration: {duration} minutes\nIntensity: {intensity}\n\n## Warmup\n5-10 minutes of movement, ball handling, and close-range form shooting.\n\n## Skill Block\n{DRILL_MAP.get(focus)}\n\n## Shooting Block\nControlled to game-speed shooting reps. Track makes, misses, and form quality.\n\n## Competition Block\nBeat-the-Pro or timed make goal.\n\n## Homework\n100-150 focused reps before the next session.\n\n## Coach Notes\n{notes}\n"


def infer_focus_from_latest_subject(subject):
    scores = latest_scores(subject.get('player_id'), subject.get('skill_player_id')) if subject else None
    if not scores:
        return SHOOTING_STEPS[0]
    weak = weakest(scores, 1)
    return weak[0][0] if weak else SHOOTING_STEPS[0]


def infer_weakness_for_skill_player(skill_player_id):
    if not skill_player_id:
        return SHOOTING_STEPS[0]
    scores = latest_scores(skill_player_id=skill_player_id)
    if not scores:
        return SHOOTING_STEPS[0]
    weak = weakest(scores, 1)
    return weak[0][0] if weak else SHOOTING_STEPS[0]


def infer_weakness_for_team(team_id):
    if not team_id:
        return SHOOTING_STEPS[0]
    weakness_df = q(
        """
        SELECT e.fundamental, AVG(e.score) AS avg_score
        FROM evaluations e
        JOIN sessions s ON s.session_id = e.session_id
        WHERE s.team_id = ?
        GROUP BY e.fundamental
        ORDER BY avg_score ASC
        LIMIT 1
        """,
        (int(team_id),),
    )
    if weakness_df.empty:
        return SHOOTING_STEPS[0]
    weakness_name = str(weakness_df.iloc[0].get("fundamental", "")).strip()
    return weakness_name if weakness_name in SHOOTING_STEPS else SHOOTING_STEPS[0]


def get_drill_library_df(target_fundamental=None, skill_level=None):
    if target_fundamental:
        df = q("SELECT * FROM drills WHERE target_fundamental=? ORDER BY drill_name", (target_fundamental,))
    else:
        df = q("SELECT * FROM drills ORDER BY target_fundamental, drill_name")

    if skill_level and not df.empty:
        levels = df.get("skill_levels", pd.Series([""] * len(df))).fillna("").astype(str)
        df = df[(levels == "") | (levels.str.contains(skill_level, case=False, na=False))]
    return df


def sync_drill_library_csv():
    drill_df = get_drill_library_df()
    if drill_df.empty:
        headers = ["drill_id", "drill_name", "target_fundamental", "description", "reps", "coaching_cues", "skill_levels", "created_at"]
        pd.DataFrame(columns=headers).to_csv(V27_DRILL_LIBRARY_CSV, index=False)
    else:
        drill_df.to_csv(V27_DRILL_LIBRARY_CSV, index=False)
    return str(V27_DRILL_LIBRARY_CSV)


def save_v27_practice_plan_json(plan_scope, focus_area, payload):
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    scope_slug = safe_filename(plan_scope or 'Practice')
    focus_slug = safe_filename(focus_area or 'Focus')
    file_name = f"{scope_slug}_{focus_slug}_Practice_{stamp}.json"
    out_path = V27_PRACTICE_PLAN_DIR / file_name
    with open(out_path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2)
    return str(out_path)


def append_v27_completion_history(plan_id, plan_scope, subject_name, team_name, focus_area, skill_level, completed_count, total_count, status, notes):
    file_exists = V27_PRACTICE_HISTORY_CSV.exists()
    headers = [
        'timestamp', 'plan_id', 'plan_scope', 'subject_name', 'team_name', 'focus_area',
        'skill_level', 'completed_drills', 'total_drills', 'completion_percent', 'status', 'notes'
    ]
    completion_pct = round((completed_count / total_count) * 100.0, 1) if total_count else 0.0
    row = {
        'timestamp': now(),
        'plan_id': int(plan_id),
        'plan_scope': plan_scope,
        'subject_name': subject_name,
        'team_name': team_name,
        'focus_area': focus_area,
        'skill_level': skill_level,
        'completed_drills': int(completed_count),
        'total_drills': int(total_count),
        'completion_percent': completion_pct,
        'status': status,
        'notes': notes,
    }
    with open(V27_PRACTICE_HISTORY_CSV, 'a', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def load_v27_completion_history():
    if not V27_PRACTICE_HISTORY_CSV.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(V27_PRACTICE_HISTORY_CSV)
    except Exception:
        return pd.DataFrame()


def build_v27_practice_plan_md(plan_scope, subject_name, team_name, focus_area, duration_minutes, skill_level, selected_drills, coach_notes="", video_link_map=None, qr_link_map=None):
    subject_line = f"Team: {team_name}" if plan_scope == 'Team' else f"Player: {subject_name}"
    warmup_minutes = 10 if duration_minutes >= 60 else 6
    cooldown_minutes = 8 if duration_minutes >= 60 else 5
    work_minutes = max(10, duration_minutes - warmup_minutes - cooldown_minutes)

    if not selected_drills:
        selected_drills = [DRILL_MAP.get(focus_area, 'Form Shooting')]

    per_drill = max(6, int(work_minutes / len(selected_drills)))

    lines = [
        "# V2.7 Practice Plan",
        "",
        f"Date: {date.today()}",
        f"Plan Scope: {plan_scope}",
        subject_line,
        f"Focus Area: {focus_area}",
        f"Skill Level: {skill_level}",
        f"Total Duration: {duration_minutes} minutes",
        "",
        "## Practice Flow",
        f"- Warmup ({warmup_minutes} min): dynamic mobility, footwork prep, and form closeouts.",
    ]

    for idx, drill_name in enumerate(selected_drills, start=1):
        line = f"- Drill Block {idx} ({per_drill} min): {drill_name}"
        if video_link_map and str(drill_name) in video_link_map:
            video_ref = str(video_link_map.get(str(drill_name), "") or "").strip()
            if video_ref:
                line += f" | Video: {video_ref}"
        if qr_link_map and str(drill_name) in qr_link_map:
            qr_ref = str(qr_link_map.get(str(drill_name), "") or "").strip()
            if qr_ref:
                line += f" | QR: {qr_ref}"
        lines.append(line)

    lines.extend([
        f"- Competitive Finisher ({max(5, int(work_minutes * 0.2))} min): score pressure reps and quick feedback.",
        f"- Cooldown + Review ({cooldown_minutes} min): breath, stretch, and coaching recap.",
        "",
        "## Coach Emphasis",
        f"- Keep all reps tied to {focus_area} quality cues.",
        "- Track makes/misses by miss pattern (short, long, left, right).",
        "- Stop and correct mechanics immediately when quality drops.",
        "",
        "## Completion Tracking",
        "- Mark each drill block complete after execution.",
        "- Save notes on what improved and what still needs reps.",
    ])

    if coach_notes:
        lines.extend(["", "## Coach Notes", coach_notes])

    return "\n".join(lines)


def save_uploaded_media(uploaded_file, output_dir, prefix):
    if uploaded_file is None:
        return ""
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    suffix = Path(uploaded_file.name).suffix or ".bin"
    out_name = f"{safe_filename(prefix)}_{stamp}{suffix}"
    out_path = Path(output_dir) / out_name
    with open(out_path, 'wb') as handle:
        handle.write(uploaded_file.getbuffer())
    return str(out_path)


def build_instruction_card_markdown(drill_name, target_fundamental, description, reps, coaching_cues, demo_link, coach_demo_link, homework_text, at_home_plan):
    lines = [
        "# Drill Instruction Card",
        "",
        f"Drill: {drill_name}",
        f"Target Fundamental: {target_fundamental}",
        f"Date: {date.today()}",
        "",
        "## Objective",
        description or "Improve mechanics and consistency through structured repetitions.",
        "",
        "## Volume",
        reps or "5 spots x 8 makes",
        "",
        "## Coaching Cues",
        coaching_cues or "Stay balanced and hold your finish.",
        "",
        "## Video References",
        f"- Drill Demo Video: {demo_link or 'Not set'}",
        f"- Coach Demonstration Clip: {coach_demo_link or 'Not set'}",
        "",
        "## Homework Assignment",
        homework_text or "Complete 60 quality reps and track make/miss notes.",
        "",
        "## At-Home Shooting Plan",
        at_home_plan or "3 sets x 20 reps across 3 spots.",
    ]
    return "\n".join(lines)


def generate_qr_code_image(link_text, label):
    if not link_text:
        return "", "No link provided for QR code generation."
    if not QR_AVAILABLE:
        return "", "QR dependency unavailable. Install qrcode package."
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_name = f"{safe_filename(label)}_qr_{stamp}.png"
    out_path = V28_QR_CODE_DIR / out_name
    qr_img = qrcode.make(link_text)
    qr_img.save(out_path)
    return str(out_path), "QR code generated."


def sync_v28_homework_assignments_csv():
    df = q('SELECT * FROM at_home_assignments ORDER BY assignment_id DESC')
    if df.empty:
        headers = [
            'assignment_id', 'plan_id', 'plan_drill_id', 'skill_player_id', 'assigned_date', 'due_date',
            'reps_goal', 'makes_goal', 'status', 'notes', 'completed_at', 'created_at', 'assignment_pdf_path'
        ]
        pd.DataFrame(columns=headers).to_csv(V28_HOMEWORK_ASSIGNMENTS_CSV, index=False)
    else:
        df.to_csv(V28_HOMEWORK_ASSIGNMENTS_CSV, index=False)
    return str(V28_HOMEWORK_ASSIGNMENTS_CSV)


def sync_v29_homework_submissions_csv():
    df = q('SELECT * FROM homework_submissions ORDER BY submission_id DESC')
    if df.empty:
        headers = [
            'submission_id', 'assignment_id', 'skill_player_id', 'submission_date', 'submission_video_path',
            'reps_completed', 'makes_completed', 'minutes_practiced', 'confidence_score', 'difficulty_score',
            'self_rating', 'player_notes', 'coach_status', 'coach_feedback',
            'effort_score', 'self_report_score', 'completion_score', 'score_label', 'created_at', 'reviewed_at'
        ]
        pd.DataFrame(columns=headers).to_csv(V29_HOMEWORK_SUBMISSIONS_CSV, index=False)
    else:
        df.to_csv(V29_HOMEWORK_SUBMISSIONS_CSV, index=False)
    return str(V29_HOMEWORK_SUBMISSIONS_CSV)


def homework_score_label(score):
    if score >= 90.0:
        return 'Excellent Completion'
    if score >= 80.0:
        return 'Strong Completion'
    if score >= 70.0:
        return 'Completed'
    if score >= 50.0:
        return 'Partial Completion'
    return 'Needs Follow-Up'


def calculate_homework_completion_score(reps_goal, makes_goal, minutes_goal, reps_completed, makes_completed, minutes_practiced, confidence_score):
    reps_goal_v = max(1, int(reps_goal or 0))
    makes_goal_v = max(1, int(makes_goal or 0))
    minutes_goal_v = max(1, int(minutes_goal or 0))
    reps_completed_v = max(0, int(reps_completed or 0))
    makes_completed_v = max(0, int(makes_completed or 0))
    minutes_v = max(0, int(minutes_practiced or 0))
    confidence_v = max(0, min(10, int(confidence_score or 0)))

    reps_ratio = min(1.0, reps_completed_v / reps_goal_v)
    makes_ratio = min(1.0, makes_completed_v / makes_goal_v)
    minutes_ratio = min(1.0, minutes_v / minutes_goal_v)

    effort_score = round(
        100.0 * (
            (0.35 * reps_ratio)
            + (0.35 * makes_ratio)
            + (0.30 * minutes_ratio)
        ),
        1,
    )
    self_report_score = round((confidence_v / 10.0) * 100.0, 1)
    completion_score = round((0.80 * effort_score) + (0.20 * self_report_score), 1)
    completion_score = max(0.0, min(100.0, completion_score))
    return effort_score, self_report_score, completion_score, homework_score_label(completion_score)


def build_homework_report_markdown(player_name, drill_name, target_fundamental, reps_goal, makes_goal, homework_notes, demo_link, qr_path, at_home_plan, completion_status, completion_log):
    lines = [
        "# Player Homework Report",
        "",
        f"Player: {player_name}",
        f"Date: {date.today()}",
        f"Drill: {drill_name}",
        f"Target Fundamental: {target_fundamental}",
        "",
        "## Drill Description",
        f"- Reps Goal: {reps_goal}",
        f"- Makes Goal: {makes_goal}",
        f"- Homework Notes: {homework_notes or 'Complete focused quality reps.'}",
        "",
        "## Demo References",
        f"- Demo Video Link: {demo_link or 'Not set'}",
        f"- QR Code Path: {qr_path or 'Not generated'}",
        "",
        "## At-Home Shooting Plan",
        at_home_plan or "3 sets x 20 reps with form checks between sets.",
        "",
        "## Completion Log",
        f"- Current Status: {completion_status}",
        f"- Notes: {completion_log or 'No completion notes yet.'}",
    ]
    return "\n".join(lines)


def build_parent_progress_markdown(player_name, latest_shot_score, assignments_total, submitted_total, reviewed_total, on_time_rate, avg_score, latest_review_status, latest_feedback):
    lines = [
        "# Parent / Player Progress Report",
        "",
        f"Player: {player_name}",
        f"Generated: {date.today()}",
        "",
        "## Snapshot",
        f"- Latest Shot Intelligence Score: {latest_shot_score}",
        f"- Homework Assignments: {assignments_total}",
        f"- Homework Submitted: {submitted_total}",
        f"- Coach Reviewed: {reviewed_total}",
        f"- On-Time Submission Rate: {on_time_rate}%",
        f"- Average Homework Completion Score: {avg_score}",
        "",
        "## Latest Coach Review",
        f"- Review Status: {latest_review_status}",
        f"- Coach Feedback: {latest_feedback or 'No coach feedback yet.'}",
    ]
    return "\n".join(lines)

def markdown_to_paragraphs(markdown_text):
    lines = str(markdown_text).splitlines()
    story_items = []
    for line in lines:
        line = line.strip()
        if not line:
            story_items.append(("space", ""))
        elif line.startswith("# "):
            story_items.append(("title", line[2:]))
        elif line.startswith("## "):
            story_items.append(("heading", line[3:]))
        elif line.startswith("- "):
            story_items.append(("bullet", line[2:]))
        else:
            story_items.append(("body", line))
    return story_items

def pdf_from_markdown(title, md, out):
    if not REPORTLAB_AVAILABLE: return None, "ReportLab is not installed. Run pip install -r requirements.txt"
    out = Path(out); styles = getSampleStyleSheet(); doc = SimpleDocTemplate(str(out), pagesize=letter, rightMargin=.6*inch, leftMargin=.6*inch, topMargin=.6*inch, bottomMargin=.6*inch)
    story = [Paragraph(title, styles["Title"]), Spacer(1,8)]
    for line in str(md).splitlines():
        line = line.strip()
        if not line: story.append(Spacer(1,6)); continue
        esc = line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        if line.startswith("# "): story.append(Paragraph(esc[2:], styles["Title"]))
        elif line.startswith("## "): story.append(Paragraph(esc[3:], styles["Heading2"]))
        elif line.startswith("- "): story.append(Paragraph("• " + esc[2:], styles["BodyText"]))
        else: story.append(Paragraph(esc, styles["BodyText"]))
    doc.build(story); return str(out), "PDF created."

def create_pdf_from_markdown(title, markdown_text, output_path):
    if not REPORTLAB_AVAILABLE:
        return None, "ReportLab is not installed. Run: pip install -r requirements.txt"
    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        styles = getSampleStyleSheet()
        style_title   = styles["Title"]
        style_heading = styles["Heading2"]
        style_body    = styles["BodyText"]
        style_bullet  = ParagraphStyle("Bullet", parent=styles["BodyText"], leftIndent=16, bulletIndent=8)
        doc = SimpleDocTemplate(
            str(out), pagesize=letter,
            rightMargin=0.6*inch, leftMargin=0.6*inch,
            topMargin=0.6*inch, bottomMargin=0.6*inch
        )
        story = [Paragraph(str(title).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"), style_title), Spacer(1, 10)]
        for kind, text in markdown_to_paragraphs(markdown_text):
            esc = str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            if kind == "space":
                story.append(Spacer(1, 6))
            elif kind == "title":
                story.append(Paragraph(esc, style_title))
            elif kind == "heading":
                story.append(Paragraph(esc, style_heading))
            elif kind == "bullet":
                story.append(Paragraph("• " + esc, style_bullet))
            else:
                story.append(Paragraph(esc, style_body))
        doc.build(story)
        return str(out), "PDF created successfully."
    except Exception as e:
        return None, f"PDF generation failed: {e}"

def register_pdf(pdf_type, subject_name, source_table, source_id, file_path):
    execute("INSERT INTO generated_pdfs(pdf_type,subject_name,source_table,source_id,file_path,created_at) VALUES(?,?,?,?,?,?)", (pdf_type, subject_name, source_table, source_id, str(file_path), now()))

def export_queries():
    return {"Skill Players":"SELECT * FROM skill_players ORDER BY first_name,last_name", "Team Players":"SELECT p.*,t.team_name FROM players p LEFT JOIN teams t ON t.team_id=p.team_id", "Teams":"SELECT * FROM teams ORDER BY team_name", "Sessions":"SELECT * FROM sessions ORDER BY session_date DESC", "Evaluations":"SELECT * FROM evaluations ORDER BY evaluation_id DESC", "Drill Library":"SELECT * FROM drills ORDER BY target_fundamental,drill_name", "Generated Reports":"SELECT * FROM generated_reports ORDER BY created_at DESC", "Generated PDFs":"SELECT * FROM generated_pdfs ORDER BY created_at DESC", "Training Packages":"SELECT * FROM training_packages ORDER BY created_at DESC", "Attendance":"SELECT * FROM attendance ORDER BY attendance_date DESC", "Payments":"SELECT * FROM payments ORDER BY payment_date DESC", "Parent Messages":"SELECT * FROM parent_messages ORDER BY created_at DESC", "Communication Followups":"SELECT * FROM communication_followups ORDER BY followup_date DESC", "Practice Scripts":"SELECT * FROM practice_scripts ORDER BY script_date DESC", "Practice Plans":"SELECT * FROM practice_plans ORDER BY plan_date DESC", "Practice Plan Drills":"SELECT * FROM practice_plan_drills ORDER BY plan_id DESC, drill_order ASC", "At-Home Assignments":"SELECT * FROM at_home_assignments ORDER BY assignment_id DESC", "Homework Submissions":"SELECT * FROM homework_submissions ORDER BY submission_id DESC", "Coach Calendar":"SELECT * FROM coach_calendar ORDER BY event_date DESC", "System Backups":"SELECT * FROM system_backups ORDER BY created_at DESC"}

def create_backup_zip():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"basketball_ai_v1_6_backup_{stamp}.zip"
    csv_files = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        # 1. Add SQLite database
        if DB_PATH.exists():
            z.write(DB_PATH, Path("database") / DB_PATH.name)
        # 2. Export each table as CSV
        for name, sql in export_queries().items():
            df = q(sql)
            csv = BACKUP_DIR / f"{safe_filename(name)}_{stamp}.csv"
            df.to_csv(csv, index=False)
            z.write(csv, Path("exports") / csv.name)
            csv_files.append(csv)
        # 3. Add generated PDFs
        pdf_count = 0
        for pdf in REPORT_DIR.glob("*.pdf"):
            z.write(pdf, Path("generated_pdfs") / pdf.name)
            pdf_count += 1
    # Clean up temp CSVs
    for csv in csv_files:
        csv.unlink(missing_ok=True)
    # 4. Register backup in system_backups
    execute("INSERT INTO system_backups(backup_name,backup_path,created_at) VALUES(?,?,?)",
            (path.name, str(path), now()))
    return path, pdf_count

def seed_demo():
    if q("SELECT COUNT(*) AS n FROM teams").iloc[0]["n"] > 0 or q("SELECT COUNT(*) AS n FROM skill_players").iloc[0]["n"] > 0: return
    tid = add_team("Portsmouth Elite","High School","Coach Demo","Summer 2026","Demo team.")
    p1 = add_team_player(tid,"Jordan","Sample","J-Smooth","High School","Guard","Right","6'1","Demo team player.")
    p2 = add_team_player(tid,"Taylor","Sample","T-Splash","High School","Wing","Left","5'10","Second demo team player.")

    sp1 = add_skill_player("Malik","Private","MJ","A. Private","parent@example.com","555-0100","Churchland HS","2028","High School","Guard","Right","5'11","Intermediate","Improve shooting consistency.","8-session package","Active","Demo skill client.")
    sp2 = add_skill_player("Avery","Trainer","Ace","R. Trainer","avery.parent@example.com","555-0142","Norcom HS","2027","High School","Guard","Right","6'0","Advanced","Quicker release under pressure.","12-session package","Active","Second demo skill client.")

    team_sid, _ = save_session(p1,None,tid,"2026-05-01","Practice","Team","Coach Demo","Gym","Manual Coach Scorecard", {"Feet & Stance":72,"Balance & Load":68,"Shot Pocket / Ball Prep":70,"Elbow & Arm Alignment":64,"Set Point & Eyes":75,"Release & Extension":69,"Follow-Through & Landing":66}, "Team baseline session.", "Unknown", "Catch-and-shoot")
    save_session(p2,None,tid,"2026-05-01","Practice","Team","Coach Demo","Gym","Manual Coach Scorecard", {"Feet & Stance":70,"Balance & Load":67,"Shot Pocket / Ball Prep":69,"Elbow & Arm Alignment":66,"Set Point & Eyes":73,"Release & Extension":68,"Follow-Through & Landing":65}, "Shared team practice baseline.", "Unknown", "Form shot")

    save_session(None,sp1,None,"2026-05-17","Private Lesson","Skill Coach","Coach Demo","Private Gym","Manual Coach Scorecard", {"Feet & Stance":76,"Balance & Load":72,"Shot Pocket / Ball Prep":75,"Elbow & Arm Alignment":68,"Set Point & Eyes":80,"Release & Extension":74,"Follow-Through & Landing":71}, "Improved rhythm.", "Make", "Catch-and-shoot", "150 catch-and-hold reps.", "Release extension.")
    save_session(None,sp2,None,"2026-05-16","Private Lesson","Skill Coach","Coach Demo","Private Gym","Manual Coach Scorecard", {"Feet & Stance":82,"Balance & Load":79,"Shot Pocket / Ball Prep":83,"Elbow & Arm Alignment":78,"Set Point & Eyes":84,"Release & Extension":80,"Follow-Through & Landing":77}, "Strong progress under fatigue.", "Make", "Off-dribble", "200 one-dribble pull-up reps.", "Faster gather to set point.")

    pkg = execute("""INSERT INTO training_packages(skill_player_id,package_name,package_type,sessions_purchased,sessions_used,sessions_remaining,price,start_date,expiration_date,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (sp1,"8-Session Shooting Development Package","Private Training",8,2,6,600,"2026-05-01","2026-08-01","Active","Demo package.",now()))
    execute("""INSERT INTO payments(skill_player_id,team_id,package_id,invoice_number,payment_date,amount_due,amount_paid,balance,payment_method,payment_status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (sp1,None,pkg,"INV-20260501-001","2026-05-01",600,300,300,"Zelle","Partial","Demo partial payment.",now()))

    execute("""INSERT INTO attendance(session_id,player_id,skill_player_id,team_id,attendance_date,attendance_status,reason,makeup_required,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""", (team_sid,p1,None,tid,"2026-05-01","Present","","No","Demo attendance record.",now()))

    execute("""INSERT INTO coach_calendar(skill_player_id,team_id,event_date,event_time,event_type,event_title,location,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""", (sp1,None,str(date.today()+timedelta(days=3)),"6:00 PM","Private Lesson","Malik Shooting Session","Private Gym","Scheduled","Continue release extension.",now()))

    execute("""INSERT INTO communication_followups(skill_player_id,player_id,team_id,followup_date,followup_type,recipient_name,recipient_contact,subject,message_body,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (sp1,None,None,str(date.today()+timedelta(days=2)),"Payment Reminder","A. Private","parent@example.com","Invoice Follow-Up","Checking in on remaining balance for Malik's training package.","Pending","Demo communication follow-up.",now()))

init_db()
st.markdown('<div style="font-size:2.4rem;font-weight:850">Basketball AI Shooting Coach V2.9</div>', unsafe_allow_html=True)
st.caption('PDF Export + Communication Automation Prep, built on V1.5.1 stabilization.')
teams = q("SELECT * FROM teams ORDER BY team_name"); skill_players = q("SELECT * FROM skill_players ORDER BY first_name,last_name"); sessions = q("SELECT * FROM sessions"); packages = q("SELECT * FROM training_packages"); payments = q("SELECT * FROM payments")
with st.sidebar:
    st.title('🏀 V2.9 Controls')
    st.markdown('[Open Challenge Hub (Port 8514)](http://localhost:8514)')
    app_lockdown = os.getenv('APP_LOCKDOWN') == '1'
    if app_lockdown:
        st.caption('Lockdown Mode: ON')
    if st.button('Load Demo Data', use_container_width=True, disabled=app_lockdown, help='Disabled while lockdown mode is active.'):
        seed_demo(); st.rerun()
    operating_mode = 'Skill Coach Mode'
    st.caption('Operating Mode: Player Only')
    selected_team_id=None; selected_team_player_id=None; selected_skill_player_id=None
    if not skill_players.empty:
        sopts = {f"{int(r.skill_player_id)} — {full_name(r)}": int(r.skill_player_id) for _, r in skill_players.iterrows()}; selected_skill_player_id = sopts[st.selectbox('Active Player', list(sopts.keys()))]
    st.divider(); session_type=st.selectbox('Session Type',['Private Lesson','Workout','Practice','Tryout','Game Film Review','Camp']); coach=st.text_input('Coach Name','Coach'); location=st.text_input('Location','Gym'); session_date=st.date_input('Session Date', date.today())

def get_active_subject():
    if operating_mode == 'Skill Coach Mode':
        if selected_skill_player_id is None: return None
        row = q('SELECT * FROM skill_players WHERE skill_player_id=?', (selected_skill_player_id,)).iloc[0]
        return {'context':'Skill Coach','player_id':None,'skill_player_id':selected_skill_player_id,'team_id':None,'name':full_name(row),'detail':f"{row['school'] or 'No School'} | {row['skill_level']} | {row['package_type']}",'raw':row}
    if selected_team_player_id is None: return None
    row = q('SELECT p.*,t.team_name FROM players p LEFT JOIN teams t ON t.team_id=p.team_id WHERE p.player_id=?', (selected_team_player_id,)).iloc[0]
    return {'context':'Team','player_id':selected_team_player_id,'skill_player_id':None,'team_id':selected_team_id,'name':full_name(row),'detail':row['team_name'] or 'No Team','raw':row}

c1,c2 = st.columns(2); c1.metric('Skill Players',len(skill_players)); c2.metric('Sessions',len(sessions))
st.markdown(
        """
        <div style='margin:12px 0 18px 0;padding:14px 16px;border:1px solid #d9dce3;border-radius:12px;background:#f7f9fc;'>
            <div style='font-size:1rem;font-weight:700;margin-bottom:6px;'>Challenge Hub Quick Access</div>
            <div style='font-size:0.92rem;margin-bottom:10px;'>Launch the separate challenge workflow for challenge creation, submissions, badges, and exports.</div>
            <a href='http://localhost:8514' target='_blank' style='display:inline-block;padding:8px 12px;border-radius:8px;background:#0b57d0;color:#ffffff;text-decoration:none;font-weight:600;'>Open Challenge Hub</a>
        </div>
        """,
        unsafe_allow_html=True,
)
LOCKED_SKILL_TABS = ['Setup','Manual Evaluation','AI Shooting Evaluation','Parent Communication','Practice Script Generator','Coach Calendar','Report Card','Weekly Briefing','Attendance Tracker','Skill Client Tracker','Practice / Homework Plans','PDF Export Center','Backup Bundle','Reports','Communication Follow-Ups','Business Center']
mode_tabs = LOCKED_SKILL_TABS.copy()
mode_tabs[9] = 'Team Coach Dashboard (V2.6)' if operating_mode == 'Team Mode' else 'Skill Client Tracker'
tabs = st.tabs(mode_tabs)
with tabs[0]:
    st.subheader('Setup'); a = st.container()
    with a:
        st.write('### Create Skill Player')
        with st.form('spform'):
            first=st.text_input('First Name *'); last=st.text_input('Last Name'); nick=st.text_input('Nickname'); parent=st.text_input('Parent / Guardian'); email=st.text_input('Email'); phone=st.text_input('Phone'); school=st.text_input('School'); grad=st.text_input('Graduation Year'); age=st.selectbox('Age Group',['Youth','Middle School','High School','College','Adult']); pos=st.selectbox('Position',['Guard','Wing','Forward','Post','Combo']); hand=st.selectbox('Shooting Hand',['Right','Left']); height=st.text_input('Height'); level=st.selectbox('Skill Level',['Beginner','Intermediate','Advanced','Elite']); package=st.selectbox('Package Type',['Drop-in','4-session package','8-session package','Monthly']); status=st.selectbox('Status',['Active','Paused','Completed','Prospect']); goal=st.text_area('Goal'); notes=st.text_area('Notes')
            if st.form_submit_button('Create Skill Player') and first: add_skill_player(first,last,nick,parent,email,phone,school,grad,age,pos,hand,height,level,goal,package,status,notes); st.success('Skill player created.'); st.rerun()
with tabs[1]:
    st.subheader('Manual Evaluation'); subject=get_active_subject()
    if not subject: st.info('Select an active player.')
    else:
        st.info(f"{subject['context']} | {subject['name']} | {subject['detail']}"); scores={}; cols=st.columns(2)
        for i, step in enumerate(SHOOTING_STEPS):
            with cols[i%2]: scores[step]=st.slider(step,0,100,75,key=step); st.caption(STEP_TIPS[step])
        shot_context=st.selectbox('Shot Context',['Form shot','Free throw','Catch-and-shoot','Off-dribble']); make_miss=st.selectbox('Make/Miss',['Unknown','Make','Miss']); homework=st.text_area('Homework','100 form shots.'); next_focus=st.text_input('Next Session Focus','Balance and follow-through'); notes=st.text_area('Coach Notes'); package_counted='No'
        if subject['skill_player_id']: package_counted=st.selectbox('Count this session against active package?',['No','Yes'])
        st.metric('Overall',f'{overall(scores)}/100'); st.dataframe(pd.DataFrame([{'Fundamental':k,'Score':v,'Rating':rating(v),'Drill':DRILL_MAP[k]} for k,v in scores.items()]), use_container_width=True, hide_index=True)
        if st.button('Save Manual Session'):
            sid,msg=save_session(subject['player_id'],subject['skill_player_id'],subject['team_id'],session_date,session_type,subject['context'],coach,location,'Manual Coach Scorecard',scores,notes,make_miss,shot_context,homework,next_focus,package_counted); st.success(f'Session saved. ID: {sid}'); st.info(f'Package update status: {msg}')
with tabs[15]:
    st.subheader('Business Center')
    pm = q('SELECT * FROM parent_messages')
    fu = q('SELECT * FROM communication_followups')
    pdf = q('SELECT * FROM generated_pdfs')
    pay = q('SELECT * FROM payments')
    events = q('SELECT * FROM coach_calendar WHERE event_date>=? ORDER BY event_date ASC', (str(date.today()),))
    revenue_collected = float(pay['amount_paid'].sum()) if not pay.empty else 0.0
    outstanding_total = float(pay['balance'].sum()) if not pay.empty else 0.0

    m = st.columns(3)
    m[0].metric('Parent Messages', len(pm))
    m[1].metric('Follow-Ups', len(fu))
    m[2].metric('Generated PDFs', len(pdf))

    m2 = st.columns(3)
    m2[0].metric('Upcoming Events', len(events))
    m2[1].metric('Outstanding Balance', f"${outstanding_total:,.0f}")
    m2[2].metric('Revenue Collected', f"${revenue_collected:,.0f}")

    st.write('### Payment Status Overview')
    if not pay.empty:
        st.bar_chart(pay.groupby('payment_status')['balance'].sum())
    else:
        st.info("No records yet.")

    st.write('### Follow-Up Status Overview')
    if not fu.empty:
        st.bar_chart(fu.groupby('status')['followup_id'].count())
    else:
        st.info("No records yet.")

    st.divider()
    st.subheader('Package Tracker'); sp=q('SELECT * FROM skill_players ORDER BY first_name')
    if sp.empty: st.info('Create/load a skill player first.')
    else:
        opts={f"{int(r.skill_player_id)} — {full_name(r)}":int(r.skill_player_id) for _,r in sp.iterrows()}
        with st.form('pkgform'):
            label=st.selectbox('Skill Player',list(opts.keys())); pname=st.text_input('Package Name','8-Session Shooting Development Package'); purchased=st.number_input('Sessions Purchased',1,value=8); used=st.number_input('Sessions Used',0,value=0); rem=max(0,int(purchased)-int(used)); price=st.number_input('Package Price',0.0,value=600.0,step=25.0); status=st.selectbox('Status',['Active','Completed','Expired','Paused'])
            if st.form_submit_button('Create Package'): execute('INSERT INTO training_packages(skill_player_id,package_name,package_type,sessions_purchased,sessions_used,sessions_remaining,price,start_date,expiration_date,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(opts[label],pname,'Private Training',int(purchased),int(used),rem,float(price),str(date.today()),str(date.today()+timedelta(days=90)),status,'',now())); st.success('Package created.'); st.rerun()
    st.dataframe(q('SELECT * FROM training_packages ORDER BY created_at DESC'), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader('Payment / Invoice Tracker'); sp=q('SELECT * FROM skill_players ORDER BY first_name')
    if not sp.empty:
        opts={f"{int(r.skill_player_id)} — {full_name(r)}":int(r.skill_player_id) for _,r in sp.iterrows()}
        with st.form('payform'):
            label=st.selectbox('Skill Player',list(opts.keys())); inv=st.text_input('Invoice Number',invoice_number()); due=st.number_input('Amount Due',0.0,value=600.0,step=25.0); paid=st.number_input('Amount Paid',0.0,value=0.0,step=25.0); balance=float(due)-float(paid); st.metric('Balance',f'${balance:.2f}'); method=st.selectbox('Method',['Cash','Check','Zelle','Cash App','Venmo','Credit Card','Other']); notes=st.text_area('Notes')
            if st.form_submit_button('Save Payment'):
                status='Paid' if balance<=0 else 'Partial' if (paid>0 and balance>0) else 'Unpaid'; execute('INSERT INTO payments(skill_player_id,team_id,package_id,invoice_number,payment_date,amount_due,amount_paid,balance,payment_method,payment_status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(opts[label],None,None,inv,str(date.today()),float(due),float(paid),balance,method,status,notes,now())); st.success('Payment saved.'); st.rerun()
    st.dataframe(q('SELECT * FROM payments ORDER BY payment_date DESC'), use_container_width=True, hide_index=True)
with tabs[3]:
    st.subheader('Parent Communication'); subject=get_active_subject()
    if not subject or not subject['skill_player_id']: st.info('Select a skill player in Skill Coach Mode.')
    else:
        bal=outstanding_balance(subject['skill_player_id']); mt=st.selectbox('Message Type',['Progress Update','Homework Reminder','Payment Reminder','Schedule Reminder','Report Card Note']); subj,body,sms,recip,contact=generate_parent_message(subject,mt,bal); subject_line=st.text_input('Email Subject',subj); recipient=st.text_input('Recipient Name',recip); rcontact=st.text_input('Recipient Contact',contact); message=st.text_area('Email-Ready Message',body,height=220); sms_body=st.text_area('SMS-Ready Message',sms,height=90); fdate=st.date_input('Follow-Up Date',date.today()+timedelta(days=3)); st.download_button('Download Email Text',message.encode(),f'{safe_filename(subject["name"])}_email.txt','text/plain'); st.download_button('Download SMS Text',sms_body.encode(),f'{safe_filename(subject["name"])}_sms.txt','text/plain')
        if st.button('Save Parent Message + Follow-Up'):
            mid=execute('INSERT INTO parent_messages(skill_player_id,player_id,team_id,message_type,recipient_name,recipient_contact,subject,message_body,sms_body,status,follow_up_date,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(subject['skill_player_id'],subject['player_id'],subject['team_id'],mt,recipient,rcontact,subject_line,message,sms_body,'Drafted',str(fdate),now()))
            execute('INSERT INTO communication_followups(skill_player_id,player_id,team_id,followup_date,followup_type,recipient_name,recipient_contact,subject,message_body,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(subject['skill_player_id'],subject['player_id'],subject['team_id'],str(fdate),mt,recipient,rcontact,subject_line,message,'Pending',f'Created from message {mid}',now())); st.success('Saved.')
with tabs[4]:
    st.subheader('Practice Script Generator'); subject=get_active_subject()
    if not subject: st.info('Select a player.')
    else:
        scores=latest_scores(subject['player_id'],subject['skill_player_id']); default=weakest(scores,1)[0][0] if scores else 'Elbow & Arm Alignment'; focus=st.selectbox('Focus Area',SHOOTING_STEPS,index=SHOOTING_STEPS.index(default)); script=generate_practice_script(subject,focus,'Private Lesson',60,'Medium','Keep form quality high.'); st.markdown(script); st.download_button('Download Markdown',script.encode(),f'{safe_filename(subject["name"])}_script.md','text/markdown')
        if st.button('Generate Practice Script PDF'):
            stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); fname=f'{safe_filename(subject["name"])}_practice_script_{stamp}.pdf'
            final,msg=create_pdf_from_markdown(f'Practice Script — {subject["name"]}',script,REPORT_DIR/fname)
            if final:
                register_pdf('Practice Script',subject['name'],'practice_scripts',None,final)
                st.success(msg); st.download_button('Download Practice Script PDF',open(final,'rb').read(),fname,'application/pdf')
            else: st.error(msg)
with tabs[5]:
    st.subheader('Coach Calendar'); subject=get_active_subject()
    with st.form('calform'):
        edate=st.date_input('Event Date',date.today()); etime=st.text_input('Event Time','6:00 PM'); etype=st.selectbox('Event Type',['Private Lesson','Team Practice','Makeup Session','Parent Meeting','Payment Follow-up','Report Review']); title=st.text_input('Event Title','Training Session'); status=st.selectbox('Status',['Scheduled','Completed','Canceled','Rescheduled'])
        if st.form_submit_button('Save Calendar Event'): execute('INSERT INTO coach_calendar(skill_player_id,team_id,event_date,event_time,event_type,event_title,location,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(subject['skill_player_id'] if subject else None, subject['team_id'] if subject else selected_team_id, str(edate),etime,etype,title,location,status,'',now())); st.success('Saved.'); st.rerun()
    st.dataframe(q('SELECT * FROM coach_calendar ORDER BY event_date ASC,event_time ASC'), use_container_width=True, hide_index=True)
with tabs[6]:
    st.subheader('Parent / Player Report Card'); subject=get_active_subject()
    if not subject: st.info('Select a player.')
    else:
        report=make_parent_report(subject,latest_scores(subject['player_id'],subject['skill_player_id']),sessions_for_subject(subject['player_id'],subject['skill_player_id'])); st.markdown(report); st.download_button('Download Markdown',report.encode(),f'{safe_filename(subject["name"])}_report_card.md','text/markdown')

        st.divider()
        st.write('### Manual vs AI Comparison (Latest)')
        manual_scores = latest_scores_for_mode(subject['player_id'], subject['skill_player_id'], 'manual')
        ai_scores = latest_scores_for_mode(subject['player_id'], subject['skill_player_id'], 'ai')

        if manual_scores is None and ai_scores is None:
            st.info('No Manual or AI sessions found yet for comparison.')
        else:
            c1, c2 = st.columns(2)
            c1.metric('Latest Manual Overall', f"{overall(manual_scores)}/100" if manual_scores else 'N/A')
            c2.metric('Latest AI Overall', f"{overall(ai_scores)}/100" if ai_scores else 'N/A')

            rows = []
            for step in SHOOTING_STEPS:
                m = manual_scores.get(step) if manual_scores else None
                a = ai_scores.get(step) if ai_scores else None
                delta = None if (m is None or a is None) else round(a - m, 1)
                rows.append({
                    'Fundamental': step,
                    'Manual Score': m,
                    'AI Score': a,
                    'AI - Manual': delta,
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if st.button('Generate Report Card PDF'):
            stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); fname=f'{safe_filename(subject["name"])}_report_card_{stamp}.pdf'
            final,msg=create_pdf_from_markdown(f'Player Progress Report — {subject["name"]}',report,REPORT_DIR/fname)
            if final:
                register_pdf('Report Card',subject['name'],'generated_reports',None,final)
                execute('INSERT INTO generated_reports(report_type,report_scope,player_id,skill_player_id,team_id,report_title,report_body,pdf_path,created_at) VALUES(?,?,?,?,?,?,?,?,?)',('Report Card',subject['context'],subject['player_id'],subject['skill_player_id'],subject['team_id'],f'Player Progress Report — {subject["name"]}',report,final,now()))
                st.success(msg); st.download_button('Download Report Card PDF',open(final,'rb').read(),fname,'application/pdf')
            else: st.error(msg)
with tabs[7]:
    st.subheader('Weekly Coach Briefing'); start=st.date_input('Start Date',date.today()-timedelta(days=7)); end=st.date_input('End Date',date.today()); brief=make_weekly_brief(start,end); st.markdown(brief); st.download_button('Download Markdown',brief.encode(),f'weekly_briefing_{start}_to_{end}.md','text/markdown')
    if st.button('Generate Weekly Briefing PDF'):
        stamp=datetime.now().strftime('%H%M%S'); fname=f'weekly_coach_briefing_{start}_to_{end}_{stamp}.pdf'
        final,msg=create_pdf_from_markdown(f'Weekly Coach Briefing — {start} to {end}',brief,REPORT_DIR/fname)
        if final:
            register_pdf('Weekly Briefing','Program','generated_reports',None,final)
            execute('INSERT INTO generated_reports(report_type,report_scope,player_id,skill_player_id,team_id,report_title,report_body,pdf_path,created_at) VALUES(?,?,?,?,?,?,?,?,?)' ,('Weekly Briefing','Program',None,None,None,f'Weekly Coach Briefing {start} to {end}',brief,final,now()))
            st.success(msg); st.download_button('Download Weekly Briefing PDF',open(final,'rb').read(),fname,'application/pdf')
        else: st.error(msg)
with tabs[8]:
    st.subheader('Attendance Tracker'); subject=get_active_subject()
    with st.form('attform'):
        adate=st.date_input('Attendance Date',date.today()); astatus=st.selectbox('Status',['Present','Absent','Late','Excused','Makeup Required']); reason=st.text_input('Reason (if absent/late)'); makeup=st.selectbox('Makeup Required?',['No','Yes']); anotes=st.text_area('Attendance Notes')
        if st.form_submit_button('Log Attendance') and subject:
            execute('INSERT INTO attendance(session_id,player_id,skill_player_id,team_id,attendance_date,attendance_status,reason,makeup_required,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(None,subject['player_id'],subject['skill_player_id'],subject['team_id'],str(adate),astatus,reason,makeup,anotes,now())); st.success('Attendance logged.'); st.rerun()
    if subject:
        if subject['skill_player_id']: att=q('SELECT * FROM attendance WHERE skill_player_id=? ORDER BY attendance_date DESC',(subject['skill_player_id'],))
        elif subject['player_id']: att=q('SELECT * FROM attendance WHERE player_id=? ORDER BY attendance_date DESC',(subject['player_id'],))
        else: att=pd.DataFrame()
        if not att.empty: st.dataframe(att,use_container_width=True,hide_index=True)
    else: st.info('Select a player to log attendance.')
with tabs[9]:
    if operating_mode == 'Team Mode':
        st.subheader('Team Coach Dashboard (V2.6)')
        if selected_team_id is None:
            st.info('Select an active team in the sidebar to view V2.6 team coaching intelligence.')
        else:
            team_row = q('SELECT * FROM teams WHERE team_id=?', (selected_team_id,))
            team_name = str(team_row.iloc[0]['team_name']) if not team_row.empty else f'Team {selected_team_id}'
            team_players = q('SELECT * FROM players WHERE team_id=? ORDER BY first_name,last_name', (selected_team_id,))
            team_sessions = q('SELECT * FROM sessions WHERE team_id=? ORDER BY session_date ASC, session_id ASC', (selected_team_id,))

            if team_players.empty or team_sessions.empty:
                st.warning('Not enough team data yet. Add team players and save sessions to unlock V2.6 insights.')
            else:
                sessions_df = team_sessions.copy()
                sessions_df['overall_score'] = pd.to_numeric(sessions_df['overall_score'], errors='coerce')
                sessions_df = sessions_df.dropna(subset=['overall_score'])
                sessions_df['session_date_dt'] = pd.to_datetime(sessions_df['session_date'], errors='coerce')
                sessions_df = sessions_df.sort_values(['session_date_dt', 'session_id'])

                if sessions_df.empty:
                    st.warning('No valid scored sessions found for this team yet.')
                else:
                    latest_df = sessions_df.groupby('player_id', as_index=False).tail(1).reset_index(drop=True)
                    leaderboard_df = latest_df[['player_id', 'overall_score', 'session_date']].copy()
                    leaderboard_df = leaderboard_df.merge(
                        team_players[['player_id', 'first_name', 'last_name', 'position']],
                        on='player_id',
                        how='left'
                    )
                    leaderboard_df['player_name'] = leaderboard_df['first_name'].fillna('') + ' ' + leaderboard_df['last_name'].fillna('')
                    leaderboard_df['player_name'] = leaderboard_df['player_name'].str.strip()
                    leaderboard_df = leaderboard_df.sort_values('overall_score', ascending=False).reset_index(drop=True)
                    leaderboard_df.insert(0, 'rank', range(1, len(leaderboard_df) + 1))

                    improvement_rows = []
                    for pid, grp in sessions_df.groupby('player_id'):
                        grp = grp.sort_values(['session_date_dt', 'session_id'])
                        first_row = grp.iloc[0]
                        latest_row = grp.iloc[-1]
                        improvement_rows.append({
                            'player_id': pid,
                            'baseline_score': float(first_row['overall_score']),
                            'latest_score': float(latest_row['overall_score']),
                            'score_change': round(float(latest_row['overall_score']) - float(first_row['overall_score']), 2),
                            'session_count': int(len(grp)),
                        })

                    improvement_df = pd.DataFrame(improvement_rows)
                    improvement_df = improvement_df.merge(
                        team_players[['player_id', 'first_name', 'last_name', 'position']],
                        on='player_id',
                        how='left'
                    )
                    improvement_df['player_name'] = improvement_df['first_name'].fillna('') + ' ' + improvement_df['last_name'].fillna('')
                    improvement_df['player_name'] = improvement_df['player_name'].str.strip()
                    improvement_df = improvement_df.sort_values('score_change', ascending=False).reset_index(drop=True)

                    score_cols = [c for c in SHOOTING_STEPS if c in latest_df.columns]
                    weakness_counts = {}
                    if score_cols:
                        for _, row in latest_df.iterrows():
                            row_scores = pd.to_numeric(row[score_cols], errors='coerce')
                            if row_scores.notna().any():
                                weakness = str(row_scores.idxmin())
                                weakness_counts[weakness] = weakness_counts.get(weakness, 0) + 1

                    if weakness_counts:
                        team_weakness = max(weakness_counts.items(), key=lambda x: x[1])[0]
                        team_weakness_count = int(weakness_counts[team_weakness])
                    else:
                        team_weakness = 'Unavailable'
                        team_weakness_count = 0

                    practice_map = {
                        'Feet & Stance': 'Open with base-width and balance stabilization drills.',
                        'Balance & Load': 'Prioritize controlled dip-load and center-of-mass consistency.',
                        'Shot Pocket / Ball Prep': 'Use quick pocket repeat and catch-to-pocket reps.',
                        'Elbow & Arm Alignment': 'Use wall-line and elbow-path shooting drills.',
                        'Set Point & Eyes': 'Emphasize eyes-first target lock before lift.',
                        'Release & Extension': 'Run one-hand release and high-finish extension work.',
                        'Follow-Through & Landing': 'Use hold-the-finish and stick-the-landing blocks.',
                    }
                    practice_recommendation = practice_map.get(team_weakness, 'Use balanced full-form team shooting progression.')

                    highest = leaderboard_df.iloc[0] if not leaderboard_df.empty else None
                    most_improved = improvement_df.iloc[0] if not improvement_df.empty else None

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric('Team Players', int(team_players['player_id'].nunique()))
                    c2.metric('Tracked Sessions', int(len(sessions_df)))
                    c3.metric('Team Avg Overall', f"{sessions_df['overall_score'].mean():.1f}")
                    c4.metric('Highest Score', f"{float(highest['overall_score']):.1f}" if highest is not None else 'N/A')

                    st.write(f"**Team:** {team_name}")
                    if highest is not None:
                        st.write(f"**Highest Current Shooter:** {highest['player_name']} ({float(highest['overall_score']):.1f})")
                    if most_improved is not None:
                        st.write(f"**Most Improved Player:** {most_improved['player_name']} ({float(most_improved['score_change']):+.1f})")
                    st.write(f"**Most Common Team Weakness:** {team_weakness} ({team_weakness_count} players)")
                    st.write(f"**Team Practice Recommendation:** {practice_recommendation}")

                    st.write('### Player Leaderboard')
                    st.dataframe(
                        leaderboard_df[['rank', 'player_name', 'position', 'overall_score', 'session_date']],
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.write('### Most Improved Players')
                    st.dataframe(
                        improvement_df[['player_name', 'position', 'baseline_score', 'latest_score', 'score_change', 'session_count']],
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.write('### Position-Based Comparison')
                    pos_df = leaderboard_df.groupby('position', dropna=False)['overall_score'].mean().reset_index()
                    pos_df['overall_score'] = pos_df['overall_score'].round(1)
                    if pos_df.empty:
                        st.info('No position data available yet for comparison.')
                    else:
                        st.dataframe(pos_df, use_container_width=True, hide_index=True)

                    st.write('### Coach Export Report')
                    coach_report_md = [
                        f"# Team Coach Dashboard Report - {team_name}",
                        f"Date: {date.today()}",
                        f"\n## Team Snapshot\n- Team Players: {int(team_players['player_id'].nunique())}\n- Tracked Sessions: {int(len(sessions_df))}\n- Team Avg Overall: {sessions_df['overall_score'].mean():.1f}",
                        f"\n## Top Insights\n- Highest Current Shooter: {highest['player_name']} ({float(highest['overall_score']):.1f})" if highest is not None else "\n## Top Insights\n- Highest Current Shooter: N/A",
                        f"- Most Improved Player: {most_improved['player_name']} ({float(most_improved['score_change']):+.1f})" if most_improved is not None else "- Most Improved Player: N/A",
                        f"- Common Team Weakness: {team_weakness} ({team_weakness_count} players)",
                        f"- Team Practice Recommendation: {practice_recommendation}",
                    ]
                    coach_report_text = "\n".join(coach_report_md)

                    if st.button('Generate Team Coach PDF (V2.6)'):
                        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        fname = f"team_{safe_filename(team_name)}_v26_coach_report_{stamp}.pdf"
                        final, msg = create_pdf_from_markdown(
                            f"Team Coach Dashboard Report - {team_name}",
                            coach_report_text,
                            REPORT_DIR / fname,
                        )
                        if final:
                            register_pdf('Team Coach Dashboard', team_name, 'generated_reports', None, final)
                            st.success(msg)
                            st.download_button('Download Team Coach PDF', open(final, 'rb').read(), fname, 'application/pdf')
                        else:
                            st.error(msg)

                    st.write('### Parent / Player Summary Report')
                    player_options = {
                        row['player_name']: int(row['player_id'])
                        for _, row in leaderboard_df[['player_id', 'player_name']].drop_duplicates().iterrows()
                        if str(row['player_name']).strip()
                    }
                    if player_options:
                        selected_name = st.selectbox('Select Team Player', list(player_options.keys()), key='team_parent_summary_player')
                        selected_pid = player_options[selected_name]
                        selected_latest = leaderboard_df[leaderboard_df['player_id'] == selected_pid].iloc[0]
                        selected_improvement = improvement_df[improvement_df['player_id'] == selected_pid].iloc[0]
                        parent_summary_text = "\n".join([
                            f"# Parent / Player Summary - {selected_name}",
                            f"Date: {date.today()}",
                            f"\n## Current Progress\n- Latest Overall Score: {float(selected_latest['overall_score']):.1f}\n- Position: {selected_latest.get('position', '')}",
                            f"\n## Improvement\n- Baseline Score: {float(selected_improvement['baseline_score']):.1f}\n- Latest Score: {float(selected_improvement['latest_score']):.1f}\n- Score Change: {float(selected_improvement['score_change']):+.1f}\n- Sessions Tracked: {int(selected_improvement['session_count'])}",
                            "\n## Coach Focus\n- Keep a consistent shooting routine and track shot quality weekly.",
                        ])

                        if st.button('Generate Parent / Player Summary PDF (V2.6)'):
                            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            fname = f"{safe_filename(selected_name)}_v26_parent_summary_{stamp}.pdf"
                            final, msg = create_pdf_from_markdown(
                                f"Parent / Player Summary - {selected_name}",
                                parent_summary_text,
                                REPORT_DIR / fname,
                            )
                            if final:
                                register_pdf('Parent/Player Summary', selected_name, 'generated_reports', None, final)
                                st.success(msg)
                                st.download_button('Download Parent / Player Summary PDF', open(final, 'rb').read(), fname, 'application/pdf')
                            else:
                                st.error(msg)
                    else:
                        st.info('No team player rows available for parent/player summaries.')
    else:
        st.subheader('Skill Client Tracker')
        sp_full=q("""
            SELECT
                sp.skill_player_id,
                sp.first_name,
                sp.last_name,
                sp.nickname,
                sp.parent_guardian,
                COALESCE(sp.contact_email, sp.contact_phone, '') AS contact,
                sp.school,
                sp.age_group,
                sp.skill_level,
                sp.package_type,
                sp.status,
                tp.package_name,
                COALESCE(tp.sessions_remaining, 0) AS sessions_remaining,
                COALESCE((SELECT SUM(py.balance) FROM payments py WHERE py.skill_player_id=sp.skill_player_id), 0) AS balance,
                (
                    SELECT s.overall_score
                    FROM sessions s
                    WHERE s.skill_player_id=sp.skill_player_id
                    ORDER BY s.session_date DESC, s.session_id DESC
                    LIMIT 1
                ) AS latest_overall,
                (
                    SELECT s.next_session_focus
                    FROM sessions s
                    WHERE s.skill_player_id=sp.skill_player_id
                    ORDER BY s.session_date DESC, s.session_id DESC
                    LIMIT 1
                ) AS next_focus
            FROM skill_players sp
            LEFT JOIN training_packages tp ON tp.package_id = (
                SELECT tpx.package_id
                FROM training_packages tpx
                WHERE tpx.skill_player_id=sp.skill_player_id AND tpx.status='Active'
                ORDER BY tpx.expiration_date ASC, tpx.package_id ASC
                LIMIT 1
            )
            ORDER BY sp.first_name, sp.last_name
        """)
        if sp_full.empty: st.info('No skill players found. Create players in Setup.')
        else:
            st.dataframe(sp_full[['skill_player_id','first_name','last_name','contact','sessions_remaining','balance','latest_overall','next_focus','status']],use_container_width=True,hide_index=True)
            c = st.columns(4)
            c[0].metric('Sessions Left (Total)', int(sp_full['sessions_remaining'].fillna(0).sum()))
            c[1].metric('Clients Owing', int((sp_full['balance'].fillna(0) > 0).sum()))
            c[2].metric('Follow-Up Needed', int(((sp_full['balance'].fillna(0) > 0) | (sp_full['sessions_remaining'].fillna(0) <= 0)).sum()))
            c[3].metric('Avg Latest Overall', f"{sp_full['latest_overall'].dropna().mean():.1f}/100" if not sp_full['latest_overall'].dropna().empty else 'N/A')
            st.write('### Follow-Up Priority')
            needs_follow_up = sp_full[(sp_full['balance'].fillna(0) > 0) | (sp_full['sessions_remaining'].fillna(0) <= 0)]
            improving = sp_full[sp_full['latest_overall'].fillna(0) >= 75]
            if not needs_follow_up.empty:
                st.dataframe(needs_follow_up[['first_name','last_name','contact','sessions_remaining','balance','next_focus']],use_container_width=True,hide_index=True)
            else:
                st.info('No immediate follow-up priorities.')
            st.write('### Improving Players')
            if not improving.empty:
                st.dataframe(improving[['first_name','last_name','latest_overall','next_focus']],use_container_width=True,hide_index=True)
            else:
                st.info('No improving trend records yet.')
        st.divider(); st.write('### Outstanding Balances')
        bal=q("""SELECT sp.first_name || ' ' || COALESCE(sp.last_name,'') AS player_name, sp.contact_email, sp.contact_phone, COALESCE(SUM(py.balance),0) AS total_balance, COALESCE(SUM(py.amount_paid),0) AS total_paid FROM skill_players sp LEFT JOIN payments py ON py.skill_player_id=sp.skill_player_id GROUP BY sp.skill_player_id ORDER BY total_balance DESC""")
        if not bal.empty: st.dataframe(bal,use_container_width=True,hide_index=True)

        st.divider()
        st.subheader('V2.7 Drill Library + Practice Plan Builder')
        st.caption('Coach execution system: drill library, weakness-to-drill mapping, custom plans, printable PDFs, and completion tracking.')
        st.caption(f'Drill Library CSV: {V27_DRILL_LIBRARY_CSV} | Practice Plans JSON: {V27_PRACTICE_PLAN_DIR} | Completion History: {V27_PRACTICE_HISTORY_CSV} | Plan PDFs: {V27_PRACTICE_PDF_DIR}')
        st.caption(f'V2.8 Drill Videos: {V28_DRILL_VIDEO_DIR} | Coach Demos: {V28_COACH_DEMO_DIR} | Instruction Cards: {V28_INSTRUCTION_CARD_DIR} | QR Codes: {V28_QR_CODE_DIR} | Homework History CSV: {V28_HOMEWORK_HISTORY_CSV} | Homework Reports: {V28_HOMEWORK_REPORT_DIR}')
        st.caption(f'V2.9 Homework Submissions CSV: {V29_HOMEWORK_SUBMISSIONS_CSV} | Submission Videos: {V29_HOMEWORK_SUBMISSION_VIDEO_DIR} | Parent Progress Reports: {V29_PARENT_PROGRESS_DIR}')

        v27_tabs = st.tabs(['Drill Library', 'Weakness-to-Drill Mapping', 'Practice Plan Builder', 'Completion Tracking', 'V2.8 Video Library', 'Coach Demonstration Mode', 'Player Homework Mode', 'V2.9 Player Portal', 'V2.9 Coach Review Queue', 'V2.9 Progress View'])

        with v27_tabs[0]:
            st.write('### Drill Library')
            filter_focus = st.selectbox('Filter By Fundamental', ['All'] + SHOOTING_STEPS, key='v27_filter_focus')
            filter_level = st.selectbox('Filter By Skill Level', ['All', 'Beginner', 'Intermediate', 'Advanced', 'Elite'], key='v27_filter_level')
            library_df = get_drill_library_df(
                None if filter_focus == 'All' else filter_focus,
                None if filter_level == 'All' else filter_level,
            )
            if library_df.empty:
                st.info('No drills in library yet.')
            else:
                show_cols = ['drill_name', 'target_fundamental', 'description', 'reps', 'coaching_cues', 'skill_levels']
                show_cols = [col for col in show_cols if col in library_df.columns]
                st.dataframe(library_df[show_cols], use_container_width=True, hide_index=True)

            with st.expander('Add Drill To Library'):
                with st.form('v27_add_drill_form'):
                    new_drill_name = st.text_input('Drill Name')
                    new_target = st.selectbox('Target Fundamental', SHOOTING_STEPS, key='v27_new_target')
                    new_skill_levels = st.multiselect('Applicable Skill Levels', ['Beginner', 'Intermediate', 'Advanced', 'Elite'], default=['Beginner', 'Intermediate', 'Advanced', 'Elite'], key='v27_new_skill_levels')
                    new_desc = st.text_area('Description', 'Purpose and setup for this drill.')
                    new_reps = st.text_input('Reps / Volume', '5 spots x 8 makes')
                    new_cues = st.text_area('Coaching Cues', 'Key corrections and cues to enforce.')
                    new_video_url = st.text_input('Demo Video URL (optional)')
                    new_hw = st.text_area('Homework Template (optional)', 'Complete 60 quality reps and track misses.')
                    new_home_plan = st.text_area('At-Home Shooting Plan Template (optional)', '3 sets x 20 reps across 3 spots.')
                    if st.form_submit_button('Save Drill'):
                        if not new_drill_name.strip():
                            st.warning('Drill name is required.')
                        else:
                            execute(
                                'INSERT INTO drills(drill_name,target_fundamental,description,reps,coaching_cues,created_at,skill_levels,demo_video_url,homework_template,at_home_plan_template) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (new_drill_name.strip(), new_target, new_desc, new_reps, new_cues, now(), ','.join(new_skill_levels), new_video_url.strip(), new_hw, new_home_plan),
                            )
                            sync_drill_library_csv()
                            st.success('Drill saved to library.')
                            st.rerun()

        with v27_tabs[1]:
            st.write('### Weakness-to-Drill Mapping')
            default_subject = get_active_subject()
            default_scope = st.selectbox('Weakness Source Scope', ['Individual', 'Team'], key='v27_mapping_scope')
            detected_weakness = SHOOTING_STEPS[0]
            if default_scope == 'Individual':
                skill_player_df = q('SELECT skill_player_id, first_name, last_name, nickname FROM skill_players ORDER BY first_name,last_name')
                if not skill_player_df.empty:
                    skill_opts = {f"{int(r.skill_player_id)} — {full_name(r)}": int(r.skill_player_id) for _, r in skill_player_df.iterrows()}
                    selected_skill_label = st.selectbox('Select Skill Player For Detection', list(skill_opts.keys()), key='v27_mapping_player')
                    detected_weakness = infer_weakness_for_skill_player(skill_opts[selected_skill_label])
            else:
                teams_df = q('SELECT team_id, team_name FROM teams ORDER BY team_name')
                if not teams_df.empty:
                    team_opts = {f"{int(r.team_id)} — {r.team_name}": int(r.team_id) for _, r in teams_df.iterrows()}
                    selected_team_label = st.selectbox('Select Team For Detection', list(team_opts.keys()), key='v27_mapping_team')
                    detected_weakness = infer_weakness_for_team(team_opts[selected_team_label])

            st.info(f"Detected {default_scope} Weakness: {detected_weakness}")
            recommended_df = get_drill_library_df(detected_weakness)
            if recommended_df.empty:
                st.warning('No direct drills found for detected weakness. Using default mapping fallback.')
            else:
                st.write('Recommended Practice Drills')
                st.dataframe(recommended_df[['drill_name', 'reps', 'coaching_cues']], use_container_width=True, hide_index=True)

            mapping_rows = []
            all_drills_df = get_drill_library_df()
            for step in SHOOTING_STEPS:
                step_drills = all_drills_df[all_drills_df['target_fundamental'].astype(str) == step] if not all_drills_df.empty else pd.DataFrame()
                top_drill = step_drills.iloc[0]['drill_name'] if not step_drills.empty else DRILL_MAP.get(step, 'N/A')
                mapping_rows.append({'Weakness': step, 'Mapped Drill': top_drill, 'Library Drill Count': int(len(step_drills))})
            st.dataframe(pd.DataFrame(mapping_rows), use_container_width=True, hide_index=True)

        with v27_tabs[2]:
            st.write('### Practice Plan Builder')
            plan_scope = st.selectbox('Plan Scope', ['Individual', 'Team'], key='v27_plan_scope')
            duration_minutes = st.selectbox('Practice Duration (minutes)', [30, 45, 60, 90, 120], key='v27_duration')
            skill_level_choice = st.selectbox('Skill Level', ['Beginner', 'Intermediate', 'Advanced', 'Elite'], key='v27_skill_level')

            selected_skill_player_id = None
            selected_player_id = None
            selected_team_for_plan = None
            subject_name = ''
            team_name = ''
            detected_focus = SHOOTING_STEPS[0]

            if plan_scope == 'Individual':
                skill_player_df = q('SELECT skill_player_id, first_name, last_name, nickname FROM skill_players ORDER BY first_name,last_name')
                if skill_player_df.empty:
                    st.warning('No skill players available. Create one in Setup.')
                else:
                    player_opts = {
                        f"{int(r.skill_player_id)} — {full_name(r)}": int(r.skill_player_id)
                        for _, r in skill_player_df.iterrows()
                    }
                    selected_label = st.selectbox('Select Skill Player', list(player_opts.keys()), key='v27_individual_player')
                    selected_skill_player_id = player_opts[selected_label]
                    selected_row = skill_player_df[skill_player_df['skill_player_id'] == selected_skill_player_id].iloc[0]
                    subject_name = full_name(selected_row)
                    detected_focus = infer_weakness_for_skill_player(selected_skill_player_id)
            else:
                teams_df = q('SELECT team_id, team_name FROM teams ORDER BY team_name')
                if teams_df.empty:
                    st.warning('No teams available. Create one in Setup.')
                else:
                    team_opts = {f"{int(r.team_id)} — {r.team_name}": int(r.team_id) for _, r in teams_df.iterrows()}
                    selected_team_label = st.selectbox('Select Team', list(team_opts.keys()), key='v27_team_select')
                    selected_team_for_plan = team_opts[selected_team_label]
                    team_name = str(teams_df[teams_df['team_id'] == selected_team_for_plan].iloc[0]['team_name'])
                    detected_focus = infer_weakness_for_team(selected_team_for_plan)

            weakness_mode = st.selectbox('Weakness Selection', ['Auto Detect (V2.5/V2.6)', 'Manual Selection'], key='v27_weakness_mode')
            default_focus = detected_focus if weakness_mode == 'Auto Detect (V2.5/V2.6)' else SHOOTING_STEPS[0]
            focus_area = st.selectbox('Primary Focus Area', SHOOTING_STEPS, index=SHOOTING_STEPS.index(default_focus) if default_focus in SHOOTING_STEPS else 0, key='v27_focus_area')
            st.caption(f"Detected Weakness: {detected_focus}")

            target_drills_df = get_drill_library_df(focus_area, skill_level_choice)
            all_target_names = target_drills_df['drill_name'].dropna().astype(str).tolist() if not target_drills_df.empty else [DRILL_MAP.get(focus_area, 'Form Shooting')]
            default_selected = all_target_names[:min(4, len(all_target_names))]
            selected_drills = st.multiselect('Select Drills For Plan', all_target_names, default=default_selected, key='v27_selected_drills')
            if selected_drills:
                st.write('Recommended Practice')
                for drill_name in selected_drills:
                    st.write(f'- {drill_name}')
            coach_plan_notes = st.text_area('Coach Plan Notes', 'Court setup, teaching emphasis, and pace notes.', key='v27_coach_notes')

            if st.button('Generate V2.7 Practice Plan', key='v27_generate_plan'):
                if plan_scope == 'Individual' and not selected_skill_player_id:
                    st.warning('Select a skill player for an individual plan.')
                elif plan_scope == 'Team' and not selected_team_for_plan:
                    st.warning('Select a team for a team plan.')
                else:
                    selected_drill_rows = []
                    for drill_name in selected_drills if selected_drills else [DRILL_MAP.get(focus_area, 'Form Shooting')]:
                        row_match = target_drills_df[target_drills_df['drill_name'].astype(str) == str(drill_name)] if not target_drills_df.empty else pd.DataFrame()
                        if not row_match.empty:
                            selected_drill_rows.append(row_match.iloc[0])

                    video_link_map = {}
                    qr_link_map = {}
                    for row in selected_drill_rows:
                        drill_name = str(row.get('drill_name', ''))
                        video_ref = str(row.get('demo_video_url', '') or row.get('demo_video_path', '') or '')
                        qr_ref = str(row.get('qr_code_path', '') or '')
                        if drill_name and video_ref:
                            video_link_map[drill_name] = video_ref
                        if drill_name and qr_ref:
                            qr_link_map[drill_name] = qr_ref

                    plan_md = build_v27_practice_plan_md(
                        plan_scope=plan_scope,
                        subject_name=subject_name,
                        team_name=team_name,
                        focus_area=focus_area,
                        duration_minutes=int(duration_minutes),
                        skill_level=skill_level_choice,
                        selected_drills=selected_drills,
                        coach_notes=coach_plan_notes,
                        video_link_map=video_link_map,
                        qr_link_map=qr_link_map,
                    )

                    plan_status = 'Planned'
                    plan_id = execute(
                        'INSERT INTO practice_plans(player_id,skill_player_id,team_id,plan_date,focus_area,duration_minutes,plan_body,homework,next_focus,status,notes,created_at,plan_scope,skill_level) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (
                            selected_player_id,
                            selected_skill_player_id,
                            selected_team_for_plan,
                            str(date.today()),
                            focus_area,
                            int(duration_minutes),
                            plan_md,
                            f'Complete all planned {focus_area} drill blocks.',
                            focus_area,
                            plan_status,
                            coach_plan_notes,
                            now(),
                            plan_scope,
                            skill_level_choice,
                        ),
                    )

                    scope_label = 'Team' if plan_scope == 'Team' else 'Individual'
                    plan_payload = {
                        'plan_id': int(plan_id),
                        'created_at': now(),
                        'plan_scope': plan_scope,
                        'subject_name': subject_name,
                        'team_name': team_name,
                        'focus_area': focus_area,
                        'detected_weakness': detected_focus,
                        'skill_level': skill_level_choice,
                        'duration_minutes': int(duration_minutes),
                        'selected_drills': selected_drills if selected_drills else [DRILL_MAP.get(focus_area, 'Form Shooting')],
                        'coach_notes': coach_plan_notes,
                        'plan_markdown': plan_md,
                    }
                    plan_json_path = save_v27_practice_plan_json(scope_label, focus_area, plan_payload)
                    execute('UPDATE practice_plans SET plan_json_path=? WHERE plan_id=?', (plan_json_path, int(plan_id)))

                    for idx, drill_name in enumerate(selected_drills if selected_drills else [DRILL_MAP.get(focus_area, 'Form Shooting')], start=1):
                        reps_value = ''
                        video_link = ''
                        homework_assignment = f'Complete {focus_area} reps at home and log shot results.'
                        at_home_plan = '3 sets x 20 reps on non-practice days.'
                        if not target_drills_df.empty:
                            row_match = target_drills_df[target_drills_df['drill_name'].astype(str) == str(drill_name)]
                            if not row_match.empty:
                                reps_value = str(row_match.iloc[0].get('reps', ''))
                                video_link = str(row_match.iloc[0].get('demo_video_url', '') or row_match.iloc[0].get('demo_video_path', '') or '')
                                homework_assignment = str(row_match.iloc[0].get('homework_template', homework_assignment) or homework_assignment)
                                at_home_plan = str(row_match.iloc[0].get('at_home_plan_template', at_home_plan) or at_home_plan)
                        execute(
                            'INSERT INTO practice_plan_drills(plan_id,drill_name,target_fundamental,duration_minutes,reps,drill_order,completed,completion_notes,completed_at,created_at,video_link,homework_assignment,at_home_plan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (int(plan_id), str(drill_name), focus_area, max(6, int(int(duration_minutes) / max(1, len(selected_drills) if selected_drills else 1))), reps_value, idx, 0, '', '', now(), video_link, homework_assignment, at_home_plan),
                        )

                    st.success(f'Practice plan generated and saved. Plan ID: {plan_id}')
                    st.caption(f'Plan JSON saved: {plan_json_path}')
                    st.markdown(plan_md)

                    if st.button('Generate Printable Practice Plan PDF', key=f'v27_pdf_{plan_id}'):
                        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        scope_slug = safe_filename('Team' if plan_scope == 'Team' else 'Individual')
                        focus_slug = safe_filename(focus_area)
                        pdf_name = f'{scope_slug}_{focus_slug}_Practice_practice_plan_{stamp}.pdf'
                        final, msg = create_pdf_from_markdown('V2.7 Practice Plan', plan_md, V27_PRACTICE_PDF_DIR / pdf_name)
                        if final:
                            register_pdf('Practice Plan V2.7', subject_name if plan_scope == 'Individual' else team_name, 'practice_plans', int(plan_id), final)
                            execute('UPDATE practice_plans SET plan_pdf_path=?, notes=COALESCE(notes, "") || ? WHERE plan_id=?', (str(final), f' | PDF: {final}', int(plan_id)))
                            st.success(msg)
                            st.download_button('Download Practice Plan PDF', open(final, 'rb').read(), pdf_name, 'application/pdf', key=f'v27_dl_{plan_id}')
                        else:
                            st.error(msg)

            saved_plans_df = q('SELECT plan_id, plan_date, plan_scope, focus_area, skill_level, duration_minutes, status, plan_json_path, plan_pdf_path FROM practice_plans ORDER BY plan_id DESC LIMIT 20')
            st.write('### Saved Plans')
            if saved_plans_df.empty:
                st.info('No saved practice plans yet.')
            else:
                st.dataframe(saved_plans_df, use_container_width=True, hide_index=True)

        with v27_tabs[3]:
            st.write('### Practice Completion Tracking')
            plans_df = q('SELECT * FROM practice_plans ORDER BY plan_id DESC')
            if plans_df.empty:
                st.info('No saved practice plans yet. Generate one in Practice Plan Builder.')
            else:
                plan_display = []
                for _, r in plans_df.head(40).iterrows():
                    scope = str(r.get('plan_scope', ''))
                    label = f"Plan {int(r['plan_id'])} | {r.get('plan_date','')} | {scope or 'Scope N/A'} | {r.get('focus_area','')} | {r.get('status','')}"
                    plan_display.append((label, int(r['plan_id'])))
                selected_plan_label = st.selectbox('Select Plan', [x[0] for x in plan_display], key='v27_plan_tracking_select')
                selected_plan_id = dict(plan_display)[selected_plan_label]

                plan_row = plans_df[plans_df['plan_id'] == selected_plan_id].iloc[0]
                st.write(f"**Plan Status:** {plan_row.get('status','Planned')}")
                st.write(f"**Plan Scope:** {plan_row.get('plan_scope','N/A')} | **Skill Level:** {plan_row.get('skill_level','N/A')} | **Duration:** {plan_row.get('duration_minutes','')} min")
                st.caption(f"Plan JSON: {plan_row.get('plan_json_path','N/A')} | Plan PDF: {plan_row.get('plan_pdf_path','N/A')}")

                plan_drills_df = q('SELECT * FROM practice_plan_drills WHERE plan_id=? ORDER BY drill_order ASC', (int(selected_plan_id),))
                if plan_drills_df.empty:
                    st.info('No drill blocks saved for this plan.')
                else:
                    update_rows = []
                    for _, drow in plan_drills_df.iterrows():
                        key = f"v27_complete_{int(drow['plan_drill_id'])}"
                        checked = st.checkbox(
                            f"{int(drow.get('drill_order', 0))}. {drow.get('drill_name', '')} ({drow.get('duration_minutes', '')} min)",
                            value=bool(int(drow.get('completed', 0) or 0)),
                            key=key,
                        )
                        update_rows.append((int(drow['plan_drill_id']), 1 if checked else 0))

                    completion_note = st.text_area('Completion Notes', key='v27_completion_note')
                    if st.button('Save Completion Status', key='v27_save_completion'):
                        completed_count = 0
                        for drill_id, completed in update_rows:
                            if completed:
                                completed_count += 1
                            execute('UPDATE practice_plan_drills SET completed=?, completion_notes=?, completed_at=? WHERE plan_drill_id=?', (completed, completion_note, now() if completed else '', int(drill_id)))

                        total_count = len(update_rows)
                        plan_status_new = 'Completed' if total_count > 0 and completed_count == total_count else ('In Progress' if completed_count > 0 else 'Planned')
                        execute('UPDATE practice_plans SET status=?, notes=COALESCE(notes, "") || ? WHERE plan_id=?', (plan_status_new, f' | Completion update: {completed_count}/{total_count} drills complete.', int(selected_plan_id)))
                        skill_player_name = ''
                        if pd.notna(plan_row.get('skill_player_id')) and str(plan_row.get('skill_player_id')).strip() not in ('', 'None', 'nan'):
                            skill_df = q('SELECT first_name,last_name,nickname FROM skill_players WHERE skill_player_id=?', (int(plan_row.get('skill_player_id')),))
                            if not skill_df.empty:
                                skill_player_name = full_name(skill_df.iloc[0])

                        team_name_value = ''
                        if pd.notna(plan_row.get('team_id')) and str(plan_row.get('team_id')).strip() not in ('', 'None', 'nan'):
                            team_df = q('SELECT team_name FROM teams WHERE team_id=?', (int(plan_row.get('team_id')),))
                            if not team_df.empty:
                                team_name_value = str(team_df.iloc[0].get('team_name', ''))

                        append_v27_completion_history(
                            plan_id=selected_plan_id,
                            plan_scope=str(plan_row.get('plan_scope', '')),
                            subject_name=skill_player_name,
                            team_name=team_name_value,
                            focus_area=str(plan_row.get('focus_area', '')),
                            skill_level=str(plan_row.get('skill_level', '')),
                            completed_count=completed_count,
                            total_count=total_count,
                            status=plan_status_new,
                            notes=completion_note,
                        )
                        st.success(f'Completion tracking updated. {completed_count}/{total_count} drills complete.')
                        st.rerun()

            st.write('### Completion History Log')
            completion_history_df = load_v27_completion_history()
            if completion_history_df.empty:
                st.info('No completion history records yet.')
            else:
                if 'timestamp' in completion_history_df.columns:
                    completion_history_df = completion_history_df.sort_values(by='timestamp', ascending=False)
                st.dataframe(completion_history_df.head(60), use_container_width=True, hide_index=True)

        with v27_tabs[4]:
            st.write('### V2.8 Drill Video Library')
            drills_df = get_drill_library_df()
            if drills_df.empty:
                st.info('No drills available yet.')
            else:
                drill_opts = {f"{int(r.drill_id)} — {r.drill_name}": int(r.drill_id) for _, r in drills_df.iterrows()}
                selected_drill_label = st.selectbox('Select Drill', list(drill_opts.keys()), key='v28_video_drill')
                selected_drill_id = drill_opts[selected_drill_label]
                drill_row = drills_df[drills_df['drill_id'] == selected_drill_id].iloc[0]

                st.write(f"**Target Fundamental:** {drill_row.get('target_fundamental','')}")
                st.write(f"**Current Demo URL:** {drill_row.get('demo_video_url','') or 'Not set'}")
                st.write(f"**Demo File:** {drill_row.get('demo_video_path','') or 'Not set'}")
                st.write(f"**Coach Demo File:** {drill_row.get('coach_demo_video_path','') or 'Not set'}")
                st.write(f"**Instruction Card:** {drill_row.get('instruction_card_path','') or 'Not set'}")
                st.write(f"**QR Code:** {drill_row.get('qr_code_path','') or 'Not set'}")

                uploaded_demo = st.file_uploader('Upload Drill Demo Video', type=['mp4', 'mov', 'avi', 'mkv'], key='v28_upload_demo_video')
                demo_video_url = st.text_input('Demo Video Link (URL)', value=str(drill_row.get('demo_video_url', '') or ''), key='v28_demo_video_url')

                if st.button('Save Drill Demo Video', key='v28_save_demo_video'):
                    file_path = save_uploaded_media(uploaded_demo, V28_DRILL_VIDEO_DIR, f"drill_demo_{drill_row.get('drill_name','drill')}") if uploaded_demo else str(drill_row.get('demo_video_path', '') or '')
                    execute('UPDATE drills SET demo_video_path=?, demo_video_url=? WHERE drill_id=?', (file_path, demo_video_url.strip(), int(selected_drill_id)))
                    sync_drill_library_csv()
                    st.success('Drill demo video reference saved.')
                    st.rerun()

                if st.button('Generate Instruction Card + QR', key='v28_instruction_card_btn'):
                    card_md = build_instruction_card_markdown(
                        drill_name=str(drill_row.get('drill_name', '')),
                        target_fundamental=str(drill_row.get('target_fundamental', '')),
                        description=str(drill_row.get('description', '')),
                        reps=str(drill_row.get('reps', '')),
                        coaching_cues=str(drill_row.get('coaching_cues', '')),
                        demo_link=str(demo_video_url.strip() or drill_row.get('demo_video_path', '') or ''),
                        coach_demo_link=str(drill_row.get('coach_demo_video_path', '') or ''),
                        homework_text=str(drill_row.get('homework_template', '') or ''),
                        at_home_plan=str(drill_row.get('at_home_plan_template', '') or ''),
                    )
                    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    card_name = f"{safe_filename(str(drill_row.get('drill_name', 'drill')))}_instruction_{stamp}.pdf"
                    card_path, card_msg = create_pdf_from_markdown('Player Instruction Card', card_md, V28_INSTRUCTION_CARD_DIR / card_name)
                    qr_target = str(demo_video_url.strip() or drill_row.get('demo_video_path', '') or '')
                    qr_path, qr_msg = generate_qr_code_image(qr_target, f"{drill_row.get('drill_name', 'drill')}")

                    execute('UPDATE drills SET instruction_card_path=?, qr_code_path=? WHERE drill_id=?', (str(card_path or ''), str(qr_path or ''), int(selected_drill_id)))
                    sync_drill_library_csv()
                    if card_path:
                        st.success(card_msg)
                        st.download_button('Download Instruction Card PDF', open(card_path, 'rb').read(), card_name, 'application/pdf', key=f'v28_card_dl_{selected_drill_id}')
                    else:
                        st.error(card_msg)
                    if qr_path:
                        st.success(qr_msg)
                        st.image(qr_path, caption='Drill QR Code')
                    else:
                        st.warning(qr_msg)

        with v27_tabs[5]:
            st.write('### V2.8 Coach Demonstration Mode')
            drills_df = get_drill_library_df()
            if drills_df.empty:
                st.info('No drills available yet.')
            else:
                drill_opts = {f"{int(r.drill_id)} — {r.drill_name}": int(r.drill_id) for _, r in drills_df.iterrows()}
                selected_drill_label = st.selectbox('Select Drill For Coach Demonstration', list(drill_opts.keys()), key='v28_demo_mode_drill')
                selected_drill_id = drill_opts[selected_drill_label]
                drill_row = drills_df[drills_df['drill_id'] == selected_drill_id].iloc[0]

                coach_demo_upload = st.file_uploader('Upload Coach Demonstration Clip', type=['mp4', 'mov', 'avi', 'mkv'], key='v28_upload_coach_demo')
                coach_demo_notes = st.text_area('Coach Demonstration Notes', value=str(drill_row.get('coach_demo_notes', '') or ''), key='v28_coach_demo_notes')
                homework_template = st.text_area('Player Homework Assignment', value=str(drill_row.get('homework_template', '') or ''), key='v28_homework_template')
                at_home_template = st.text_area('At-Home Shooting Plan', value=str(drill_row.get('at_home_plan_template', '') or ''), key='v28_home_plan_template')

                if st.button('Save Coach Demonstration Setup', key='v28_save_coach_demo'):
                    coach_demo_path = save_uploaded_media(coach_demo_upload, V28_COACH_DEMO_DIR, f"coach_demo_{drill_row.get('drill_name', 'drill')}") if coach_demo_upload else str(drill_row.get('coach_demo_video_path', '') or '')
                    execute(
                        'UPDATE drills SET coach_demo_video_path=?, coach_demo_notes=?, homework_template=?, at_home_plan_template=? WHERE drill_id=?',
                        (coach_demo_path, coach_demo_notes, homework_template, at_home_template, int(selected_drill_id)),
                    )
                    sync_drill_library_csv()
                    st.success('Coach demonstration mode updated for this drill.')
                    st.rerun()

                latest_coach_demo = str(drill_row.get('coach_demo_video_path', '') or '')
                if latest_coach_demo and Path(latest_coach_demo).exists():
                    st.video(latest_coach_demo)

        with v27_tabs[6]:
            st.write('### V2.8 Player Homework Mode')
            plans_df = q('SELECT plan_id, skill_player_id, focus_area, plan_date, status FROM practice_plans ORDER BY plan_id DESC')
            if plans_df.empty:
                st.info('No practice plans available for homework assignment.')
            else:
                plan_opts = {f"Plan {int(r.plan_id)} | {r.plan_date} | {r.focus_area} | {r.status}": int(r.plan_id) for _, r in plans_df.iterrows()}
                selected_plan_label = st.selectbox('Select Plan For Homework', list(plan_opts.keys()), key='v28_homework_plan')
                selected_plan_id = plan_opts[selected_plan_label]
                drill_blocks_df = q('SELECT * FROM practice_plan_drills WHERE plan_id=? ORDER BY drill_order ASC', (int(selected_plan_id),))

                if drill_blocks_df.empty:
                    st.info('No drill blocks found for selected plan.')
                else:
                    available_players_df = q('SELECT skill_player_id, first_name, last_name, nickname FROM skill_players ORDER BY first_name,last_name')
                    if available_players_df.empty:
                        st.warning('No skill players available for assignment.')
                    else:
                        player_opts = {f"{int(r.skill_player_id)} — {full_name(r)}": int(r.skill_player_id) for _, r in available_players_df.iterrows()}
                        selected_player_label = st.selectbox('Select Player', list(player_opts.keys()), key='v28_homework_player')
                        selected_homework_player = player_opts[selected_player_label]
                        due_date = st.date_input('Homework Due Date', date.today() + timedelta(days=5), key='v28_homework_due')

                        for _, drow in drill_blocks_df.iterrows():
                            st.write(f"- {int(drow.get('drill_order', 0))}. {drow.get('drill_name', '')} | Homework: {drow.get('homework_assignment', '')}")

                        reps_goal = st.number_input('Reps Goal', min_value=20, max_value=1000, value=150, step=10, key='v28_reps_goal')
                        makes_goal = st.number_input('Makes Goal', min_value=10, max_value=500, value=80, step=5, key='v28_makes_goal')
                        minutes_goal = st.number_input('Minutes Goal', min_value=10, max_value=240, value=20, step=5, key='v28_minutes_goal')
                        homework_notes = st.text_area('Homework Notes', 'Track misses and send update video clips.', key='v28_homework_notes')

                        if st.button('Assign At-Home Shooting Plan', key='v28_assign_homework'):
                            for _, drow in drill_blocks_df.iterrows():
                                execute(
                                    'INSERT INTO at_home_assignments(plan_id,plan_drill_id,skill_player_id,assigned_date,due_date,reps_goal,makes_goal,minutes_goal,status,notes,completed_at,created_at,assignment_pdf_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                    (
                                        int(selected_plan_id),
                                        int(drow['plan_drill_id']),
                                        int(selected_homework_player),
                                        str(date.today()),
                                        str(due_date),
                                        int(reps_goal),
                                        int(makes_goal),
                                        int(minutes_goal),
                                        'Assigned',
                                        homework_notes,
                                        '',
                                        now(),
                                        '',
                                    ),
                                )
                            sync_v28_homework_assignments_csv()
                            st.success('At-home shooting assignments saved.')
                            st.rerun()

            st.write('### At-Home Assignment Tracker')
            homework_df = q('''
                SELECT a.*, d.drill_name, sp.first_name, sp.last_name, sp.nickname
                FROM at_home_assignments a
                LEFT JOIN practice_plan_drills d ON d.plan_drill_id = a.plan_drill_id
                LEFT JOIN skill_players sp ON sp.skill_player_id = a.skill_player_id
                ORDER BY a.assignment_id DESC
            ''')
            if homework_df.empty:
                st.info('No at-home assignments recorded yet.')
            else:
                if 'player_name' not in homework_df.columns:
                    homework_df['player_name'] = homework_df.apply(lambda r: full_name(r), axis=1)
                st.dataframe(homework_df[['assignment_id', 'player_name', 'drill_name', 'assigned_date', 'due_date', 'reps_goal', 'makes_goal', 'minutes_goal', 'status', 'notes']], use_container_width=True, hide_index=True)

                assignment_opts = {f"Assignment {int(r.assignment_id)} | {r.player_name} | {r.drill_name} | {r.status}": int(r.assignment_id) for _, r in homework_df.iterrows()}
                selected_assignment_label = st.selectbox('Select Assignment To Update', list(assignment_opts.keys()), key='v28_assignment_update')
                selected_assignment_id = assignment_opts[selected_assignment_label]
                selected_assignment_row = homework_df[homework_df['assignment_id'] == selected_assignment_id].iloc[0]
                new_status = st.selectbox('Assignment Status', ['Assigned', 'In Progress', 'Completed'], key='v28_assignment_status')
                update_notes = st.text_area('Progress Notes', key='v28_assignment_notes')
                if st.button('Update Assignment Status', key='v28_update_assignment'):
                    execute(
                        'UPDATE at_home_assignments SET status=?, notes=COALESCE(notes, "") || ?, completed_at=? WHERE assignment_id=?',
                        (new_status, f' | {update_notes}', now() if new_status == 'Completed' else '', int(selected_assignment_id)),
                    )
                    sync_v28_homework_assignments_csv()
                    st.success('Assignment updated.')
                    st.rerun()

                if st.button('Generate Homework Report PDF', key='v28_generate_homework_pdf'):
                    details_df = q(
                        '''
                        SELECT
                            a.assignment_id,
                            a.reps_goal,
                            a.makes_goal,
                            a.status,
                            a.notes,
                            a.assignment_pdf_path,
                            d.drill_name,
                            d.target_fundamental,
                            d.video_link,
                            d.homework_assignment,
                            d.at_home_plan,
                            dr.qr_code_path
                        FROM at_home_assignments a
                        LEFT JOIN practice_plan_drills d ON d.plan_drill_id = a.plan_drill_id
                        LEFT JOIN drills dr ON LOWER(TRIM(dr.drill_name)) = LOWER(TRIM(d.drill_name))
                        WHERE a.assignment_id = ?
                        LIMIT 1
                        ''',
                        (int(selected_assignment_id),),
                    )
                    if details_df.empty:
                        st.error('Could not load assignment details for report generation.')
                    else:
                        details = details_df.iloc[0]
                        player_name = str(selected_assignment_row.get('player_name', '') or 'Player')
                        drill_name = str(details.get('drill_name', '') or '')
                        homework_md = build_homework_report_markdown(
                            player_name=player_name,
                            drill_name=drill_name,
                            target_fundamental=str(details.get('target_fundamental', '') or ''),
                            reps_goal=int(details.get('reps_goal', 0) or 0),
                            makes_goal=int(details.get('makes_goal', 0) or 0),
                            homework_notes=str(details.get('homework_assignment', '') or ''),
                            demo_link=str(details.get('video_link', '') or ''),
                            qr_path=str(details.get('qr_code_path', '') or ''),
                            at_home_plan=str(details.get('at_home_plan', '') or ''),
                            completion_status=str(details.get('status', '') or 'Assigned'),
                            completion_log=str(details.get('notes', '') or ''),
                        )
                        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        pdf_name = f"{safe_filename(player_name)}_homework_{stamp}.pdf"
                        pdf_path, pdf_msg = create_pdf_from_markdown('Player Homework Report', homework_md, V28_HOMEWORK_REPORT_DIR / pdf_name)
                        if pdf_path:
                            execute('UPDATE at_home_assignments SET assignment_pdf_path=? WHERE assignment_id=?', (str(pdf_path), int(selected_assignment_id)))
                            sync_v28_homework_assignments_csv()
                            st.success(pdf_msg)
                            st.caption(f'Homework report saved: {pdf_path}')
                            st.download_button('Download Homework Report PDF', open(pdf_path, 'rb').read(), pdf_name, 'application/pdf', key=f'v28_homework_pdf_dl_{selected_assignment_id}')
                        else:
                            st.error(pdf_msg)

        with v27_tabs[7]:
            st.write('### V2.9 Player Portal + Homework Submission')
            st.markdown(
                """
                <style>
                .v29-card {border: 1px solid #d9dee7; border-radius: 12px; padding: 12px; margin-bottom: 10px; background: #f8fafc;}
                @media (max-width: 768px) {
                    .v29-card {padding: 10px; border-radius: 10px;}
                    div[data-testid="stHorizontalBlock"] {flex-direction: column !important;}
                    div[data-testid="stForm"] button, div[data-testid="stButton"] button {width: 100% !important;}
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            st.caption('Mobile-first player portal: assignment view, upload proof video, and self-report submission.')

            player_df = q('SELECT skill_player_id, first_name, last_name, nickname FROM skill_players ORDER BY first_name,last_name')
            if player_df.empty:
                st.info('No skill players available. Add a player in Setup first.')
            else:
                player_opts = {f"{int(r.skill_player_id)} — {full_name(r)}": int(r.skill_player_id) for _, r in player_df.iterrows()}
                selected_player_label = st.selectbox('Player Dashboard', list(player_opts.keys()), key='v29_player_portal_player')
                selected_player_id = int(player_opts[selected_player_label])

                assignment_view_df = q(
                    '''
                    SELECT
                        a.assignment_id,
                        a.assigned_date,
                        a.due_date,
                        a.reps_goal,
                        a.makes_goal,
                        a.minutes_goal,
                        a.status,
                        a.notes,
                        d.drill_name,
                        d.target_fundamental,
                        d.homework_assignment,
                        d.at_home_plan,
                        d.video_link,
                        dr.qr_code_path
                    FROM at_home_assignments a
                    LEFT JOIN practice_plan_drills d ON d.plan_drill_id = a.plan_drill_id
                    LEFT JOIN drills dr ON LOWER(TRIM(dr.drill_name)) = LOWER(TRIM(d.drill_name))
                    WHERE a.skill_player_id = ?
                    ORDER BY a.assignment_id DESC
                    ''',
                    (selected_player_id,),
                )

                if assignment_view_df.empty:
                    st.info('No homework assignments for this player yet.')
                else:
                    st.write('#### Homework Assignment View')
                    for _, arow in assignment_view_df.head(6).iterrows():
                        st.markdown(
                            f"""
                            <div class='v29-card'>
                            <b>Assignment #{int(arow.get('assignment_id', 0))}</b><br/>
                            Drill: {arow.get('drill_name', '')}<br/>
                            Due: {arow.get('due_date', '')} | Status: {arow.get('status', '')}<br/>
                            Goals: {int(arow.get('reps_goal', 0) or 0)} reps / {int(arow.get('makes_goal', 0) or 0)} makes / {int(arow.get('minutes_goal', 0) or 0)} minutes
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    submit_opts = {
                        f"Assignment {int(r.assignment_id)} | {r.drill_name} | Due {r.due_date} | {r.status}": int(r.assignment_id)
                        for _, r in assignment_view_df.iterrows()
                    }
                    selected_submit_label = st.selectbox('Select Assignment To Submit', list(submit_opts.keys()), key='v29_submit_assignment')
                    selected_submit_assignment_id = int(submit_opts[selected_submit_label])
                    selected_assignment = assignment_view_df[assignment_view_df['assignment_id'] == selected_submit_assignment_id].iloc[0]

                    st.write(f"**Drill:** {selected_assignment.get('drill_name', '')}")
                    st.write(f"**Homework:** {selected_assignment.get('homework_assignment', '') or 'Complete assigned reps with quality mechanics.'}")
                    st.write(f"**At-Home Plan:** {selected_assignment.get('at_home_plan', '') or '3 sets x 20 reps.'}")
                    st.write(f"**Demo Link:** {selected_assignment.get('video_link', '') or 'Not set'}")
                    st.write(f"**QR Reference:** {selected_assignment.get('qr_code_path', '') or 'Not set'}")

                    uploaded_submission_video = st.file_uploader('Upload Homework Completion Video', type=['mp4', 'mov', 'avi', 'mkv'], key='v29_submission_video')
                    submission_date = st.date_input('Submission Date', date.today(), key='v29_submission_date')
                    reps_completed = st.number_input('Player Self-Report: Reps Completed', min_value=0, max_value=2000, value=int(selected_assignment.get('reps_goal', 0) or 0), step=10, key='v29_reps_completed')
                    makes_completed = st.number_input('Player Self-Report: Makes Completed', min_value=0, max_value=1200, value=int(selected_assignment.get('makes_goal', 0) or 0), step=5, key='v29_makes_completed')
                    minutes_practiced = st.number_input('Player Self-Report: Minutes Practiced', min_value=0, max_value=300, value=int(selected_assignment.get('minutes_goal', 20) or 20), step=5, key='v29_minutes_practiced')
                    confidence_score = st.slider('Confidence Score (1-10)', min_value=1, max_value=10, value=8, key='v29_confidence_score')
                    difficulty_score = st.slider('Difficulty Score (1-10)', min_value=1, max_value=10, value=6, key='v29_difficulty_score')
                    player_notes = st.text_area('Player Notes', 'What felt strong? What still needs work?', key='v29_player_notes')

                    if st.button('Submit Homework To Coach Review Queue', key='v29_submit_homework_btn'):
                        if uploaded_submission_video is None:
                            st.warning('Upload a completion video before submitting.')
                        else:
                            player_slug = safe_filename(str(selected_player_label).split('—', 1)[-1].strip().replace(' ', '_'))
                            submission_video_path = save_uploaded_media(uploaded_submission_video, V29_HOMEWORK_SUBMISSION_VIDEO_DIR, f"{player_slug}_homework_video")
                            effort_score, self_report_score, auto_score, score_label = calculate_homework_completion_score(
                                reps_goal=int(selected_assignment.get('reps_goal', 0) or 0),
                                makes_goal=int(selected_assignment.get('makes_goal', 0) or 0),
                                minutes_goal=int(selected_assignment.get('minutes_goal', 0) or 20),
                                reps_completed=int(reps_completed),
                                makes_completed=int(makes_completed),
                                minutes_practiced=int(minutes_practiced),
                                confidence_score=int(confidence_score),
                            )
                            execute(
                                'INSERT INTO homework_submissions(assignment_id,skill_player_id,submission_date,submission_video_path,reps_completed,makes_completed,minutes_practiced,confidence_score,difficulty_score,self_rating,player_notes,coach_status,coach_feedback,effort_score,self_report_score,completion_score,score_label,created_at,reviewed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                (
                                    int(selected_submit_assignment_id),
                                    int(selected_player_id),
                                    str(submission_date),
                                    submission_video_path,
                                    int(reps_completed),
                                    int(makes_completed),
                                    int(minutes_practiced),
                                    int(confidence_score),
                                    int(difficulty_score),
                                    int(max(1, min(5, round(int(confidence_score) / 2)))),
                                    player_notes,
                                    'Pending Review',
                                    '',
                                    float(effort_score),
                                    float(self_report_score),
                                    float(auto_score),
                                    score_label,
                                    now(),
                                    '',
                                ),
                            )
                            execute('UPDATE at_home_assignments SET status=?, notes=COALESCE(notes, "") || ? WHERE assignment_id=?', ('Submitted', f' | Submitted on {submission_date}', int(selected_submit_assignment_id)))
                            sync_v28_homework_assignments_csv()
                            sync_v29_homework_submissions_csv()
                            st.success(f'Homework submitted. Completion score: {auto_score}/100 ({score_label})')
                            st.rerun()

                submission_history_df = q(
                    '''
                    SELECT submission_id, assignment_id, submission_date, reps_completed, makes_completed, minutes_practiced, confidence_score, difficulty_score, coach_status, completion_score, score_label
                    FROM homework_submissions
                    WHERE skill_player_id = ?
                    ORDER BY submission_id DESC
                    ''',
                    (selected_player_id,),
                )
                st.write('#### Submission History')
                if submission_history_df.empty:
                    st.info('No homework submissions yet for this player.')
                else:
                    st.dataframe(submission_history_df, use_container_width=True, hide_index=True)

        with v27_tabs[8]:
            st.write('### V2.9 Coach Review Queue')
            review_df = q(
                '''
                SELECT
                    hs.submission_id,
                    hs.assignment_id,
                    hs.submission_date,
                    hs.submission_video_path,
                    hs.reps_completed,
                    hs.makes_completed,
                    hs.minutes_practiced,
                    hs.confidence_score,
                    hs.difficulty_score,
                    hs.self_rating,
                    hs.player_notes,
                    hs.coach_status,
                    hs.coach_feedback,
                    hs.effort_score,
                    hs.self_report_score,
                    hs.completion_score,
                    hs.score_label,
                    a.status AS assignment_status,
                    d.drill_name,
                    sp.first_name,
                    sp.last_name,
                    sp.nickname
                FROM homework_submissions hs
                LEFT JOIN at_home_assignments a ON a.assignment_id = hs.assignment_id
                LEFT JOIN practice_plan_drills d ON d.plan_drill_id = a.plan_drill_id
                LEFT JOIN skill_players sp ON sp.skill_player_id = hs.skill_player_id
                ORDER BY hs.submission_id DESC
                '''
            )
            if review_df.empty:
                st.info('No submissions in the coach review queue yet.')
            else:
                review_df['player_name'] = review_df.apply(lambda r: full_name(r), axis=1)
                st.dataframe(review_df[['submission_id', 'assignment_id', 'player_name', 'drill_name', 'submission_date', 'coach_status', 'completion_score', 'assignment_status']], use_container_width=True, hide_index=True)

                review_opts = {f"Submission {int(r.submission_id)} | {r.player_name} | {r.drill_name} | {r.coach_status}": int(r.submission_id) for _, r in review_df.iterrows()}
                selected_review_label = st.selectbox('Select Submission To Review', list(review_opts.keys()), key='v29_review_select')
                selected_submission_id = int(review_opts[selected_review_label])
                selected_review_row = review_df[review_df['submission_id'] == selected_submission_id].iloc[0]

                st.write(f"**Player:** {selected_review_row.get('player_name', '')}")
                st.write(f"**Drill:** {selected_review_row.get('drill_name', '')}")
                st.write(f"**Submitted Video:** {selected_review_row.get('submission_video_path', '') or 'Not set'}")
                st.write(f"**Player Confidence/Difficulty:** {int(selected_review_row.get('confidence_score', 0) or 0)}/10, {int(selected_review_row.get('difficulty_score', 0) or 0)}/10")
                if str(selected_review_row.get('submission_video_path', '') or '').strip() and Path(str(selected_review_row.get('submission_video_path', ''))).exists():
                    st.video(str(selected_review_row.get('submission_video_path', '')))

                coach_status_choice = st.selectbox('Coach Review Status', ['Pending Review', 'Needs Revision', 'Reviewed', 'Approved'], index=0 if str(selected_review_row.get('coach_status', '')) not in ['Pending Review', 'Needs Revision', 'Reviewed', 'Approved'] else ['Pending Review', 'Needs Revision', 'Reviewed', 'Approved'].index(str(selected_review_row.get('coach_status', ''))), key='v29_coach_status')
                coach_feedback = st.text_area('Coach Feedback', value=str(selected_review_row.get('coach_feedback', '') or ''), key='v29_coach_feedback')
                reviewed_score = st.number_input('Coach Completion Score (0-100)', min_value=0.0, max_value=100.0, value=float(selected_review_row.get('completion_score', 0.0) or 0.0), step=1.0, key='v29_reviewed_score')

                if st.button('Save Coach Review', key='v29_save_review'):
                    reviewed_label = homework_score_label(float(reviewed_score))
                    execute(
                        'UPDATE homework_submissions SET coach_status=?, coach_feedback=?, completion_score=?, score_label=?, reviewed_at=? WHERE submission_id=?',
                        (coach_status_choice, coach_feedback, float(reviewed_score), reviewed_label, now(), int(selected_submission_id)),
                    )
                    assignment_status = 'Submitted'
                    completed_at_value = ''
                    if coach_status_choice in ('Reviewed', 'Approved'):
                        assignment_status = 'Completed' if float(reviewed_score) >= 70.0 else 'In Progress'
                        completed_at_value = now() if assignment_status == 'Completed' else ''
                    elif coach_status_choice == 'Needs Revision':
                        assignment_status = 'In Progress'
                    execute('UPDATE at_home_assignments SET status=?, completed_at=?, notes=COALESCE(notes, "") || ? WHERE assignment_id=?', (assignment_status, completed_at_value, f' | Coach review: {coach_status_choice} ({reviewed_score}/100)', int(selected_review_row.get('assignment_id', 0) or 0)))
                    sync_v28_homework_assignments_csv()
                    sync_v29_homework_submissions_csv()
                    st.success('Coach review saved and assignment status updated.')
                    st.rerun()

        with v27_tabs[9]:
            st.write('### V2.9 Parent / Player Progress View')
            progress_players_df = q('SELECT skill_player_id, first_name, last_name, nickname FROM skill_players ORDER BY first_name,last_name')
            if progress_players_df.empty:
                st.info('No skill players available yet.')
            else:
                progress_player_opts = {f"{int(r.skill_player_id)} — {full_name(r)}": int(r.skill_player_id) for _, r in progress_players_df.iterrows()}
                selected_progress_player_label = st.selectbox('Select Player Progress Dashboard', list(progress_player_opts.keys()), key='v29_progress_player')
                selected_progress_player_id = int(progress_player_opts[selected_progress_player_label])

                progress_df = q(
                    '''
                    SELECT
                        a.assignment_id,
                        a.assigned_date,
                        a.due_date,
                        a.status,
                        d.drill_name,
                        hs.submission_date,
                        hs.minutes_practiced,
                        hs.completion_score,
                        hs.score_label,
                        hs.coach_status,
                        hs.coach_feedback
                    FROM at_home_assignments a
                    LEFT JOIN practice_plan_drills d ON d.plan_drill_id = a.plan_drill_id
                    LEFT JOIN homework_submissions hs
                        ON hs.submission_id = (
                            SELECT MAX(h2.submission_id)
                            FROM homework_submissions h2
                            WHERE h2.assignment_id = a.assignment_id
                        )
                    WHERE a.skill_player_id = ?
                    ORDER BY a.assignment_id DESC
                    ''',
                    (selected_progress_player_id,),
                )

                if progress_df.empty:
                    st.info('No assignment progress recorded yet for this player.')
                else:
                    latest_session_df = q('SELECT overall_score FROM sessions WHERE skill_player_id=? ORDER BY session_date DESC, session_id DESC LIMIT 1', (selected_progress_player_id,))
                    latest_shot_score = f"{float(latest_session_df.iloc[0].get('overall_score', 0.0) or 0.0):.1f}/100" if not latest_session_df.empty else 'N/A'
                    total_assignments = int(len(progress_df))
                    submitted_count = int(progress_df['submission_date'].fillna('').astype(str).str.len().gt(0).sum())
                    reviewed_count = int(progress_df['coach_status'].fillna('').astype(str).isin(['Reviewed', 'Approved']).sum())
                    avg_score = float(progress_df['completion_score'].fillna(0.0).mean()) if total_assignments else 0.0
                    minutes_total = int(progress_df['minutes_practiced'].fillna(0).astype(int).sum())

                    on_time_count = 0
                    timed_rows = 0
                    for _, prow in progress_df.iterrows():
                        sub_text = str(prow.get('submission_date', '') or '').strip()
                        due_text = str(prow.get('due_date', '') or '').strip()
                        if sub_text and due_text:
                            timed_rows += 1
                            try:
                                if datetime.fromisoformat(sub_text).date() <= datetime.fromisoformat(due_text).date():
                                    on_time_count += 1
                            except Exception:
                                pass
                    on_time_rate = round((on_time_count / timed_rows) * 100.0, 1) if timed_rows else 0.0

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric('Assignments', total_assignments)
                    c2.metric('Submitted', submitted_count)
                    c3.metric('Reviewed', reviewed_count)
                    c4.metric('Avg Score', f'{avg_score:.1f}/100')
                    c5, c6, c7 = st.columns(3)
                    c5.metric('Total Practice Minutes', minutes_total)
                    c6.metric('On-Time Submissions', f'{on_time_rate}%')
                    c7.metric('Latest Shot Intelligence', latest_shot_score)

                    chart_df = progress_df.copy()
                    chart_df['submission_date'] = pd.to_datetime(chart_df['submission_date'], errors='coerce')
                    chart_df = chart_df.dropna(subset=['submission_date'])
                    chart_df['completion_score'] = pd.to_numeric(chart_df['completion_score'], errors='coerce').fillna(0.0)
                    if not chart_df.empty:
                        chart_df = chart_df.sort_values('submission_date')
                        st.line_chart(chart_df.set_index('submission_date')['completion_score'])
                    st.dataframe(progress_df[['assignment_id', 'drill_name', 'assigned_date', 'due_date', 'submission_date', 'minutes_practiced', 'completion_score', 'score_label', 'coach_status', 'status']], use_container_width=True, hide_index=True)

                    latest_feedback = ''
                    latest_review_status = 'N/A'
                    reviewed_rows = progress_df[progress_df['coach_status'].fillna('').astype(str).str.len().gt(0)]
                    if not reviewed_rows.empty:
                        latest_row = reviewed_rows.iloc[0]
                        latest_feedback = str(latest_row.get('coach_feedback', '') or '')
                        latest_review_status = str(latest_row.get('coach_status', '') or 'N/A')

                    if st.button('Export Parent Progress PDF', key='v29_export_parent_progress_pdf'):
                        parent_md = build_parent_progress_markdown(
                            player_name=str(selected_progress_player_label).split('—', 1)[-1].strip(),
                            latest_shot_score=latest_shot_score,
                            assignments_total=total_assignments,
                            submitted_total=submitted_count,
                            reviewed_total=reviewed_count,
                            on_time_rate=on_time_rate,
                            avg_score=f'{avg_score:.1f}/100',
                            latest_review_status=latest_review_status,
                            latest_feedback=latest_feedback,
                        )
                        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        player_slug = safe_filename(str(selected_progress_player_label).split('—', 1)[-1].strip().replace(' ', '_'))
                        pdf_name = f'{player_slug}_parent_progress_{stamp}.pdf'
                        pdf_path, pdf_msg = create_pdf_from_markdown('Parent Progress Report', parent_md, V29_PARENT_PROGRESS_DIR / pdf_name)
                        if pdf_path:
                            st.success(pdf_msg)
                            st.caption(f'Parent progress report saved: {pdf_path}')
                            st.download_button('Download Parent Progress PDF', open(pdf_path, 'rb').read(), pdf_name, 'application/pdf', key=f'v29_parent_progress_dl_{selected_progress_player_id}')
                        else:
                            st.error(pdf_msg)
with tabs[10]:
    st.subheader('Practice / Homework Plans'); subject=get_active_subject()
    if not subject: st.info('Select a player to view practice and homework plans.')
    else:
        ss=sessions_for_subject(subject['player_id'],subject['skill_player_id'])
        if ss.empty: st.info('No sessions found. Save a session with homework in Manual Evaluation first.')
        else:
            hw=ss[ss['homework_assigned'].notna()&(ss['homework_assigned']!='')]
            if hw.empty: st.info('No homework plans recorded yet.')
            else:
                st.write(f"### Homework Plans for {subject['name']}")
                for _,row in hw.iloc[::-1].iterrows():
                    with st.expander(f"{row['session_date']} — {row['session_context']} — Score: {row['overall_score']}/100"):
                        st.write(f"**Homework:** {row['homework_assigned']}")
                        if row.get('next_session_focus'): st.write(f"**Next Focus:** {row['next_session_focus']}")
                        if row.get('coach_notes'): st.write(f"**Coach Notes:** {row['coach_notes']}")
        st.divider(); st.write('### Saved Practice Scripts')
        if subject['skill_player_id']: scripts=q('SELECT * FROM practice_scripts WHERE skill_player_id=? ORDER BY script_date DESC',(subject['skill_player_id'],))
        elif subject['team_id']: scripts=q('SELECT * FROM practice_scripts WHERE team_id=? ORDER BY script_date DESC',(subject['team_id'],))
        else: scripts=pd.DataFrame()
        if scripts.empty: st.info('No practice scripts saved. Generate one in Practice Script Generator.')
        else: st.dataframe(scripts,use_container_width=True,hide_index=True)
with tabs[11]:
    st.subheader('PDF Export Center')
    if REPORTLAB_AVAILABLE: st.success('✅ PDF engine (ReportLab) is available.')
    else: st.error('❌ ReportLab not installed. Run: pip install -r requirements.txt')
    st.divider()
    st.write('### Generate Invoice PDF')
    pay=q('SELECT * FROM payments ORDER BY payment_date DESC')
    if pay.empty:
        st.info('No payments found. Add a payment in the Payment / Invoice Tracker tab.')
    else:
        opts={f"{int(r.payment_id)} — {r.invoice_number} — ${float(r.balance or 0):.2f} balance":int(r.payment_id) for _,r in pay.iterrows()}
        pid=opts[st.selectbox('Select Payment / Invoice',list(opts.keys()))]
        inv=make_invoice_text(pid)
        st.markdown(inv)
        if st.button('Generate Invoice PDF'):
            row=pay[pay['payment_id']==pid].iloc[0]
            stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); fname=f'{safe_filename(row["invoice_number"])}_invoice_{stamp}.pdf'
            final,msg=create_pdf_from_markdown(f'Invoice {row["invoice_number"]}',inv,REPORT_DIR/fname)
            if final:
                register_pdf('Invoice',str(row.get('invoice_number','')),'payments',int(pid),final)
                st.success(msg); st.download_button('Download Invoice PDF',open(final,'rb').read(),fname,'application/pdf')
            else: st.error(msg)
    st.divider()
    st.write('### Generated PDF Registry')
    pdf_log=q('SELECT pdf_type,subject_name,source_table,source_id,file_path,created_at FROM generated_pdfs ORDER BY created_at DESC')
    if pdf_log.empty: st.info('No PDFs generated yet.')
    else: st.dataframe(pdf_log,use_container_width=True,hide_index=True)
with tabs[12]:
    st.subheader('Backup / Export Bundle')
    st.write('Creates a ZIP file containing the database, all CSV exports, and all generated PDFs.')
    table_count = len(export_queries())
    pdf_count_cur = len(list(REPORT_DIR.glob('*.pdf')))
    db_exists = DB_PATH.exists()
    c1, c2, c3 = st.columns(3)
    c1.metric('Database', '✅ Found' if db_exists else '⚠️ Not found')
    c2.metric('Export Tables', table_count)
    c3.metric('Generated PDFs', pdf_count_cur)
    st.divider()
    if st.button('Create Backup ZIP', type='primary'):
        try:
            path, pdf_bundled = create_backup_zip()
            st.success(f'Backup created: {path.name}')
            st.info(f'Bundle contains: database + {table_count} CSV exports + {pdf_bundled} PDF(s)')
            st.download_button('Download Backup ZIP', open(path, 'rb').read(), path.name, 'application/zip')
        except Exception as e:
            st.error(f'Backup failed: {e}')
    st.divider()
    st.write('### Backup History')
    history = q('SELECT * FROM system_backups ORDER BY created_at DESC')
    if history.empty: st.info('No backups created yet.')
    else: st.dataframe(history, use_container_width=True, hide_index=True)
with tabs[13]:
    st.subheader('Reports'); report_map=export_queries(); report=st.selectbox('Report',list(report_map.keys())); df=q(report_map[report]); st.dataframe(df,use_container_width=True,hide_index=True); st.download_button(f'Download {report} CSV',df.to_csv(index=False).encode(),f'{report.lower().replace(" ","_")}_export.csv','text/csv')
with tabs[14]:
    st.subheader('Communication Follow-Ups'); subject=get_active_subject()
    st.write('### Create Manual Follow-Up')
    with st.form('followup_form'):
        fu_date=st.date_input('Follow-Up Date',date.today()+timedelta(days=3))
        fu_type=st.selectbox('Follow-Up Type',['Payment Reminder','Homework Reminder','Schedule Reminder','Report Review','Parent Meeting','Other'])
        fu_recipient=st.text_input('Recipient Name', subject['raw'].get('parent_guardian','') if subject and subject.get('skill_player_id') else '')
        fu_contact=st.text_input('Recipient Contact', subject['raw'].get('contact_email','') or subject['raw'].get('contact_phone','') if subject and subject.get('skill_player_id') else '')
        fu_subject=st.text_input('Subject', f'{fu_type} — {subject["name"]}' if subject else '')
        fu_body=st.text_area('Message / Notes', height=120)
        fu_status=st.selectbox('Status',['Pending','Completed','Canceled'])
        if st.form_submit_button('Save Follow-Up'):
            execute('INSERT INTO communication_followups(skill_player_id,player_id,team_id,followup_date,followup_type,recipient_name,recipient_contact,subject,message_body,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (subject['skill_player_id'] if subject else None, subject['player_id'] if subject else None, subject['team_id'] if subject else None,
                     str(fu_date), fu_type, fu_recipient, fu_contact, fu_subject, fu_body, fu_status, 'Manual entry', now()))
            st.success('Follow-up saved.'); st.rerun()
    st.divider()
    st.write('### Follow-Up Queue')
    fu_all=q('SELECT * FROM communication_followups ORDER BY followup_date ASC')
    if fu_all.empty: st.info('No follow-ups recorded yet.')
    else:
        pending=fu_all[fu_all['status']=='Pending']; other=fu_all[fu_all['status']!='Pending']
        if not pending.empty:
            st.write(f'**Pending ({len(pending)})**')
            st.dataframe(pending[['followup_date','followup_type','recipient_name','recipient_contact','subject','status','notes']],use_container_width=True,hide_index=True)
        if not other.empty:
            with st.expander(f'Completed / Canceled ({len(other)})'):
                st.dataframe(other[['followup_date','followup_type','recipient_name','subject','status','notes']],use_container_width=True,hide_index=True)
with tabs[2]:
    st.subheader('AI Shooting Evaluation (V1.6.1 Restoration)')
    subject = get_active_subject()
    ai_runtime_available = MP_POSE_AVAILABLE or MP_TASKS_POSE_AVAILABLE
    if not CV_AVAILABLE:
        st.error('AI dependencies are missing. Install: opencv-python, mediapipe, numpy')
    elif not ai_runtime_available:
        st.error('Mediapipe Pose runtime is not available in this Python environment.')
    elif not subject:
        st.info('Select an active player first.')
    else:
        st.info(f"{subject['context']} | {subject['name']} | {subject['detail']}")
        dominant_hand = st.selectbox('Dominant Shooting Hand', ['Right', 'Left'], key='ai_dom_hand')
        shot_context_ai = st.selectbox('Shot Context', ['Form shot', 'Free throw', 'Catch-and-shoot', 'Off-dribble'], key='ai_shot_context')
        uploaded_media = st.file_uploader(
            'Upload Shooting Media (Video: MP4/MOV/AVI or Image: JPG/JPEG/PNG/WEBP)',
            type=['mp4', 'mov', 'avi', 'jpg', 'jpeg', 'png', 'webp'],
            key='ai_media_upload'
        )

        if uploaded_media and st.button('Run AI Seven-Step Evaluation', key='ai_run_eval'):
            suffix = (Path(uploaded_media.name).suffix or '').lower()
            tmp_cleanup = []

            if suffix in ['.jpg', '.jpeg', '.png', '.webp']:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_img:
                    tmp_img.write(uploaded_media.getbuffer())
                    tmp_img_path = tmp_img.name
                tmp_cleanup.append(tmp_img_path)

                img = cv2.imread(tmp_img_path)
                if img is None:
                    st.error('Unable to read uploaded image. Please try a different file.')
                    for p in tmp_cleanup:
                        try:
                            os.remove(p)
                        except Exception:
                            pass
                    st.stop()

                height, width = img.shape[:2]
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_vid:
                    tmp_path = tmp_vid.name
                tmp_cleanup.append(tmp_path)

                writer = cv2.VideoWriter(tmp_path, cv2.VideoWriter_fourcc(*'mp4v'), 15.0, (width, height))
                for _ in range(30):
                    writer.write(img)
                writer.release()
            else:
                suffix = suffix if suffix in ['.mp4', '.mov', '.avi'] else '.mp4'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_media.getbuffer())
                    tmp_path = tmp.name
                tmp_cleanup.append(tmp_path)

            with st.spinner('Analyzing shooting motion with pose estimation...'):
                ai_report = run_ai_seven_step_evaluation(tmp_path, dominant_hand)

            for p in tmp_cleanup:
                try:
                    os.remove(p)
                except Exception:
                    pass

            if 'error' in ai_report:
                st.error(ai_report['error'])
            else:
                st.metric('Overall AI Score', f"{ai_report['overall_score']}/100")
                st.caption(f"Classification: {ai_report['classification']}")
                table_df = pd.DataFrame([
                    {
                        'Category': category,
                        'Score': f"{score}/10",
                        'AI Feedback': ai_report['feedback'][category],
                    }
                    for category, score in ai_report['scores'].items()
                ])
                st.dataframe(table_df, use_container_width=True, hide_index=True)

                weakest_step = min(ai_report['scores'].items(), key=lambda kv: kv[1])[0]
                st.warning(f"Fix this first: {weakest_step}")

                if st.button('Save AI Session', key='ai_save_session'):
                    ai_to_internal = {
                        'Feet & Stance': round(ai_report['scores']['Stance and Balance'] * 10, 1),
                        'Balance & Load': round(ai_report['scores']['Hand Placement'] * 10, 1),
                        'Shot Pocket / Ball Prep': round(ai_report['scores']['Shot Pocket'] * 10, 1),
                        'Elbow & Arm Alignment': round(ai_report['scores']['Elbow Alignment'] * 10, 1),
                        'Set Point & Eyes': round(ai_report['scores']['Eyes on Target'] * 10, 1),
                        'Release & Extension': round(ai_report['scores']['Release and Follow Through'] * 10, 1),
                        'Follow-Through & Landing': round(ai_report['scores']['Hold and Evaluate'] * 10, 1),
                    }
                    notes = f"AI video evaluation. Classification: {ai_report['classification']}."
                    sid, msg = save_session(
                        subject['player_id'],
                        subject['skill_player_id'],
                        subject['team_id'],
                        session_date,
                        session_type,
                        subject['context'],
                        coach,
                        location,
                        'AI Pose Scorecard',
                        ai_to_internal,
                        notes,
                        'Unknown',
                        shot_context_ai,
                        'Review AI feedback and complete 100 corrective reps.',
                        weakest_step,
                        'No',
                    )
                    st.success(f'Session saved. ID: {sid}')
                    st.info(f'Package update status: {msg}')

