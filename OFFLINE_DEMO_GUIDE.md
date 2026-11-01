# 🌲 Salix Multilingual Offline Demo Guide

> **100% Hermetic / Offline Execution**  
> Tailored for Hackathon presentations and live judging with **zero internet connection**.  
> Full native support for **English**, **Roman Urdu (Latin script)**, and **Urdu (اردو نستعلیق / Nastaliq script)**.

---

## 🚀 1-Click Launch Instructions

You can start the entire demo offline using either the batch launcher or PowerShell:

### Option A: Windows Explorer (Easiest)
Simply double-click:
```text
run_demo_offline.bat
```
This starts both the FastAPI backend (`http://127.0.0.1:8010`) and the Next.js frontend (`http://localhost:3000`), and automatically opens your browser.

### Option B: PowerShell
Open a terminal in the project root and run:
```powershell
.\run_demo_offline.ps1
```

---

## 🎯 How Offline Execution Works

Under **Offline Mode (`SALIX_PROVIDER_MODE=mock`)**:
1. **No Cloud Dependency**: No outbound network requests are made to Alibaba Cloud Model Studio, OpenAI, Google Gemini, Deepgram, or Edge TTS.
2. **Local Diarization & ASR Twin**: Audio files uploaded through the UI are processed using `MockASR`. When paired with companion scripts (in `storage/samples/`), it outputs exact, timed, speaker-diarized conversations.
3. **Local Reasoning Twin**: Heuristic analysis models compute deal risks, objection classifications, narrative play candidates, and coaching plans completely in-memory.
4. **Deterministic Metrics Engine**: 100% pure Python arithmetic calculates talk ratios, customer patience latency, monologue runs, and open-ended question detection across English and Urdu.
5. **Local Persistent Database**: Pre-seeded SQLite database (`salix.db`) contains team reps, deals, plays, moments, and call history ready to explore.

---

## 🧪 Live Demo Flow for Judges (Step-by-Step)

### 1. Show the Calls Dashboard
* Navigate to `http://localhost:3000/calls`.
* Point out the pre-seeded calls showcasing Pakistani sales team workflows (reps like Bilal and colleagues).
* Notice the **Offline Twin** status badge indicating zero cloud dependencies.

### 2. Live Upload of Multilingual Calls
Navigate to `http://localhost:3000/upload`:
* Type the salesperson's name (for example `Bilal's Call`) and drop a file. There is no language to choose: it is detected from the transcript.
* Offline, the twin cannot listen, so it reads the script beside each bundled sample. Detection then runs on that text exactly as it would on a real transcript. Any other file gets the English stand-in.

#### Try uploading any of the pre-packaged sample files from `storage/samples/`:
| Audio File | Detected As | Description |
| :--- | :--- | :--- |
| `storage/samples/urdu_call.mp3` | **Urdu** | Native Nastaliq B2B sales call dealing with manual spreadsheet renewals, pricing objections, and budget authority. |
| `storage/samples/mixed_call.mp3` | **Roman Urdu** | Natural Karachi/Lahore sales floor dialogue switching seamlessly between Urdu and English. |
| `storage/samples/english_call.mp3` | **English** | SaaS renewal discovery call facing customer pushback and timeline objections. |

* Click **Upload & Analyze**.
* Watch the **7-stage ingest DAG pipeline** execute live on your machine:
  1. Store Audio (Local Storage)
  2. Transcribe (Speaker Diarization)
  3. One Script (Language Normalization)
  4. Speaker Roles (Rep vs Buyer Attribution)
  5. Deterministic Metrics Calculation
  6. Anatomy & Moment Extraction
  7. Deal Trajectory & Coaching Update

### 3. Explore the Call Analysis View
Click on any analyzed call to show the judges:
* **Waveform Audio Player**: Scrub through the audio locally without external streaming.
* **Bi-directional Transcript**:
  * Native Urdu text rendered with right-to-left (`dir="auto"`) alignment.
  * Roman Urdu and English rendered with matching typography.
* **Deterministic Metrics**:
  * **Talk Ratio**: Measured against the optimal 43% benchmark.
  * **Patience Latency**: Time rep waited before answering buyer objections.
  * **Longest Monologue**: Unbroken stretches of rep speech.
  * **Question Profile**: Categorized as open vs. closed inquiry.
* **Key Moments & Objections**: Identified objection categories (Price, Status Quo, Authority, Setup Risk) with direct clickable citations back to the transcript.

### 4. Live Interactive Dojo (Sales Simulator)
Navigate to `http://localhost:3000/dojo`:
* Select a practice persona (e.g., an operations head pushing back on budget).
* Select the language:
  * **English**
  * **Roman Urdu** (`en-PK` acoustic tuning)
  * **اردو (Urdu)** (Nastaliq script)
* Start the session:
  * Speak or type your sales pitch.
  * The AI persona holds its objection realistically and pushes back.
  * Live coach nudges trigger if you monologue or dodge an objection.
  * End the session to generate a comprehensive scorecard using the exact same metrics engine as real calls.

### 5. Playbook & Coaching Plan
Navigate to `http://localhost:3000/plays` and `http://localhost:3000/coaching`:
* Show how winning plays are synthesized from high-performing team calls.
* Show targeted drills prescribed to bridge reps' specific skill gaps (Discovery, Objection Handling, Deal Velocity).

---

## 🔍 Verifying the Test Suite (100% Passing)

To prove to the judges that the code is thoroughly tested and resilient:
```powershell
cd api
.\.venv\Scripts\python -m pytest -q
```
**Result**: **1,006 passed** tests with 0 failures!
