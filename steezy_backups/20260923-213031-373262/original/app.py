"""Web server: drag a video onto the page, watch it clip, download the results."""
from __future__ import annotations
import json
import shutil
import threading
import uuid
import math
from dataclasses import replace
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

# load a local .env (e.g. PEXELS_API_KEY) BEFORE importing config, which snapshots env vars
load_dotenv()
load_dotenv(Path(__file__).parent / ".env.pro", override=True)

from clipper.config import Config, validate_overrides, validate_brand
from clipper import pipeline

BRAND_FILE = Path("brand.json")


def _load_brand() -> dict:
    try:
        return validate_brand(json.loads(BRAND_FILE.read_text(encoding="utf-8")))
    except Exception:
        return {}


base_cfg = replace(Config(), **_load_brand())   # apply saved brand defaults at startup
app = FastAPI(title="clipper")
STATIC = Path(__file__).parent / "static"
UPLOADS = Path("uploads"); UPLOADS.mkdir(exist_ok=True)

# in-memory, UI-facing job store: id -> {status, percent, message, clips, error}
JOBS: dict[str, dict] = {}
# internal per-job state for single-clip regeneration (not sent to the UI / not JSON)
JOB_STATE: dict[str, dict] = {}
PROCESS_LOCK = threading.Lock()


def _run(job_id: str, path: str, cfg: Config) -> None:
    with PROCESS_LOCK:
        JOBS[job_id]["status"] = "running"
        _process(job_id, path, cfg)


def _process(job_id: str, path: str, cfg: Config) -> None:
    def progress(percent: int, message: str) -> None:
        JOBS[job_id].update(percent=percent, message=message)
    try:
        transcript, scored = pipeline.analyze(path, cfg, progress)
        # keep the slow-stage results so a single clip can be re-rendered later
        JOB_STATE[job_id] = {"transcript": transcript, "scored": scored, "media": path, "cfg": cfg, "edits": {}}
        JOBS[job_id]["clips"] = []   # filled incrementally so the UI shows clips as they finish
        pipeline.render_all(path, transcript, scored, cfg, progress,
                            on_clip=lambda r: JOBS[job_id]["clips"].append(r))
        JOBS[job_id].update(status="done", percent=100)
    except Exception as exc:  # surface the real reason to the UI
        JOBS[job_id].update(status="error", error=str(exc))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...),
                 background: UploadFile = File(None),
                 aspect: str = Form("9:16"),
                 caption_style: str = Form("editorial"),
                 processing_mode: str = Form("auto"),
                 caption_position: str = Form("auto"),
                 language: str = Form("id"),
                 layout: str = Form("fill"),
                 length: str = Form("auto"),
                 trim: str = Form("0"),
                 broll: str = Form("0"),
                 num_clips: str = Form(None)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    job_id = uuid.uuid4().hex[:12]
    dest = UPLOADS / f"{job_id}-{Path(file.filename).name}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    bg_path = ""
    if background is not None and background.filename:
        bg_dest = UPLOADS / f"{job_id}-bg-{Path(background.filename).name}"
        with bg_dest.open("wb") as out:
            shutil.copyfileobj(background.file, out)
        bg_path = str(bg_dest)
    job_cfg = replace(base_cfg, background_path=bg_path, job_id=job_id,
                      work_dir=str(Path(base_cfg.work_dir) / job_id), **validate_overrides(
        {"aspect": aspect, "caption_style": caption_style, "layout": layout,
         "processing_mode": processing_mode, "caption_position": caption_position, "language": language,
         "length": length, "trim": trim, "broll": broll, "num_clips": num_clips}))
    JOBS[job_id] = {"status": "queued", "percent": 0, "message": "Queued — menunggu proses sebelumnya",
                    "clips": [], "error": None}
    threading.Thread(target=_run, args=(job_id, str(dest), job_cfg), daemon=True).start()
    return JSONResponse({"job": job_id})


