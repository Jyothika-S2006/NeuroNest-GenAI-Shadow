import cv2
import mediapipe as mp
import numpy as np
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class PoseAnalysis:
    is_sitting: bool
    is_slouching: bool
    is_pacing: bool
    is_inactive: bool
    posture_label: str
    confidence: float

@dataclass
class RoutineStatus:
    expected_activity: str
    actual_activity: str
    deviation_detected: bool
    deviation_message: str
    hours_inactive: float

@dataclass
class PipelineResult:
    pose: dict
    routine: dict
    risk_score: float
    risk_level: str
    alert: Optional[str]
    emotion_label: str
    timestamp: float
    landmarks_detected: bool

# ─── Pose Analyzer ────────────────────────────────────────────────────────────

class PoseAnalyzer:
    def __init__(self):
        self.pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        # Track position history for pacing detection
        self.position_history = deque(maxlen=30)  # last 30 frames
        self.shoulder_history = deque(maxlen=60)

    def analyze(self, frame: np.ndarray) -> tuple[Optional[PoseAnalysis], any]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)

        if not results.pose_landmarks:
            return None, results

        lm = results.pose_landmarks.landmark

        # Key landmarks
        nose        = lm[mp_pose.PoseLandmark.NOSE]
        l_shoulder  = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
        r_shoulder  = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
        l_hip       = lm[mp_pose.PoseLandmark.LEFT_HIP]
        r_hip       = lm[mp_pose.PoseLandmark.RIGHT_HIP]
        l_knee      = lm[mp_pose.PoseLandmark.LEFT_KNEE]
        r_knee      = lm[mp_pose.PoseLandmark.RIGHT_KNEE]

        mid_shoulder_y = (l_shoulder.y + r_shoulder.y) / 2
        mid_hip_y      = (l_hip.y + r_hip.y) / 2
        mid_knee_y     = (l_knee.y + r_knee.y) / 2
        mid_x          = (l_shoulder.x + r_shoulder.x) / 2

        # ── Sitting Detection ──
        # If hips and knees are close in y-axis (normalized), likely sitting
        hip_knee_diff = abs(mid_hip_y - mid_knee_y)
        is_sitting = hip_knee_diff < 0.15

        # ── Slouch Detection ──
        # Compare shoulder-to-hip angle with vertical
        spine_angle = abs(mid_shoulder_y - mid_hip_y)
        shoulder_width = abs(l_shoulder.x - r_shoulder.x)
        # Rounded shoulders = narrow width + forward lean
        is_slouching = shoulder_width < 0.15 or (nose.y > mid_shoulder_y + 0.05)
        self.shoulder_history.append(shoulder_width)

        # ── Pacing Detection ──
        self.position_history.append(mid_x)
        is_pacing = False
        if len(self.position_history) >= 20:
            positions = list(self.position_history)
            movement_range = max(positions) - min(positions)
            # Count direction changes
            changes = sum(1 for i in range(1, len(positions)-1)
                         if (positions[i]-positions[i-1]) * (positions[i+1]-positions[i]) < 0)
            is_pacing = movement_range > 0.25 and changes > 4

        # ── Posture Label ──
        if is_pacing:
            label = "Pacing"
            confidence = 0.82
        elif is_slouching and is_sitting:
            label = "Slouched Sitting"
            confidence = 0.88
        elif is_sitting:
            label = "Sitting"
            confidence = 0.91
        elif is_slouching:
            label = "Slouching"
            confidence = 0.79
        else:
            label = "Standing / Active"
            confidence = 0.85

        return PoseAnalysis(
            is_sitting=is_sitting,
            is_slouching=is_slouching,
            is_pacing=is_pacing,
            is_inactive=(is_sitting and not is_pacing),
            posture_label=label,
            confidence=confidence
        ), results

# ─── Routine Tracker ──────────────────────────────────────────────────────────

