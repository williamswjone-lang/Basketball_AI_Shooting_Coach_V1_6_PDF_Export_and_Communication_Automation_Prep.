from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pandas as pd
import streamlit as st

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
CHALLENGE_DIR = BASE_DIR / "data" / "challenges"
VIDEO_DIR = CHALLENGE_DIR / "videos"
CHALLENGES_CSV = CHALLENGE_DIR / "challenges.csv"
ENROLLMENTS_CSV = CHALLENGE_DIR / "enrollments.csv"
ATTEMPTS_CSV = CHALLENGE_DIR / "attempts.csv"
SCORING_RULES_CSV = CHALLENGE_DIR / "scoring_rules.csv"
WALLETS_CSV = CHALLENGE_DIR / "player_point_wallets.csv"
RANKING_HISTORY_CSV = CHALLENGE_DIR / "ranking_history_snapshots.csv"
REWARD_CATALOG_CSV = CHALLENGE_DIR / "reward_catalog.csv"
SPONSOR_INVENTORY_CSV = CHALLENGE_DIR / "sponsor_reward_inventory.csv"
REWARD_REQUESTS_CSV = CHALLENGE_DIR / "reward_redemption_requests.csv"
CERTIFICATES_CSV = CHALLENGE_DIR / "digital_reward_certificates.csv"
LEGACY_SUBMISSIONS_CSV = CHALLENGE_DIR / "submissions.csv"

CHALLENGE_COLUMNS = [
    "challenge_id",
    "title",
    "description",
    "division",
    "difficulty",
    "target_reps",
    "target_days",
    "status",
    "created_at",
]

ENROLLMENT_COLUMNS = [
    "enrollment_id",
    "challenge_id",
    "challenge_title",
    "player_name",
    "division",
    "age_group",
    "team_name",
    "enrolled_at",
]

ATTEMPT_COLUMNS = [
    "attempt_id",
    "challenge_id",
    "challenge_title",
    "player_name",
    "division",
    "age_group",
    "team_name",
    "submitted_score",
    "final_verified_score",
    "raw_score",
    "effort_score",
    "consistency_score",
    "points_awarded",
    "streak_bonus",
    "badge_awarded",
    "video_file_name",
    "video_file_path",
    "player_submission_notes",
    "coach_notes",
    "verification_status",
    "verification_decision",
    "coach_reviewed_at",
    "submitted_at",
]

SCORING_RULE_COLUMNS = [
    "division",
    "raw_weight",
    "effort_weight",
    "consistency_weight",
    "points_multiplier",
    "advanced_threshold",
    "elite_threshold",
    "updated_at",
]

WALLET_COLUMNS = [
    "player_name",
    "division",
    "age_group",
    "team_name",
    "points_balance",
    "total_verified_attempts",
    "starter_badge_count",
    "last_updated",
]

RANKING_HISTORY_COLUMNS = [
    "snapshot_id",
    "snapshot_type",
    "period_key",
    "created_at",
    "player_name",
    "division",
    "age_group",
    "team_name",
    "points_total",
    "rank",
]

REWARD_CATALOG_COLUMNS = [
    "reward_id",
    "reward_name",
    "reward_description",
    "sponsor_name",
    "division",
    "min_points",
    "min_verified_attempts",
    "min_improvement_delta",
    "requires_starter_badge",
    "parent_approval_required",
    "coach_approval_required",
    "points_cost",
    "status",
    "created_at",
]

SPONSOR_INVENTORY_COLUMNS = [
    "inventory_id",
    "reward_id",
    "reward_name",
    "sponsor_name",
    "total_inventory",
    "remaining_inventory",
    "status",
    "updated_at",
]

REWARD_REQUEST_COLUMNS = [
    "request_id",
    "player_name",
    "division",
    "age_group",
    "team_name",
    "reward_id",
    "reward_name",
    "sponsor_name",
    "points_cost",
    "request_status",
    "parent_approval_required",
    "parent_approval_status",
    "parent_approved_at",
    "coach_approval_required",
    "coach_approval_status",
    "coach_approved_at",
    "redemption_status",
    "redeemed_at",
    "certificate_id",
    "certificate_issued_at",
    "rejection_reason",
    "requested_at",
]

CERTIFICATE_COLUMNS = [
    "certificate_id",
    "request_id",
    "player_name",
    "reward_name",
    "sponsor_name",
    "certificate_text",
    "issued_at",
]

DEFAULT_DIVISIONS = ["Youth", "Middle School", "High School", "College", "Adult", "Open"]
DEFAULT_AGE_GROUPS = ["U10", "U12", "U14", "U16", "U18", "College", "Adult"]
VERIFICATION_RULES = [
    ("Video shows player", "Player is visible"),
    ("Video shows ball", "Ball is visible"),
    ("Video shows basket or drill area", "Court context is visible"),
    ("Attempt matches challenge", "Player is doing the correct challenge"),
    ("Score is believable", "Submitted score matches video"),
    ("No obvious editing", "No suspicious cuts"),
    ("Full attempt sequence shown", "Entire scoring sequence is visible"),
]

NON_BETTING_BLOCKED_TERMS = [
    "bet",
    "wager",
    "odds",
    "parlay",
    "gambling",
    "jackpot",
    "casino",
    "sportsbook",
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and value.strip() == "":
            return default
        out = float(value)
        if pd.isna(out):
            return default
        return out
    except Exception:
        return default


def _to_int(value: object, default: int = 0) -> int:
    return int(round(_to_float(value, float(default))))


def _to_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _contains_blocked_reward_language(text: str) -> bool:
    lower = str(text).lower()
    return any(term in lower for term in NON_BETTING_BLOCKED_TERMS)


def _request_needs_parent_approval(row: pd.Series) -> bool:
    return _to_bool(row.get("parent_approval_required", False))


def _request_needs_coach_approval(row: pd.Series) -> bool:
    return _to_bool(row.get("coach_approval_required", True))


def _inventory_remaining_for_reward(inventory_df: pd.DataFrame, reward_id: str) -> int:
    rows = inventory_df[inventory_df["reward_id"].astype(str) == str(reward_id)].copy()
    if rows.empty:
        return 0
    return _to_int(rows.iloc[0].get("remaining_inventory", 0), 0)


def _player_latest_improvement(improvement_df: pd.DataFrame, player_name: str) -> float:
    rows = improvement_df[improvement_df["player_name"].astype(str) == str(player_name)].copy()
    if rows.empty:
        return 0.0
    return _to_float(rows.iloc[0].get("improvement_delta", 0.0), 0.0)


def _is_player_eligible_for_reward(
    wallet_row: pd.Series,
    reward_row: pd.Series,
    improvement_df: pd.DataFrame,
) -> tuple[bool, str]:
    points_balance = _to_int(wallet_row.get("points_balance", 0), 0)
    verified_attempts = _to_int(wallet_row.get("total_verified_attempts", 0), 0)
    starter_badges = _to_int(wallet_row.get("starter_badge_count", 0), 0)

    min_points = _to_int(reward_row.get("min_points", 0), 0)
    min_verified_attempts = _to_int(reward_row.get("min_verified_attempts", 0), 0)
    min_improvement_delta = _to_float(reward_row.get("min_improvement_delta", 0.0), 0.0)
    needs_starter_badge = _to_bool(reward_row.get("requires_starter_badge", False))
    points_cost = _to_int(reward_row.get("points_cost", 0), 0)

    if points_balance < min_points:
        return False, f"Needs at least {min_points} development points."
    if points_balance < points_cost:
        return False, f"Needs {points_cost} points to redeem this reward."
    if verified_attempts < min_verified_attempts:
        return False, f"Needs at least {min_verified_attempts} verified attempts."

    improvement_delta = _player_latest_improvement(improvement_df, str(wallet_row.get("player_name", "")))
    if improvement_delta < min_improvement_delta:
        return False, f"Needs improvement delta of {min_improvement_delta:.2f} or higher."

    if needs_starter_badge and starter_badges <= 0:
        return False, "Requires a Starter Badge from verified challenge activity."

    return True, "Eligible"


def _certificate_text(player_name: str, reward_name: str, sponsor_name: str) -> str:
    sponsor = sponsor_name if str(sponsor_name).strip() else "Community Sponsor"
    return f"Development Certificate: {player_name} successfully redeemed '{reward_name}' supported by {sponsor}."


def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns].copy()