@app.get("/api/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    return JSONResponse(job)


@app.post("/api/regenerate/{job_id}/{idx}")
def regenerate(job_id: str, idx: int,
               aspect: str = Form("9:16"),
               caption_style: str = Form("editorial"),
               caption_position: str = Form("auto"),
               layout: str = Form("fill"),
               trim: str = Form("0")) -> JSONResponse:
    st, job = JOB_STATE.get(job_id), JOBS.get(job_id)
    if not st or not job:
        raise HTTPException(404, "Unknown job.")
    if idx < 0 or idx >= len(st["scored"]):
        raise HTTPException(404, "Unknown clip.")
    cfg = replace(st["cfg"], **validate_overrides(
        {"aspect": aspect, "caption_style": caption_style, "layout": layout, "trim": trim,
         "caption_position": caption_position}))
    clip = st["scored"][idx]
    if not PROCESS_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Tunggu proses video yang sedang berjalan.")
    try:
        words = st.get("edits", {}).get(idx, st["transcript"]["words"])
        res = pipeline.render_clip(st["media"], words, clip, pipeline.clip_name(clip, idx), cfg)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    finally:
        PROCESS_LOCK.release()
    if idx < len(job.get("clips", [])):
        job["clips"][idx] = res
    return JSONResponse(res)


@app.get("/api/editor/{job_id}/{idx}")
def editor_get(job_id: str, idx: int):
    st = JOB_STATE.get(job_id)
    if not st or not 0 <= idx < len(st["scored"]):
        raise HTTPException(404, "Clip tidak ditemukan.")
    c = st["scored"][idx]
    words = st.get("edits", {}).get(idx, st["transcript"]["words"])
    return {"clip": c, "duration": st["transcript"]["duration"],
            "words": [w for w in words if w["end"] > c["start"] and w["start"] < c["end"]]}


@app.post("/api/editor/{job_id}/{idx}")
def editor_save(job_id: str, idx: int, data: dict = Body(...)):
    st, job = JOB_STATE.get(job_id), JOBS.get(job_id)
    if not st or not job or not 0 <= idx < len(st["scored"]):
        raise HTTPException(404, "Clip tidak ditemukan.")
    if job["status"] not in ("done", "error"):
        raise HTTPException(409, "Tunggu proses selesai sebelum mengedit.")
    if not PROCESS_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Tunggu proses video yang sedang berjalan.")
    try:
        source_duration = st["transcript"]["duration"]
        start, end = float(data["start"]), float(data["end"])
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= source_duration + .05:
            raise ValueError("Batas clip di luar durasi video.")
        raw = data["words"]
        if not isinstance(raw, list) or not raw or len(raw) > 10000:
            raise ValueError("Daftar kata tidak valid.")
        words, previous = [], -1.
        for w in raw:
            a, b, text = float(w["start"]), float(w["end"]), str(w["word"]).strip()
            if not text or len(text) > 120 or not all(math.isfinite(v) for v in (a, b)) or not 0 <= a < b <= source_duration + .05 or a < previous:
                raise ValueError("Periksa urutan waktu dan teks setiap kata.")
            words.append({"word": text, "start": a, "end": b})
            previous = a
        keys = data.get("keywords", [])
        if not isinstance(keys, list):
            raise ValueError("Keywords harus berupa daftar.")
        c = {**st["scored"][idx], "start": start, "end": end,
             "keywords": [str(k)[:80] for k in keys[:20]], "selection_source": "reviewed"}
        # Keep source words outside the original clip so extending boundaries still works.
        old = st["scored"][idx]
        existing = st.get("edits", {}).get(idx, st["transcript"]["words"])
        outside = [w for w in existing if w["end"] <= old["start"] or w["start"] >= old["end"]]
        combined = sorted(outside + words, key=lambda w: w["start"])
        st.setdefault("edits", {})[idx] = combined
        st["scored"][idx] = c
        p = Path(st["cfg"].work_dir) / f"edit-{idx}.json"
        p.write_text(json.dumps({"clip": c, "words": combined}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        PROCESS_LOCK.release()


@app.get("/api/brand")
def get_brand() -> JSONResponse:
    return JSONResponse({"accent_hex": base_cfg.accent_hex,
                         "caption_style": base_cfg.caption_style,
                         "font_name": base_cfg.font_name})


@app.post("/api/brand")
def set_brand(accent_hex: str = Form(...), caption_style: str = Form(...),
              font_name: str = Form(...)) -> JSONResponse:
    global base_cfg
    v = validate_brand({"accent_hex": accent_hex, "caption_style": caption_style,
                        "font_name": font_name})
    BRAND_FILE.write_text(json.dumps(v), encoding="utf-8")
    base_cfg = replace(base_cfg, **v)
    return JSONResponse({"ok": True, **v})


@app.get("/clips/{name}")
def clip(name: str) -> FileResponse:
    path = Path(base_cfg.out_dir) / Path(name).name
    if not path.exists():
        raise HTTPException(404, "Clip not found.")
    return FileResponse(path, media_type="video/mp4")


if __name__ == "__main__":
    print("clipper -> http://localhost:8765   (model: %s)" % base_cfg.model)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