class RoutineTracker:
    # Simple time-based routine expectations
    ROUTINE_SCHEDULE = [
        (6,  8,  "Morning activity / exercise"),
        (8,  10, "Breakfast routine"),
        (10, 12, "Light activity / reading"),
        (12, 14, "Lunch & rest"),
        (14, 16, "Afternoon activity"),
        (16, 18, "Chai time / social"),
        (18, 20, "Evening walk / movement"),
        (20, 22, "Dinner & wind down"),
        (22, 6,  "Sleep / rest"),
    ]

    def __init__(self):
        self.inactive_since: Optional[float] = None
        self.last_active_time: float = time.time()
        self.INACTIVITY_THRESHOLD_MINUTES = 45  # alert after 45 mins

    def get_expected_activity(self) -> str:
        hour = time.localtime().tm_hour
        for start, end, activity in self.ROUTINE_SCHEDULE:
            if start <= end:
                if start <= hour < end:
                    return activity
            else:  # overnight
                if hour >= start or hour < end:
                    return activity
        return "Rest"

    def update(self, pose: Optional[PoseAnalysis]) -> RoutineStatus:
        now = time.time()
        expected = self.get_expected_activity()

        # Determine actual activity
        if pose is None:
            actual = "Not visible"
        elif pose.is_pacing:
            actual = "Pacing / Moving"
            self.last_active_time = now
            self.inactive_since = None
        elif pose.is_inactive:
            actual = "Sedentary / Sitting"
        else:
            actual = "Active / Standing"
            self.last_active_time = now
            self.inactive_since = None

        # Track inactivity duration
        if pose and pose.is_inactive and self.inactive_since is None:
            self.inactive_since = now

        hours_inactive = 0.0
        deviation = False
        deviation_msg = ""

        if self.inactive_since:
            minutes_inactive = (now - self.inactive_since) / 60
            hours_inactive = minutes_inactive / 60

            if minutes_inactive > self.INACTIVITY_THRESHOLD_MINUTES:
                deviation = True
                deviation_msg = f"Inactive for {int(minutes_inactive)} minutes — expected: {expected}"

        # Check time-based expectation vs actual
        hour = time.localtime().tm_hour
        if 16 <= hour < 18 and pose and pose.is_inactive and not deviation:
            deviation = True
            deviation_msg = "Chai time — no movement detected"

        return RoutineStatus(
            expected_activity=expected,
            actual_activity=actual,
            deviation_detected=deviation,
            deviation_message=deviation_msg,
            hours_inactive=round(hours_inactive, 2)
        )

# ─── Risk Scorer ──────────────────────────────────────────────────────────────

class RiskScorer:
    def __init__(self):
        self.score_history = deque(maxlen=10)

    def score(self, pose: Optional[PoseAnalysis], routine: RoutineStatus) -> tuple[float, str, Optional[str], str]:
        raw = 0.0

        if pose is None:
            raw += 20  # person not visible

        if pose:
            if pose.is_slouching:
                raw += 25
            if pose.is_pacing:
                raw += 20  # repetitive pacing = anxious
            if pose.is_inactive:
                raw += 15
            if pose.posture_label == "Slouched Sitting":
                raw += 10

        if routine.deviation_detected:
            raw += 30
        if routine.hours_inactive > 1:
            raw += min(routine.hours_inactive * 10, 30)

        raw = min(raw, 100)
        self.score_history.append(raw)
        score = np.mean(list(self.score_history))

        # Risk level
        if score < 25:
            level = "Low"
            emotion = "Calm / Content"
            alert = None
        elif score < 50:
            level = "Moderate"
            emotion = "Possibly Restless"
            alert = "Gentle check-in recommended" if routine.deviation_detected else None
        elif score < 75:
            level = "High"
            emotion = "Distressed / Isolated"
            alert = f"⚠️ Call Amma Now? {routine.deviation_message or 'Unusual behavior detected'}"
        else:
            level = "Critical"
            emotion = "Severely Isolated"
            alert = f"🚨 Immediate attention needed! {routine.deviation_message or 'Elder may need help'}"

        return round(score, 1), level, alert, emotion

# ─── Main Pipeline ────────────────────────────────────────────────────────────

class EmotionPipeline:
    def __init__(self):
        self.pose_analyzer  = PoseAnalyzer()
        self.routine_tracker = RoutineTracker()
        self.risk_scorer    = RiskScorer()
        self.frame_count    = 0

    def analyze_frame(self, frame: np.ndarray) -> dict:
        self.frame_count += 1

        # 1. Pose Analysis
        pose, mp_results = self.pose_analyzer.analyze(frame)

        # 2. Routine Tracking
        routine = self.routine_tracker.update(pose)

        # 3. Risk Scoring
        risk_score, risk_level, alert, emotion_label = self.risk_scorer.score(pose, routine)

        result = PipelineResult(
            pose=asdict(pose) if pose else {
                "is_sitting": False, "is_slouching": False,
                "is_pacing": False, "is_inactive": False,
                "posture_label": "Not detected", "confidence": 0.0
            },
            routine=asdict(routine),
            risk_score=risk_score,
            risk_level=risk_level,
            alert=alert,
            emotion_label=emotion_label,
            timestamp=time.time(),
            landmarks_detected=pose is not None
        )

        return asdict(result)