def _save_csv(path: Path, df: pd.DataFrame, columns: list[str]) -> None:
    df[columns].to_csv(path, index=False)


def _default_scoring_rules() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for div in DEFAULT_DIVISIONS:
        rows.append(
            {
                "division": div,
                "raw_weight": 0.60,
                "effort_weight": 0.25,
                "consistency_weight": 0.15,
                "points_multiplier": 1.5,
                "advanced_threshold": 300,
                "elite_threshold": 600,
                "updated_at": _now(),
            }
        )
    return pd.DataFrame(rows, columns=SCORING_RULE_COLUMNS)


def _ensure_storage() -> None:
    CHALLENGE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    if not CHALLENGES_CSV.exists():
        pd.DataFrame(columns=CHALLENGE_COLUMNS).to_csv(CHALLENGES_CSV, index=False)

    if not ENROLLMENTS_CSV.exists():
        pd.DataFrame(columns=ENROLLMENT_COLUMNS).to_csv(ENROLLMENTS_CSV, index=False)

    if not ATTEMPTS_CSV.exists():
        attempts_df = pd.DataFrame(columns=ATTEMPT_COLUMNS)
        if LEGACY_SUBMISSIONS_CSV.exists():
            legacy = pd.read_csv(LEGACY_SUBMISSIONS_CSV)
            if not legacy.empty:
                for _, row in legacy.iterrows():
                    score = _to_float(row.get("score", 0.0), 0.0)
                    attempts_df.loc[len(attempts_df)] = {
                        "attempt_id": row.get("submission_id", str(uuid4())[:10]),
                        "challenge_id": row.get("challenge_id", ""),
                        "challenge_title": "",
                        "player_name": row.get("player_name", ""),
                        "division": "Open",
                        "age_group": "Adult",
                        "team_name": "Independent",
                        "submitted_score": score,
                        "final_verified_score": score,
                        "raw_score": score,
                        "effort_score": score,
                        "consistency_score": score,
                        "points_awarded": int(round(score * 1.5)),
                        "streak_bonus": 0,
                        "badge_awarded": "Starter Badge",
                        "video_file_name": "",
                        "video_file_path": "",
                        "player_submission_notes": row.get("notes", ""),
                        "coach_notes": "",
                        "verification_status": "Verified",
                        "verification_decision": "Approved",
                        "coach_reviewed_at": row.get("submitted_at", _now()),
                        "submitted_at": row.get("submitted_at", _now()),
                    }
        attempts_df.to_csv(ATTEMPTS_CSV, index=False)

    if not SCORING_RULES_CSV.exists():
        _default_scoring_rules().to_csv(SCORING_RULES_CSV, index=False)

    if not WALLETS_CSV.exists():
        pd.DataFrame(columns=WALLET_COLUMNS).to_csv(WALLETS_CSV, index=False)

    if not RANKING_HISTORY_CSV.exists():
        pd.DataFrame(columns=RANKING_HISTORY_COLUMNS).to_csv(RANKING_HISTORY_CSV, index=False)

    if not REWARD_CATALOG_CSV.exists():
        pd.DataFrame(columns=REWARD_CATALOG_COLUMNS).to_csv(REWARD_CATALOG_CSV, index=False)

    if not SPONSOR_INVENTORY_CSV.exists():
        pd.DataFrame(columns=SPONSOR_INVENTORY_COLUMNS).to_csv(SPONSOR_INVENTORY_CSV, index=False)

    if not REWARD_REQUESTS_CSV.exists():
        pd.DataFrame(columns=REWARD_REQUEST_COLUMNS).to_csv(REWARD_REQUESTS_CSV, index=False)

    if not CERTIFICATES_CSV.exists():
        pd.DataFrame(columns=CERTIFICATE_COLUMNS).to_csv(CERTIFICATES_CSV, index=False)


def _normalize_challenge_status(challenges_df: pd.DataFrame) -> pd.DataFrame:
    df = challenges_df.copy()
    df["status"] = df["status"].astype(str).str.strip().replace({"Active": "Open", "Completed": "Closed", "": "Open"})
    return df


def _allowed_video(filename: str) -> bool:
    lower = filename.lower()
    return lower.endswith(".mp4") or lower.endswith(".mov") or lower.endswith(".avi") or lower.endswith(".m4v")


def _video_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp4" or suffix == ".m4v":
        return "video/mp4"
    if suffix == ".mov":
        return "video/quicktime"
    if suffix == ".avi":
        return "video/x-msvideo"
    return "video/mp4"


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _transcode_to_web_mp4(source_path: Path, output_path: Path) -> tuple[bool, str]:
    if not _ffmpeg_available():
        return False, "ffmpeg not found"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        run = subprocess.run(cmd, capture_output=True, text=True)
        if run.returncode != 0:
            detail = run.stderr.strip().splitlines()
            return False, detail[-1] if detail else "ffmpeg transcoding failed"
        return output_path.exists() and output_path.is_file(), "ok"
    except Exception as ex:
        return False, str(ex)


def _reward_status(points_total: float, advanced_threshold: float, elite_threshold: float) -> str:
    if points_total >= elite_threshold:
        return "Elite Recognition"
    if points_total >= advanced_threshold:
        return "Advanced Recognition"
    return "Skill Growth Track"


def _tier(avg_score: float) -> str:
    if avg_score >= 95:
        return "Legend"
    if avg_score >= 90:
        return "Elite"
    if avg_score >= 80:
        return "Pro"
    if avg_score >= 70:
        return "Rising"
    return "Starter"


def _composite_score(raw_score: float, effort_score: float, consistency_score: float, rule_row: pd.Series) -> float:
    raw_w = _to_float(rule_row.get("raw_weight"), 0.60)
    effort_w = _to_float(rule_row.get("effort_weight"), 0.25)
    consistency_w = _to_float(rule_row.get("consistency_weight"), 0.15)
    return (raw_score * raw_w) + (effort_score * effort_w) + (consistency_score * consistency_w)


def _points_from_score(composite: float, multiplier: float) -> int:
    return int(round(composite * multiplier))


def _streak_bonus(verified_df: pd.DataFrame, player_name: str) -> int:
    player_verified = verified_df[verified_df["player_name"].astype(str) == str(player_name)].copy()
    if player_verified.empty:
        return 0

    player_verified["submitted_dt"] = pd.to_datetime(player_verified["submitted_at"], errors="coerce")
    player_verified = player_verified.sort_values("submitted_dt", ascending=False)

    streak = 0
    prev = None
    for _, row in player_verified.iterrows():
        dt = row["submitted_dt"]
        if pd.isna(dt):
            break
        if prev is None:
            streak = 1
            prev = dt
            continue
        delta_days = (prev - dt).days
        if delta_days <= 7:
            streak += 1
            prev = dt
        else:
            break

    return min(max(streak - 1, 0) * 5, 25)


def _rebuild_wallets(attempts_df: pd.DataFrame) -> pd.DataFrame:
    verified = attempts_df[attempts_df["verification_status"].astype(str) == "Verified"].copy()
    if verified.empty:
        return pd.DataFrame(columns=WALLET_COLUMNS)

    verified["points_awarded"] = verified["points_awarded"].apply(lambda x: int(_to_float(x, 0)))
    verified["badge_awarded"] = verified["badge_awarded"].astype(str)

    wallets = (
        verified.groupby(["player_name", "division", "age_group", "team_name"], as_index=False)
        .agg(
            points_balance=("points_awarded", "sum"),
            total_verified_attempts=("attempt_id", "count"),
            starter_badge_count=("badge_awarded", lambda x: int((x == "Starter Badge").sum())),
        )
    )
    wallets["last_updated"] = _now()
    return wallets[WALLET_COLUMNS]


