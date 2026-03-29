# NeuroNest AI Pipeline — Setup Guide for Replit

## Files to add to your Replit project

```
your-replit/
├── main.py              ← FastAPI server + WebSocket endpoint
├── pipeline.py          ← All AI logic (MediaPipe + OpenCV)
├── requirements.txt     ← Python dependencies
├── .replit              ← Run config
├── pipeline_client.js   ← Drop into your frontend folder
└── test.html            ← Test page (optional)
```

---

## Step 1 — Add Python files

Copy `main.py`, `pipeline.py`, `requirements.txt`, `.replit` into the **root** of your Replit project.

---

## Step 2 — Install dependencies

In the Replit Shell tab, run:
```bash
pip install -r requirements.txt
```

Or just click **Run** — Replit will auto-install from requirements.txt.

---

## Step 3 — Start the backend

Click **Run** in Replit. You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Your WebSocket endpoint will be live at:
```
ws://YOUR-REPLIT-URL:8000/ws/analyze
```

---

## Step 4 — Connect your existing frontend UI

Copy `pipeline_client.js` into your frontend folder, then add this to your UI code:

### If your frontend is plain HTML/JS:
```html
<script type="module">
  import { NeuroPipeline, formatResult, riskColor } from './pipeline_client.js'

  const pipeline = new NeuroPipeline()

  pipeline.onResult = (raw) => {
    const d = formatResult(raw)
    // d.posture       → "Sitting" / "Pacing" / "Slouching"
    // d.riskScore     → 0-100
    // d.riskLevel     → "Low" / "Moderate" / "High" / "Critical"
    // d.emotion       → "Calm" / "Distressed" etc.
    // d.deviation     → true/false
    // d.deviationMsg  → "Inactive for 47 minutes..."
    // d.alert         → "⚠️ Call Amma Now?" or null
    
    // Update your UI here!
    document.getElementById('your-risk-display').textContent = d.riskScore
  }

  pipeline.onAlert = (alert) => {
    // Show alert popup in your UI
    showNotification(alert)
  }

  pipeline.start()  // starts webcam + connects to AI
</script>
```

### If your frontend is React:
```jsx
import { useEffect, useRef } from 'react'
import { NeuroPipeline, formatResult } from './pipeline_client.js'

export function usePipeline(onResult) {
  const pipelineRef = useRef(null)

  useEffect(() => {
    const p = new NeuroPipeline()
    p.onResult = (raw) => onResult(formatResult(raw))
    p.start()
    pipelineRef.current = p
    return () => p.stop()
  }, [])

  return pipelineRef
}
```

---

## What the pipeline detects

| Output | What it means |
|--------|--------------|
| `posture_label` | Sitting / Pacing / Slouching / Standing |
| `is_pacing` | Repetitive side-to-side movement |
| `is_slouching` | Rounded shoulders / forward lean |
| `deviation_detected` | Broke expected routine for the time of day |
| `hours_inactive` | How long they've been sedentary |
| `risk_score` | 0–100 composite isolation risk |
| `risk_level` | Low / Moderate / High / Critical |
| `emotion_label` | Calm / Possibly Restless / Distressed / Isolated |
| `alert` | Text message to show family (null if all ok) |

---

## Routine schedule (auto-detects by time of day)

| Time | Expected |
|------|----------|
| 6–8am | Morning activity |
| 8–10am | Breakfast routine |
| 4–6pm | Chai time / social |
| 6–8pm | Evening walk |
| 10pm+ | Sleep / rest |

Alert triggers if elder is **inactive for 45+ minutes** during active hours.

---

## Troubleshooting

**"Camera error"** → Make sure your browser allows webcam access (HTTPS or localhost only)

**WebSocket won't connect** → Check that your backend is running on port 8000. In Replit, use the full `.repl.co` URL.

**MediaPipe not found** → Run `pip install mediapipe==0.10.14` in the Shell tab manually.
