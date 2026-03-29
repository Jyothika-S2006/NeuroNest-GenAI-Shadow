/**
 * NeuroNest AI Pipeline Client
 * Drop this into your existing Replit frontend.
 * 
 * Usage:
 *   import { NeuroPipeline } from './pipeline_client.js'
 *   const pipeline = new NeuroPipeline('ws://localhost:8000/ws/analyze')
 *   pipeline.onResult = (data) => updateYourUI(data)
 *   pipeline.start()
 */

export class NeuroPipeline {
  constructor(wsUrl = null) {
    // Auto-detect: use current host if no URL given
    const host = wsUrl || `ws://${window.location.hostname}:8000/ws/analyze`
    this.wsUrl = host
    this.ws = null
    this.stream = null
    this.videoEl = null
    this.canvas = document.createElement('canvas')
    this.ctx = this.canvas.getContext('2d')
    this.interval = null
    this.FPS = 5  // send 5 frames/sec — enough for behavior detection

    // ── Callbacks (override these) ──
    this.onResult    = (data) => console.log('Pipeline result:', data)
    this.onAlert     = (alert) => console.warn('ALERT:', alert)
    this.onConnected = () => console.log('Pipeline connected')
    this.onError     = (err) => console.error('Pipeline error:', err)
  }

  // ── Start everything ──────────────────────────────────────────────────────
  async start(videoElement = null) {
    this.videoEl = videoElement || await this._createVideoElement()
    await this._startCamera()
    this._connectWebSocket()
  }

  stop() {
    clearInterval(this.interval)
    if (this.ws) this.ws.close()
    if (this.stream) this.stream.getTracks().forEach(t => t.stop())
  }

  // ── Camera Setup ──────────────────────────────────────────────────────────
  async _startCamera() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' },
        audio: false
      })
      this.videoEl.srcObject = this.stream
      await this.videoEl.play()
      this.canvas.width  = 640
      this.canvas.height = 480
    } catch (err) {
      this.onError(`Camera error: ${err.message}`)
    }
  }

  _createVideoElement() {
    const v = document.createElement('video')
    v.style.display = 'none'
    document.body.appendChild(v)
    return v
  }

  // ── WebSocket ─────────────────────────────────────────────────────────────
  _connectWebSocket() {
    this.ws = new WebSocket(this.wsUrl)

    this.ws.onopen = () => {
      this.onConnected()
      this._startSendingFrames()
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.onResult(data)
        if (data.alert) this.onAlert(data.alert)
      } catch (e) {
        this.onError(`Parse error: ${e}`)
      }
    }

    this.ws.onerror = (e) => this.onError(e)
    this.ws.onclose = () => {
      clearInterval(this.interval)
      // Auto-reconnect after 3s
      setTimeout(() => this._connectWebSocket(), 3000)
    }
  }

  // ── Frame Sending ─────────────────────────────────────────────────────────
  _startSendingFrames() {
    this.interval = setInterval(() => {
      if (this.ws.readyState !== WebSocket.OPEN) return
      if (!this.videoEl.videoWidth) return

      this.ctx.drawImage(this.videoEl, 0, 0, 640, 480)
      const frame = this.canvas.toDataURL('image/jpeg', 0.7)

      this.ws.send(JSON.stringify({ type: 'frame', frame }))
    }, 1000 / this.FPS)
  }
}

// ─── Utility: Map pipeline result → UI-friendly object ───────────────────────
export function formatResult(data) {
  return {
    // Pose card
    posture:     data.pose?.posture_label    || 'Unknown',
    confidence:  Math.round((data.pose?.confidence || 0) * 100),
    isSitting:   data.pose?.is_sitting       || false,
    isSlouching: data.pose?.is_slouching     || false,
    isPacing:    data.pose?.is_pacing        || false,

    // Routine card
    expected:    data.routine?.expected_activity  || '—',
    actual:      data.routine?.actual_activity    || '—',
    deviation:   data.routine?.deviation_detected || false,
    deviationMsg: data.routine?.deviation_message || '',
    hoursInactive: data.routine?.hours_inactive   || 0,

    // Risk card
    riskScore:   data.risk_score  || 0,
    riskLevel:   data.risk_level  || 'Low',
    emotion:     data.emotion_label || 'Calm',

    // Alert
    alert:       data.alert || null,
    detected:    data.landmarks_detected || false,
  }
}

// ─── Utility: Risk level → color ─────────────────────────────────────────────
export function riskColor(level) {
  return {
    Low:      '#22c55e',
    Moderate: '#f59e0b',
    High:     '#ef4444',
    Critical: '#7c3aed',
  }[level] || '#6b7280'
}