def _build_verified_leaderboard(attempts_df: pd.DataFrame, scoring_df: pd.DataFrame) -> pd.DataFrame:
    verified = attempts_df[attempts_df["verification_status"].astype(str) == "Verified"].copy()
    if verified.empty:
        return pd.DataFrame(columns=[
            "rank",
            "player_name",
            "division",
            "age_group",
            "team_name",
            "verified_attempts",
            "avg_score",
            "best_score",
            "points_total",
            "tier",
            "reward_status",
        ])

    scoring_lookup = scoring_df.set_index("division")
    rows: list[dict[str, object]] = []
    for _, row in verified.iterrows():
        div = str(row.get("division", "Open"))
        rule = scoring_lookup.loc[div] if div in scoring_lookup.index else scoring_lookup.iloc[0]
        final_score = _to_float(row.get("final_verified_score"), _to_float(row.get("submitted_score"), 0.0))
        effort = _to_float(row.get("effort_score"), final_score)
        consistency = _to_float(row.get("consistency_score"), final_score)
        composite = _composite_score(final_score, effort, consistency, rule)

        points_awarded = int(_to_float(row.get("points_awarded"), _points_from_score(composite, _to_float(rule.get("points_multiplier"), 1.5))))
        rows.append(
            {
                "player_name": row.get("player_name", ""),
                "division": div,
                "age_group": row.get("age_group", ""),
                "team_name": row.get("team_name", ""),
                "composite_score": round(composite, 2),
                "points": points_awarded,
                "advanced_threshold": _to_float(rule.get("advanced_threshold"), 300),
                "elite_threshold": _to_float(rule.get("elite_threshold"), 600),
            }
        )

    scored_df = pd.DataFrame(rows)
    leaderboard = (
        scored_df.groupby(["player_name", "division", "age_group", "team_name"], as_index=False)
        .agg(
            verified_attempts=("composite_score", "count"),
            avg_score=("composite_score", "mean"),
            best_score=("composite_score", "max"),
            points_total=("points", "sum"),
            advanced_threshold=("advanced_threshold", "max"),
            elite_threshold=("elite_threshold", "max"),
        )
        .sort_values(by=["points_total", "avg_score"], ascending=[False, False])
    )

    leaderboard["avg_score"] = leaderboard["avg_score"].round(1)
    leaderboard["best_score"] = leaderboard["best_score"].round(1)
    leaderboard["tier"] = leaderboard["avg_score"].apply(_tier)
    leaderboard["reward_status"] = leaderboard.apply(
        lambda r: _reward_status(_to_float(r["points_total"]), _to_float(r["advanced_threshold"]), _to_float(r["elite_threshold"])),
        axis=1,
    )
    leaderboard.insert(0, "rank", range(1, len(leaderboard) + 1))

    return leaderboard[
        [
            "rank",
            "player_name",
            "division",
            "age_group",
            "team_name",
            "verified_attempts",
            "avg_score",
            "best_score",
            "points_total",
            "tier",
            "reward_status",
        ]
    ]


def _period_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["submitted_dt"] = pd.to_datetime(out["submitted_at"], errors="coerce")
    out["year"] = out["submitted_dt"].dt.year
    out["month"] = out["submitted_dt"].dt.strftime("%Y-%m")
    out["week"] = out["submitted_dt"].dt.strftime("%G-W%V")
    return out


def _period_leaderboard(verified_df: pd.DataFrame, period_col: str, period_value: str) -> pd.DataFrame:
    if verified_df.empty:
        return pd.DataFrame(columns=["rank", "player_name", "division", "age_group", "team_name", "points_total", "verified_attempts"])

    view = verified_df[verified_df[period_col].astype(str) == str(period_value)].copy()
    if view.empty:
        return pd.DataFrame(columns=["rank", "player_name", "division", "age_group", "team_name", "points_total", "verified_attempts"])

    view["points_awarded"] = view["points_awarded"].apply(lambda x: int(_to_float(x, 0)))

    rank_df = (
        view.groupby(["player_name", "division", "age_group", "team_name"], as_index=False)
        .agg(points_total=("points_awarded", "sum"), verified_attempts=("attempt_id", "count"))
        .sort_values(by=["points_total", "verified_attempts"], ascending=[False, False])
    )
    rank_df.insert(0, "rank", range(1, len(rank_df) + 1))
    return rank_df


def _improvement_rankings(verified_df: pd.DataFrame) -> pd.DataFrame:
    if verified_df.empty:
        return pd.DataFrame(columns=["rank", "player_name", "division", "team_name", "improvement_delta"])

    df = verified_df.copy()
    df["submitted_dt"] = pd.to_datetime(df["submitted_at"], errors="coerce")
    df = df.sort_values("submitted_dt")

    rows: list[dict[str, object]] = []
    for player, group in df.groupby("player_name"):
        scores = group["final_verified_score"].apply(lambda x: _to_float(x, 0)).tolist()
        if len(scores) < 2:
            continue
        midpoint = len(scores) // 2
        first_half = scores[:midpoint] if midpoint > 0 else scores[:1]
        second_half = scores[midpoint:] if midpoint > 0 else scores[-1:]
        if not first_half or not second_half:
            continue
        delta = (sum(second_half) / len(second_half)) - (sum(first_half) / len(first_half))
        latest = group.iloc[-1]
        rows.append(
            {
                "player_name": player,
                "division": latest.get("division", ""),
                "team_name": latest.get("team_name", ""),
                "improvement_delta": round(delta, 2),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["rank", "player_name", "division", "team_name", "improvement_delta"])

    out = pd.DataFrame(rows).sort_values("improvement_delta", ascending=False)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def _verified_attempt_rankings(verified_df: pd.DataFrame) -> pd.DataFrame:
    if verified_df.empty:
        return pd.DataFrame(columns=["rank", "player_name", "challenge_title", "division", "final_verified_score", "points_awarded", "submitted_at"])

    out = verified_df.copy()
    out["final_verified_score"] = out["final_verified_score"].apply(lambda x: _to_float(x, _to_float(x, 0)))
    out["points_awarded"] = out["points_awarded"].apply(lambda x: int(_to_float(x, 0)))
    out = out.sort_values(by=["final_verified_score", "points_awarded"], ascending=[False, False])
    out.insert(0, "rank", range(1, len(out) + 1))
    return out[["rank", "player_name", "challenge_title", "division", "final_verified_score", "points_awarded", "submitted_at"]]


def _leaderboard_pdf(leaderboard_df: pd.DataFrame) -> bytes:
    if not REPORTLAB_AVAILABLE:
        return b""

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    rows = [["Rank", "Player", "Division", "Age Group", "Team", "Attempts", "Points", "Reward"]]
    for _, row in leaderboard_df.iterrows():
        rows.append(
            [
                str(int(row["rank"])),
                str(row["player_name"]),
                str(row["division"]),
                str(row["age_group"]),
                str(row["team_name"]),
                str(int(row["verified_attempts"])),
                str(int(row["points_total"])),
                str(row["reward_status"]),
            ]
        )

    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )

    elements = [
        Paragraph("Skill Challenge League - Verified Leaderboard", styles["Title"]),
        Spacer(1, 8),
        Paragraph(f"Generated: {_now()}", styles["Normal"]),
        Spacer(1, 12),
        table,
    ]
    doc.build(elements)
    return buffer.getvalue()


def _save_ranking_snapshot(ranking_df: pd.DataFrame, snapshot_type: str, period_key: str) -> None:
    if ranking_df.empty:
        return

    history_df = _load_csv(RANKING_HISTORY_CSV, RANKING_HISTORY_COLUMNS)
    snap_id = str(uuid4())[:10]
    now = _now()

    rows = []
    for _, row in ranking_df.iterrows():
        rows.append(
            {
                "snapshot_id": snap_id,
                "snapshot_type": snapshot_type,
                "period_key": period_key,
                "created_at": now,
                "player_name": row.get("player_name", ""),
                "division": row.get("division", ""),
                "age_group": row.get("age_group", ""),
                "team_name": row.get("team_name", ""),
                "points_total": int(_to_float(row.get("points_total"), 0)),
                "rank": int(_to_float(row.get("rank"), 0)),
            }
        )

    history_df = pd.concat([history_df, pd.DataFrame(rows)], ignore_index=True)
    _save_csv(RANKING_HISTORY_CSV, history_df, RANKING_HISTORY_COLUMNS)


_ensure_storage()

st.set_page_config(page_title="Basketball Challenge Hub V5.4", page_icon="🏀", layout="wide")
st.title("Basketball Challenge Hub V5.4")
st.caption(
    "V5.4 is complete when the Skill Challenge League can manage a development-safe reward catalog, identify eligible players, support sponsor-provided rewards, require coach and parent approvals, track redemption status, issue digital certificates, and maintain non-betting prize language across the platform."
)

challenges_df = _normalize_challenge_status(_load_csv(CHALLENGES_CSV, CHALLENGE_COLUMNS))
enrollments_df = _load_csv(ENROLLMENTS_CSV, ENROLLMENT_COLUMNS)
attempts_df = _load_csv(ATTEMPTS_CSV, ATTEMPT_COLUMNS)
scoring_df = _load_csv(SCORING_RULES_CSV, SCORING_RULE_COLUMNS)

if scoring_df.empty:
    scoring_df = _default_scoring_rules()
    _save_csv(SCORING_RULES_CSV, scoring_df, SCORING_RULE_COLUMNS)

history_df = _load_csv(RANKING_HISTORY_CSV, RANKING_HISTORY_COLUMNS)
reward_catalog_df = _load_csv(REWARD_CATALOG_CSV, REWARD_CATALOG_COLUMNS)
sponsor_inventory_df = _load_csv(SPONSOR_INVENTORY_CSV, SPONSOR_INVENTORY_COLUMNS)
reward_requests_df = _load_csv(REWARD_REQUESTS_CSV, REWARD_REQUEST_COLUMNS)
certificates_df = _load_csv(CERTIFICATES_CSV, CERTIFICATE_COLUMNS)

division_options = scoring_df["division"].dropna().astype(str).tolist()
if not division_options:
    division_options = DEFAULT_DIVISIONS

open_challenges_df = challenges_df[challenges_df["status"] == "Open"].copy()
verified_attempts_df = attempts_df[attempts_df["verification_status"].astype(str) == "Verified"].copy()
pending_attempts_df = attempts_df[attempts_df["verification_status"].astype(str) == "Pending Review"].copy()

wallets_df = _rebuild_wallets(attempts_df)
_save_csv(WALLETS_CSV, wallets_df, WALLET_COLUMNS)

with st.sidebar:
    st.markdown("[Back to Main V2.9 App (Port 8511)](http://localhost:8511)")
    st.divider()
    st.header("Create Skill Challenge")
    with st.form("challenge_form", clear_on_submit=True):
        title = st.text_input("Challenge Title")
        description = st.text_area("Challenge Description", height=80)
        division = st.selectbox("Division", division_options)
        difficulty = st.selectbox("Difficulty", ["Foundational", "Progressive", "Advanced", "Elite"], index=1)
        target_reps = st.number_input("Target Reps", min_value=1, max_value=5000, value=250, step=10)
        target_days = st.number_input("Target Days", min_value=1, max_value=60, value=7, step=1)
        create_challenge = st.form_submit_button("Save Challenge", use_container_width=True)

        if create_challenge:
            if not title.strip():
                st.error("Challenge title is required.")
            else:
                challenges_df = pd.concat(
                    [
                        challenges_df,
                        pd.DataFrame(
                            [
                                {
                                    "challenge_id": str(uuid4())[:8],
                                    "title": title.strip(),
                                    "description": description.strip(),
                                    "division": division,
                                    "difficulty": difficulty,
                                    "target_reps": int(target_reps),
                                    "target_days": int(target_days),
                                    "status": "Open",
                                    "created_at": _now(),
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
                _save_csv(CHALLENGES_CSV, challenges_df, CHALLENGE_COLUMNS)
                st.success("Challenge saved to CSV.")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Open Challenges", len(open_challenges_df))
m2.metric("Player Wallets", len(wallets_df))
m3.metric("Pending Verification", len(pending_attempts_df))
m4.metric("Verified Attempts", len(verified_attempts_df))

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Skill Challenge League",
    "Enroll Players",
    "Player Video Submission",
    "Coach Verification",
    "Verified Leaderboard",
    "Rankings and Wallets",
    "Rewards and Redemption",
])

with tab1:
    st.subheader("Skill Challenge League")
    if open_challenges_df.empty:
        st.info("No open challenges yet. Create one from the sidebar.")
    else:
        cols = ["challenge_id", "title", "division", "difficulty", "target_reps", "target_days", "created_at"]
        st.dataframe(open_challenges_df[cols].sort_values("created_at", ascending=False), use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Enroll Players")
    if open_challenges_df.empty:
        st.warning("Open at least one challenge before enrolling players.")
    else:
        with st.form("enroll_form", clear_on_submit=True):
            challenge_label = st.selectbox("Challenge", [f"{row.challenge_id} | {row.title}" for _, row in open_challenges_df.iterrows()])
            player_name = st.text_input("Player Name")
            division = st.selectbox("Player Division", division_options, key="enroll_division")
            age_group = st.selectbox("Age Group", DEFAULT_AGE_GROUPS)
            team_name = st.text_input("Team Name", value="Independent")
            enroll = st.form_submit_button("Enroll Player", use_container_width=True)

            if enroll:
                if not player_name.strip():
                    st.error("Player name is required.")
                else:
                    selected_id = challenge_label.split("|")[0].strip()
                    selected_title = challenge_label.split("|")[1].strip()
                    enrollments_df = pd.concat(
                        [
                            enrollments_df,
                            pd.DataFrame(
                                [
                                    {
                                        "enrollment_id": str(uuid4())[:10],
                                        "challenge_id": selected_id,
                                        "challenge_title": selected_title,
                                        "player_name": player_name.strip(),
                                        "division": division,
                                        "age_group": age_group,
                                        "team_name": team_name.strip() or "Independent",
                                        "enrolled_at": _now(),
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )
                    _save_csv(ENROLLMENTS_CSV, enrollments_df, ENROLLMENT_COLUMNS)
                    st.success("Player enrolled.")

    if enrollments_df.empty:
        st.info("No enrollments yet.")
    else:
        st.dataframe(enrollments_df.sort_values("enrolled_at", ascending=False), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Player Video Submission")
    if enrollments_df.empty:
        st.warning("Enroll players before submitting challenge attempts.")
    else:
        choices = [f"{row.enrollment_id} | {row.player_name} | {row.challenge_title} | {row.division}" for _, row in enrollments_df.iterrows()]
        with st.form("submission_form", clear_on_submit=True):
            selected_enrollment = st.selectbox("Enrollment", choices)
            submitted_score = st.number_input("Submitted Score", min_value=0, max_value=1000, value=100, step=1)
            upload = st.file_uploader("Upload Attempt Video", type=["mp4", "mov", "avi", "m4v"])
            submission_notes = st.text_area("Player Submission Notes", height=80)
            submit_attempt = st.form_submit_button("Submit Attempt for Verification", use_container_width=True)

            if submit_attempt:
                if upload is None:
                    st.error("Video upload is required for verification.")
                elif not _allowed_video(upload.name):
                    st.error("Unsupported video type. Use mp4, mov, avi, or m4v.")
                else:
                    enrollment_id = selected_enrollment.split("|")[0].strip()
                    row = enrollments_df[enrollments_df["enrollment_id"] == enrollment_id].iloc[0]
                    attempt_id = str(uuid4())[:10]
                    safe_name = upload.name.replace(" ", "_")
                    saved_name = f"{attempt_id}_{safe_name}"
                    saved_path = VIDEO_DIR / saved_name
                    saved_path.write_bytes(upload.getbuffer())

                    final_video_name = saved_name
                    final_video_path = saved_path

                    # Convert non-MP4 uploads into web-safe MP4 for reliable in-browser preview.
                    if saved_path.suffix.lower() != ".mp4":
                        transcoded_name = f"{attempt_id}_websafe.mp4"
                        transcoded_path = VIDEO_DIR / transcoded_name
                        ok_transcode, transcode_detail = _transcode_to_web_mp4(saved_path, transcoded_path)
                        if ok_transcode:
                            final_video_name = transcoded_name
                            final_video_path = transcoded_path
                            st.info("Video converted to web-safe MP4 for coach preview.")
                        else:
                            st.warning(f"Video kept in original format for now ({transcode_detail}).")

                    attempt_row = {
                        "attempt_id": attempt_id,
                        "challenge_id": row["challenge_id"],
                        "challenge_title": row["challenge_title"],
                        "player_name": row["player_name"],
                        "division": row.get("division", "Open"),
                        "age_group": row.get("age_group", "Adult"),
                        "team_name": row.get("team_name", "Independent"),
                        "submitted_score": int(submitted_score),
                        "final_verified_score": "",
                        "raw_score": int(submitted_score),
                        "effort_score": int(submitted_score),
                        "consistency_score": int(submitted_score),
                        "points_awarded": 0,
                        "streak_bonus": 0,
                        "badge_awarded": "",
                        "video_file_name": final_video_name,
                        "video_file_path": str(final_video_path),
                        "player_submission_notes": submission_notes.strip(),
                        "coach_notes": "",
                        "verification_status": "Pending Review",
                        "verification_decision": "Pending",
                        "coach_reviewed_at": "",
                        "submitted_at": _now(),
                    }
                    attempts_df = pd.concat([attempts_df, pd.DataFrame([attempt_row])], ignore_index=True)
                    _save_csv(ATTEMPTS_CSV, attempts_df, ATTEMPT_COLUMNS)
                    st.success("Attempt submitted and queued for coach verification.")

with tab4:
    st.subheader("Coach Verification Queue")
    st.markdown("### V5.2 Verification Rules")
    st.dataframe(pd.DataFrame(VERIFICATION_RULES, columns=["Rule", "Check"]), use_container_width=True, hide_index=True)

    pending_df = attempts_df[attempts_df["verification_status"].astype(str) == "Pending Review"].copy()
    if pending_df.empty:
        st.info("No pending attempts to review.")
    else:
        labels = []
        for _, r in pending_df.iterrows():
            safe_score = _to_int(r.get("submitted_score", 0), 0)
            labels.append(f"{r.attempt_id} | {r.player_name} | {r.challenge_title} | score:{safe_score}")
        selected_label = st.selectbox("Pending Attempt", labels)
        selected_id = selected_label.split("|")[0].strip()
        row_idx = attempts_df.index[attempts_df["attempt_id"] == selected_id][0]
        selected_row = attempts_df.loc[row_idx]
        submitted_score_value = _to_int(selected_row.get("submitted_score", 0), 0)

        st.markdown(f"**Player:** {selected_row['player_name']}")
        st.markdown(f"**Challenge:** {selected_row['challenge_title']}")
        st.markdown(f"**Submitted Score:** {submitted_score_value}")

        st.markdown("### Coach Video Review")

        raw_video_path = str(selected_row.get("video_file_path", "")).strip()
        raw_video_name = str(selected_row.get("video_file_name", "")).strip()
        if not raw_video_path or raw_video_path in {".", "./", ".\\"}:
            st.warning("Video path is missing or invalid for this attempt.")
        else:
            video_path = Path(raw_video_path)
            if not video_path.is_absolute():
                video_path = (BASE_DIR / video_path).resolve()

            if video_path.exists() and video_path.is_file():
                file_name = raw_video_name or video_path.name
                file_size_mb = round(video_path.stat().st_size / (1024 * 1024), 2)
                video_mime = _video_mime_type(video_path)
                info_c1, info_c2 = st.columns(2)
                info_c1.caption(f"File: {file_name}")
                info_c2.caption(f"Size: {file_size_mb} MB")

                try:
                    video_bytes = video_path.read_bytes()
                    st.video(video_bytes, format=video_mime)
                except Exception:
                    st.warning("Video file could not be opened for preview.")

                try:
                    st.download_button(
                        "Download Attempt Video",
                        data=video_bytes,
                        file_name=file_name,
                        mime=video_mime,
                        use_container_width=True,
                    )
                except Exception:
                    st.warning("Video file exists but could not be read for download.")

                st.caption("If preview is blank, download and open locally. Recommended upload format is MP4 (H.264).")
            else:
                st.warning("Video file not found on disk.")

        with st.form("coach_review_form"):
            checks = []
            for idx, (rule, check) in enumerate(VERIFICATION_RULES):
                checks.append(st.checkbox(f"{rule} - {check}", key=f"rule_{selected_id}_{idx}"))

            decision = st.selectbox("Coach Decision", ["Approve (Verified)", "Reject"])
            adjusted_score = st.number_input(
                "Final Verified Score",
                min_value=0,
                max_value=1000,
                value=submitted_score_value,
                step=1,
            )
            coach_notes = st.text_area("Coach Notes", height=90)
            save_review = st.form_submit_button("Save Coach Decision", use_container_width=True)

            if save_review:
                if decision == "Approve (Verified)" and not all(checks):
                    st.error("All verification rules must be checked before approval.")
                else:
                    if decision == "Approve (Verified)":
                        verified_now = attempts_df[attempts_df["verification_status"].astype(str) == "Verified"].copy()
                        streak_bonus = _streak_bonus(verified_now, str(selected_row.get("player_name", "")))

                        div = str(selected_row.get("division", "Open"))
                        scoring_lookup = scoring_df.set_index("division")
                        rule = scoring_lookup.loc[div] if div in scoring_lookup.index else scoring_lookup.iloc[0]

                        final_score = int(adjusted_score)
                        composite = _composite_score(final_score, final_score, final_score, rule)
                        base_points = _points_from_score(composite, _to_float(rule.get("points_multiplier"), 1.5))
                        points_awarded = base_points + streak_bonus

                        prior_verified_count = len(verified_now[verified_now["player_name"].astype(str) == str(selected_row.get("player_name", ""))])
                        badge = "Starter Badge" if prior_verified_count == 0 else ""

                        attempts_df.loc[row_idx, "verification_status"] = "Verified"
                        attempts_df.loc[row_idx, "verification_decision"] = "Approved"
                        attempts_df.loc[row_idx, "final_verified_score"] = final_score
                        attempts_df.loc[row_idx, "raw_score"] = final_score
                        attempts_df.loc[row_idx, "effort_score"] = final_score
                        attempts_df.loc[row_idx, "consistency_score"] = final_score
                        attempts_df.loc[row_idx, "streak_bonus"] = streak_bonus
                        attempts_df.loc[row_idx, "points_awarded"] = points_awarded
                        attempts_df.loc[row_idx, "badge_awarded"] = badge
                    else:
                        attempts_df.loc[row_idx, "verification_status"] = "Rejected"
                        attempts_df.loc[row_idx, "verification_decision"] = "Rejected"
                        attempts_df.loc[row_idx, "final_verified_score"] = ""
                        attempts_df.loc[row_idx, "streak_bonus"] = 0
                        attempts_df.loc[row_idx, "points_awarded"] = 0
                        attempts_df.loc[row_idx, "badge_awarded"] = ""

                    attempts_df.loc[row_idx, "coach_notes"] = coach_notes.strip()
                    attempts_df.loc[row_idx, "coach_reviewed_at"] = _now()
                    _save_csv(ATTEMPTS_CSV, attempts_df, ATTEMPT_COLUMNS)
                    st.success("Coach verification saved.")

with tab5:
    st.subheader("Verified Leaderboard")
    st.caption("Leaderboard automatically updates using verified attempts only.")

    leaderboard_df = _build_verified_leaderboard(attempts_df, scoring_df)
    pending_count = len(attempts_df[attempts_df["verification_status"].astype(str) == "Pending Review"])

    if leaderboard_df.empty:
        st.info("No verified attempts yet.")
        if pending_count > 0:
            st.warning(f"Pending attempts excluded: {pending_count}")
    else:
        st.dataframe(leaderboard_df, use_container_width=True, hide_index=True)
        st.info(f"Verified leaderboard rows: {len(leaderboard_df)}. Pending attempts excluded: {pending_count}.")

        csv_data = leaderboard_df.to_csv(index=False).encode("utf-8")
        c1, c2 = st.columns(2)
        c1.download_button(
            "Export Leaderboard CSV",
            data=csv_data,
            file_name=f"verified_leaderboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        if REPORTLAB_AVAILABLE:
            pdf_data = _leaderboard_pdf(leaderboard_df)
            c2.download_button(
                "Export Leaderboard PDF",
                data=pdf_data,
                file_name=f"verified_leaderboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            c2.warning("PDF export unavailable: reportlab not installed.")

with tab6:
    st.subheader("Rankings and Wallets")

    verified = attempts_df[attempts_df["verification_status"].astype(str) == "Verified"].copy()
    verified = _period_columns(verified)

    week_options = sorted([w for w in verified.get("week", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()], reverse=True)
    month_options = sorted([m for m in verified.get("month", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()], reverse=True)
    year_options = sorted([str(int(y)) for y in verified.get("year", pd.Series(dtype=float)).dropna().unique().tolist()], reverse=True)

    selected_week = week_options[0] if week_options else ""
    selected_month = month_options[0] if month_options else ""
    selected_year = year_options[0] if year_options else ""

    c1, c2, c3 = st.columns(3)
    if week_options:
        selected_week = c1.selectbox("Weekly Ranking", week_options)
    if month_options:
        selected_month = c2.selectbox("Monthly Ranking", month_options)
    if year_options:
        selected_year = c3.selectbox("Season Ranking", year_options)

    weekly_df = _period_leaderboard(verified, "week", selected_week) if selected_week else pd.DataFrame()
    monthly_df = _period_leaderboard(verified, "month", selected_month) if selected_month else pd.DataFrame()
    season_df = _period_leaderboard(verified, "year", selected_year) if selected_year else pd.DataFrame()

    st.markdown("### Top Performer Cards")
    top_cols = st.columns(3)
    top_week = weekly_df.iloc[0] if not weekly_df.empty else None
    top_month = monthly_df.iloc[0] if not monthly_df.empty else None
    top_season = season_df.iloc[0] if not season_df.empty else None
    top_cols[0].metric("Top Weekly", str(top_week["player_name"]) if top_week is not None else "N/A", str(int(top_week["points_total"])) + " pts" if top_week is not None else "")
    top_cols[1].metric("Top Monthly", str(top_month["player_name"]) if top_month is not None else "N/A", str(int(top_month["points_total"])) + " pts" if top_month is not None else "")
    top_cols[2].metric("Top Season", str(top_season["player_name"]) if top_season is not None else "N/A", str(int(top_season["points_total"])) + " pts" if top_season is not None else "")

    st.markdown("### Player Point Wallets")
    if wallets_df.empty:
        st.info("No wallet balances yet. Verify attempts to build player wallets.")
    else:
        st.dataframe(wallets_df.sort_values("points_balance", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("### Weekly Rankings")
    if weekly_df.empty:
        st.info("No weekly ranking data available.")
    else:
        st.dataframe(weekly_df, use_container_width=True, hide_index=True)

    st.markdown("### Monthly Rankings")
    if monthly_df.empty:
        st.info("No monthly ranking data available.")
    else:
        st.dataframe(monthly_df, use_container_width=True, hide_index=True)

    st.markdown("### Season Rankings")
    if season_df.empty:
        st.info("No season ranking data available.")
    else:
        st.dataframe(season_df, use_container_width=True, hide_index=True)

    st.markdown("### Division Rankings")
    if not wallets_df.empty:
        div_rank = wallets_df.sort_values(["division", "points_balance"], ascending=[True, False])
        st.dataframe(div_rank[["player_name", "division", "points_balance", "total_verified_attempts"]], use_container_width=True, hide_index=True)

    st.markdown("### Age Group Rankings")
    if not wallets_df.empty:
        age_rank = wallets_df.sort_values(["age_group", "points_balance"], ascending=[True, False])
        st.dataframe(age_rank[["player_name", "age_group", "points_balance", "total_verified_attempts"]], use_container_width=True, hide_index=True)

    st.markdown("### Team Rankings")
    if wallets_df.empty:
        st.info("No team ranking data available yet.")
    else:
        team_rank = wallets_df.groupby("team_name", as_index=False).agg(team_points=("points_balance", "sum"), players=("player_name", "count")).sort_values("team_points", ascending=False)
        team_rank.insert(0, "rank", range(1, len(team_rank) + 1))
        st.dataframe(team_rank, use_container_width=True, hide_index=True)

    st.markdown("### Improvement Rankings")
    improve_df = _improvement_rankings(verified)
    if improve_df.empty:
        st.info("Need multiple verified attempts per player to calculate improvement rankings.")
    else:
        st.dataframe(improve_df, use_container_width=True, hide_index=True)

    st.markdown("### Verified Attempt Rankings")
    attempt_rank_df = _verified_attempt_rankings(verified)
    if attempt_rank_df.empty:
        st.info("No verified attempts available.")
    else:
        st.dataframe(attempt_rank_df, use_container_width=True, hide_index=True)

    st.markdown("### Save Ranking History Snapshots")
    s1, s2, s3 = st.columns(3)
    if s1.button("Save Weekly Snapshot", use_container_width=True, disabled=weekly_df.empty):
        _save_ranking_snapshot(weekly_df, "weekly", selected_week)
        st.success("Weekly ranking snapshot saved.")
    if s2.button("Save Monthly Snapshot", use_container_width=True, disabled=monthly_df.empty):
        _save_ranking_snapshot(monthly_df, "monthly", selected_month)
        st.success("Monthly ranking snapshot saved.")
    if s3.button("Save Season Snapshot", use_container_width=True, disabled=season_df.empty):
        _save_ranking_snapshot(season_df, "season", selected_year)
        st.success("Season ranking snapshot saved.")

    history_df = _load_csv(RANKING_HISTORY_CSV, RANKING_HISTORY_COLUMNS)
    if history_df.empty:
        st.info("No ranking history snapshots yet.")
    else:
        st.dataframe(history_df.sort_values("created_at", ascending=False), use_container_width=True, hide_index=True)

with tab7:
    st.subheader("Rewards and Redemption")
    st.caption("Development-safe rewards only. This platform does not support betting or gambling language.")

    verified_for_rewards = attempts_df[attempts_df["verification_status"].astype(str) == "Verified"].copy()
    improvement_for_rewards = _improvement_rankings(verified_for_rewards)

    active_rewards = reward_catalog_df[reward_catalog_df["status"].astype(str) == "Active"].copy()
    open_requests = reward_requests_df[~reward_requests_df["redemption_status"].astype(str).isin(["Redeemed", "Closed"])].copy()
    redeemed_requests = reward_requests_df[reward_requests_df["redemption_status"].astype(str) == "Redeemed"].copy()

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Reward Catalog", len(reward_catalog_df))
    r2.metric("Active Rewards", len(active_rewards))
    r3.metric("Open Requests", len(open_requests))
    r4.metric("Redeemed Rewards", len(redeemed_requests))

    st.markdown("### Maintain Reward Catalog")
    with st.form("reward_catalog_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        reward_name = c1.text_input("Reward Name")
        sponsor_name = c2.text_input("Sponsor Name", value="Community Sponsor")
        reward_description = st.text_area("Reward Description", height=80)
        c3, c4, c5 = st.columns(3)
        reward_division = c3.selectbox("Reward Division", ["All"] + division_options)
        points_cost = c4.number_input("Points Cost", min_value=0, max_value=5000, value=100, step=5)
        total_inventory = c5.number_input("Sponsor Inventory", min_value=0, max_value=5000, value=25, step=1)
        c6, c7, c8 = st.columns(3)
        min_points = c6.number_input("Minimum Points", min_value=0, max_value=5000, value=100, step=5)
        min_verified_attempts = c7.number_input("Minimum Verified Attempts", min_value=0, max_value=200, value=1, step=1)
        min_improvement_delta = c8.number_input("Minimum Improvement Delta", min_value=0.0, max_value=200.0, value=0.0, step=0.5)
        c9, c10, c11 = st.columns(3)
        requires_starter_badge = c9.checkbox("Requires Starter Badge", value=False)
        parent_required = c10.checkbox("Parent Approval Required", value=False)
        coach_required = c11.checkbox("Coach Approval Required", value=True)
        save_reward = st.form_submit_button("Save Reward Catalog Entry", use_container_width=True)

        if save_reward:
            if not reward_name.strip():
                st.error("Reward name is required.")
            elif _contains_blocked_reward_language(reward_name) or _contains_blocked_reward_language(reward_description):
                st.error("Reward language must remain development-safe and non-betting.")
            else:
                reward_id = str(uuid4())[:10]
                now = _now()
                reward_row = {
                    "reward_id": reward_id,
                    "reward_name": reward_name.strip(),
                    "reward_description": reward_description.strip(),
                    "sponsor_name": sponsor_name.strip() or "Community Sponsor",
                    "division": reward_division,
                    "min_points": int(min_points),
                    "min_verified_attempts": int(min_verified_attempts),
                    "min_improvement_delta": round(float(min_improvement_delta), 2),
                    "requires_starter_badge": bool(requires_starter_badge),
                    "parent_approval_required": bool(parent_required),
                    "coach_approval_required": bool(coach_required),
                    "points_cost": int(points_cost),
                    "status": "Active",
                    "created_at": now,
                }
                reward_catalog_df = pd.concat([reward_catalog_df, pd.DataFrame([reward_row])], ignore_index=True)
                _save_csv(REWARD_CATALOG_CSV, reward_catalog_df, REWARD_CATALOG_COLUMNS)

                inventory_row = {
                    "inventory_id": str(uuid4())[:10],
                    "reward_id": reward_id,
                    "reward_name": reward_name.strip(),
                    "sponsor_name": sponsor_name.strip() or "Community Sponsor",
                    "total_inventory": int(total_inventory),
                    "remaining_inventory": int(total_inventory),
                    "status": "Active",
                    "updated_at": now,
                }
                sponsor_inventory_df = pd.concat([sponsor_inventory_df, pd.DataFrame([inventory_row])], ignore_index=True)
                _save_csv(SPONSOR_INVENTORY_CSV, sponsor_inventory_df, SPONSOR_INVENTORY_COLUMNS)
                st.success("Reward catalog and sponsor inventory updated.")

    if reward_catalog_df.empty:
        st.info("No rewards in catalog yet.")
    else:
        catalog_view = reward_catalog_df.merge(
            sponsor_inventory_df[["reward_id", "remaining_inventory"]],
            on="reward_id",
            how="left",
        )
        catalog_view["remaining_inventory"] = catalog_view["remaining_inventory"].fillna(0).apply(lambda x: _to_int(x, 0))
        st.dataframe(catalog_view.sort_values("created_at", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("### Evaluate Player Reward Eligibility")
    if wallets_df.empty or reward_catalog_df.empty:
        st.info("Need wallet points and reward catalog entries to evaluate eligibility.")
    else:
        player_options = sorted(wallets_df["player_name"].dropna().astype(str).unique().tolist())
        selected_player = st.selectbox("Player for Eligibility Check", player_options)
        player_wallet = wallets_df[wallets_df["player_name"].astype(str) == selected_player].iloc[0]
        player_division = str(player_wallet.get("division", ""))
        eval_rows: list[dict[str, object]] = []
        for _, reward_row in reward_catalog_df.iterrows():
            reward_division = str(reward_row.get("division", "All"))
            if reward_division not in {"All", player_division}:
                continue
            remaining = _inventory_remaining_for_reward(sponsor_inventory_df, str(reward_row.get("reward_id", "")))
            eligible, reason = _is_player_eligible_for_reward(player_wallet, reward_row, improvement_for_rewards)
            if remaining <= 0:
                eligible = False
                reason = "Inventory unavailable"
            eval_rows.append(
                {
                    "reward_name": reward_row.get("reward_name", ""),
                    "sponsor_name": reward_row.get("sponsor_name", ""),
                    "points_cost": _to_int(reward_row.get("points_cost", 0), 0),
                    "remaining_inventory": remaining,
                    "eligible": "Yes" if eligible else "No",
                    "reason": reason,
                }
            )

        if not eval_rows:
            st.info("No rewards currently aligned to this player's division.")
        else:
            st.dataframe(pd.DataFrame(eval_rows), use_container_width=True, hide_index=True)

    st.markdown("### Request Reward Redemption")
    if wallets_df.empty or active_rewards.empty:
        st.info("Need active rewards and player wallets before requesting redemption.")
    else:
        request_player_options = sorted(wallets_df["player_name"].dropna().astype(str).unique().tolist())
        with st.form("reward_request_form", clear_on_submit=True):
            request_player = st.selectbox("Requesting Player", request_player_options)
            request_wallet = wallets_df[wallets_df["player_name"].astype(str) == request_player].iloc[0]
            request_division = str(request_wallet.get("division", ""))

            eligible_reward_rows: list[pd.Series] = []
            eligible_labels: list[str] = []
            for _, reward_row in active_rewards.iterrows():
                reward_division = str(reward_row.get("division", "All"))
                if reward_division not in {"All", request_division}:
                    continue
                remaining = _inventory_remaining_for_reward(sponsor_inventory_df, str(reward_row.get("reward_id", "")))
                eligible, _ = _is_player_eligible_for_reward(request_wallet, reward_row, improvement_for_rewards)
                if eligible and remaining > 0:
                    eligible_reward_rows.append(reward_row)
                    eligible_labels.append(
                        f"{reward_row.get('reward_id', '')} | {reward_row.get('reward_name', '')} | cost:{_to_int(reward_row.get('points_cost', 0), 0)} | remaining:{remaining}"
                    )

            if not eligible_labels:
                st.info("No currently eligible rewards for this player.")
                submit_request = False
            else:
                selected_reward_label = st.selectbox("Eligible Reward", eligible_labels)
                submit_request = st.form_submit_button("Submit Reward Request", use_container_width=True)

            if submit_request and eligible_labels:
                selected_reward_id = selected_reward_label.split("|")[0].strip()
                reward_row = active_rewards[active_rewards["reward_id"].astype(str) == selected_reward_id].iloc[0]

                request_row = {
                    "request_id": str(uuid4())[:10],
                    "player_name": request_player,
                    "division": request_wallet.get("division", ""),
                    "age_group": request_wallet.get("age_group", ""),
                    "team_name": request_wallet.get("team_name", ""),
                    "reward_id": reward_row.get("reward_id", ""),
                    "reward_name": reward_row.get("reward_name", ""),
                    "sponsor_name": reward_row.get("sponsor_name", ""),
                    "points_cost": _to_int(reward_row.get("points_cost", 0), 0),
                    "request_status": "Pending Approvals",
                    "parent_approval_required": bool(_to_bool(reward_row.get("parent_approval_required", False))),
                    "parent_approval_status": "Pending" if _to_bool(reward_row.get("parent_approval_required", False)) else "Not Required",
                    "parent_approved_at": "",
                    "coach_approval_required": bool(_to_bool(reward_row.get("coach_approval_required", True))),
                    "coach_approval_status": "Pending" if _to_bool(reward_row.get("coach_approval_required", True)) else "Not Required",
                    "coach_approved_at": "",
                    "redemption_status": "Requested",
                    "redeemed_at": "",
                    "certificate_id": "",
                    "certificate_issued_at": "",
                    "rejection_reason": "",
                    "requested_at": _now(),
                }
                reward_requests_df = pd.concat([reward_requests_df, pd.DataFrame([request_row])], ignore_index=True)
                _save_csv(REWARD_REQUESTS_CSV, reward_requests_df, REWARD_REQUEST_COLUMNS)
                st.success("Reward request submitted.")

    st.markdown("### Approve, Reject, or Redeem Rewards")
    pending_requests = reward_requests_df[~reward_requests_df["request_status"].astype(str).isin(["Rejected"])].copy()
    if pending_requests.empty:
        st.info("No reward requests available for approval/redeem actions.")
    else:
        labels = [f"{r.request_id} | {r.player_name} | {r.reward_name} | {r.request_status}" for _, r in pending_requests.iterrows()]
        selected_request_label = st.selectbox("Reward Request", labels)
        selected_request_id = selected_request_label.split("|")[0].strip()
        req_idx = reward_requests_df.index[reward_requests_df["request_id"].astype(str) == selected_request_id][0]
        req_row = reward_requests_df.loc[req_idx]

        st.markdown(f"**Player:** {req_row['player_name']}")
        st.markdown(f"**Reward:** {req_row['reward_name']}")
        st.markdown(f"**Sponsor:** {req_row['sponsor_name']}")
        st.markdown(f"**Status:** {req_row['request_status']} / {req_row['redemption_status']}")

        with st.form("reward_approval_form"):
            parent_action = st.selectbox("Parent Approval Action", ["No Change", "Approve", "Reject"])
            coach_action = st.selectbox("Coach Approval Action", ["No Change", "Approve", "Reject"])
            redemption_action = st.selectbox("Redemption Action", ["No Change", "Mark Redeemed"])
            rejection_reason = st.text_input("Rejection Reason")
            save_reward_action = st.form_submit_button("Save Reward Decision", use_container_width=True)

            if save_reward_action:
                now = _now()

                if parent_action == "Approve" and _request_needs_parent_approval(req_row):
                    reward_requests_df.loc[req_idx, "parent_approval_status"] = "Approved"
                    reward_requests_df.loc[req_idx, "parent_approved_at"] = now
                elif parent_action == "Reject" and _request_needs_parent_approval(req_row):
                    reward_requests_df.loc[req_idx, "parent_approval_status"] = "Rejected"

                if coach_action == "Approve" and _request_needs_coach_approval(req_row):
                    reward_requests_df.loc[req_idx, "coach_approval_status"] = "Approved"
                    reward_requests_df.loc[req_idx, "coach_approved_at"] = now
                elif coach_action == "Reject" and _request_needs_coach_approval(req_row):
                    reward_requests_df.loc[req_idx, "coach_approval_status"] = "Rejected"

                req_row = reward_requests_df.loc[req_idx]
                parent_ready = (not _request_needs_parent_approval(req_row)) or str(req_row.get("parent_approval_status", "")) == "Approved"
                coach_ready = (not _request_needs_coach_approval(req_row)) or str(req_row.get("coach_approval_status", "")) == "Approved"
                rejected = str(req_row.get("parent_approval_status", "")) == "Rejected" or str(req_row.get("coach_approval_status", "")) == "Rejected"

                if rejected:
                    reward_requests_df.loc[req_idx, "request_status"] = "Rejected"
                    reward_requests_df.loc[req_idx, "redemption_status"] = "Closed"
                    reward_requests_df.loc[req_idx, "rejection_reason"] = rejection_reason.strip() or "Approval rejected"
                    _save_csv(REWARD_REQUESTS_CSV, reward_requests_df, REWARD_REQUEST_COLUMNS)
                    st.warning("Reward request rejected.")
                else:
                    if parent_ready and coach_ready:
                        reward_requests_df.loc[req_idx, "request_status"] = "Approved"
                    else:
                        reward_requests_df.loc[req_idx, "request_status"] = "Pending Approvals"

                    if redemption_action == "Mark Redeemed":
                        if not (parent_ready and coach_ready):
                            st.error("All required approvals must be complete before redemption.")
                        else:
                            reward_id = str(req_row.get("reward_id", ""))
                            inv_match = sponsor_inventory_df[sponsor_inventory_df["reward_id"].astype(str) == reward_id]
                            wallet_match = wallets_df[wallets_df["player_name"].astype(str) == str(req_row.get("player_name", ""))]

                            if inv_match.empty:
                                st.error("Sponsor inventory entry is missing for this reward.")
                            elif wallet_match.empty:
                                st.error("Player wallet is missing for this request.")
                            else:
                                inv_idx = inv_match.index[0]
                                wallet_idx = wallet_match.index[0]
                                remaining = _to_int(sponsor_inventory_df.loc[inv_idx, "remaining_inventory"], 0)
                                player_points = _to_int(wallets_df.loc[wallet_idx, "points_balance"], 0)
                                cost = _to_int(req_row.get("points_cost", 0), 0)

                                if remaining <= 0:
                                    st.error("Cannot redeem: sponsor inventory is empty.")
                                elif player_points < cost:
                                    st.error("Cannot redeem: player does not have enough points.")
                                else:
                                    sponsor_inventory_df.loc[inv_idx, "remaining_inventory"] = remaining - 1
                                    sponsor_inventory_df.loc[inv_idx, "updated_at"] = now
                                    wallets_df.loc[wallet_idx, "points_balance"] = player_points - cost
                                    wallets_df.loc[wallet_idx, "last_updated"] = now

                                    cert_id = str(uuid4())[:12]
                                    cert_row = {
                                        "certificate_id": cert_id,
                                        "request_id": req_row.get("request_id", ""),
                                        "player_name": req_row.get("player_name", ""),
                                        "reward_name": req_row.get("reward_name", ""),
                                        "sponsor_name": req_row.get("sponsor_name", ""),
                                        "certificate_text": _certificate_text(
                                            str(req_row.get("player_name", "")),
                                            str(req_row.get("reward_name", "")),
                                            str(req_row.get("sponsor_name", "")),
                                        ),
                                        "issued_at": now,
                                    }

                                    certificates_df = pd.concat([certificates_df, pd.DataFrame([cert_row])], ignore_index=True)
                                    reward_requests_df.loc[req_idx, "redemption_status"] = "Redeemed"
                                    reward_requests_df.loc[req_idx, "redeemed_at"] = now
                                    reward_requests_df.loc[req_idx, "certificate_id"] = cert_id
                                    reward_requests_df.loc[req_idx, "certificate_issued_at"] = now

                                    _save_csv(SPONSOR_INVENTORY_CSV, sponsor_inventory_df, SPONSOR_INVENTORY_COLUMNS)
                                    _save_csv(WALLETS_CSV, wallets_df, WALLET_COLUMNS)
                                    _save_csv(CERTIFICATES_CSV, certificates_df, CERTIFICATE_COLUMNS)
                                    st.success("Reward redeemed, inventory reduced, and digital certificate issued.")

                    _save_csv(REWARD_REQUESTS_CSV, reward_requests_df, REWARD_REQUEST_COLUMNS)

    st.markdown("### Reward Requests")
    if reward_requests_df.empty:
        st.info("No reward requests yet.")
    else:
        st.dataframe(reward_requests_df.sort_values("requested_at", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("### Digital Certificates")
    if certificates_df.empty:
        st.info("No certificates issued yet.")
    else:
        st.dataframe(certificates_df.sort_values("issued_at", ascending=False), use_container_width=True, hide_index=True)
