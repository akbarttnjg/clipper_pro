"""
Stage 2 - AI clip selector.

Purpose:
    Analyze Whisper word-level transcript using Ollama LLM and return
    high quality standalone short-form video clips.

Contract:
    Input:
        transcript = {
            "words": [
                {
                    "word": str,
                    "start": float,
                    "end": float
                }
            ],
            "duration": float
        }

    Output:
        [
            {
                "start": float,
                "end": float,
                "title": str,
                "hook": str,
                "reason": str,
                "score": int
            }
        ]

Designed for:
    - faster-whisper
    - Ollama
    - Qwen3 models
    - Indonesian content
"""


from __future__ import annotations


import json
import math
import re
from typing import Any, Dict, List, Optional


import requests


from .config import Config



# ============================================================
# CONSTANTS
# ============================================================


# Transcript chunk size.
# Large enough for context, small enough for local 8B models.
_CHUNK_WORDS: int = 1200


# Overlap avoids losing clips near chunk boundaries.
_CHUNK_OVERLAP_WORDS: int = 120


# Words per timestamp line sent to LLM.
_BLOCK_WORDS: int = 16


# Ollama timeout.
_OLLAMA_TIMEOUT_S: int = 900


# Maximum LLM response size.
_MAX_RESPONSE_TOKENS: int = 900



# Titles that indicate low quality output.
# Qwen sometimes returns generic names.
_GENERIC_TITLES = {
    "clip",
    "video",
    "cuplikan",
    "potongan",
    "bagian",
    "highlight",
    "short",
    "untitled",
}



# Opening words that often indicate weak hooks.
_WEAK_OPENERS = {
    "jadi",
    "nah",
    "oke",
    "baik",
    "sebenarnya",
    "pertama",
    "gitu",
    "begini",
}



# ============================================================
# WORD VALIDATION
# ============================================================


def _safe_words(
    transcript: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Validate Whisper word timestamps.

    Removes:
        - empty tokens
        - invalid timestamps
        - malformed entries

    Returns:
        Sorted word list.
    """

    output: List[Dict[str, Any]] = []


    raw_words = transcript.get(
        "words",
        []
    )


    if not isinstance(
        raw_words,
        list
    ):
        return output


    for item in raw_words:

        if not isinstance(
            item,
            dict
        ):
            continue


        try:

            word = str(
                item["word"]
            ).strip()


            start = float(
                item["start"]
            )


            end = float(
                item["end"]
            )


        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            continue



        if not word:
            continue


        if start < 0:
            continue


        if end <= start:
            continue



        output.append(
            {
                "word": word,
                "start": start,
                "end": end,
            }
        )


    output.sort(
        key=lambda x: x["start"]
    )


    return output



# ============================================================
# TRANSCRIPT CHUNKING
# ============================================================


def _make_chunks(
    words: List[Dict[str, Any]],
    chunk_words: int = _CHUNK_WORDS,
    overlap_words: int = _CHUNK_OVERLAP_WORDS,
) -> List[List[Dict[str, Any]]]:
    """
    Split long transcripts into overlapping chunks.

    Example:

        chunk 1:
            word 0 - 1200

        chunk 2:
            word 1080 - 2280

    Overlap prevents losing important moments.
    """


    if not words:
        return []


    if chunk_words <= 0:
        raise ValueError(
            "chunk_words must be > 0"
        )


    if (
        overlap_words < 0
        or overlap_words >= chunk_words
    ):
        raise ValueError(
            "invalid overlap size"
        )


    if len(words) <= chunk_words:
        return [
            words
        ]



    chunks: List[
        List[Dict[str, Any]]
    ] = []


    step = (
        chunk_words
        -
        overlap_words
    )


    index = 0


    while index < len(words):

        end = min(
            len(words),
            index + chunk_words
        )


        chunk = words[index:end]


        if chunk:
            chunks.append(
                chunk
            )


        if end >= len(words):
            break


        index += step



    return chunks



# ============================================================
# TIMESTAMP FORMATTER
# ============================================================


def _timestamped_text(
    words: List[Dict[str, Any]]
) -> str:
    """
    Convert words into compact timestamp transcript.

    Example:

    [10.20-15.30] belajar investasi itu bukan soal kaya cepat
    """


    lines: List[str] = []


    for index in range(
        0,
        len(words),
        _BLOCK_WORDS,
    ):

        block = words[
            index:index + _BLOCK_WORDS
        ]


        if not block:
            continue



        start = float(
            block[0]["start"]
        )


        end = float(
            block[-1]["end"]
        )


        text = " ".join(
            str(
                item["word"]
            )
            for item in block
        )


        lines.append(
            f"[{start:.2f}-{end:.2f}] {text}"
        )


    return "\n".join(lines)



# ============================================================
# PROMPT BUILDER
# ============================================================


def _system_prompt(
    cfg: Config,
    requested: int,
) -> str:
    """
    Strict Qwen instruction.

    Prevents previous failure:
        summary/key_points output instead of clips.
    """


    schema = {
        "clips": [
            {
                "start": 120.5,
                "end": 155.0,
                "title": "Judul clip",
                "hook": "Kalimat hook",
                "reason": "Alasan clip bernilai",
                "score": 90,
            }
        ]
    }


    return (
        "Anda adalah editor video short-form profesional "
        "berbahasa Indonesia.\n\n"

        "Tugas utama:\n"
        "Pilih bagian transcript yang paling bernilai "
        "untuk TikTok, Shorts, dan Reels.\n\n"

        "WAJIB:\n"
        "- Output JSON saja.\n"
        "- Gunakan key utama bernama clips.\n"
        "- Start dan end harus berupa detik.\n\n"

        "DILARANG:\n"
        "- membuat summary\n"
        "- membuat key_points\n"
        "- membuat insight\n"
        "- membuat transcript ulang\n"
        "- membuat audience analysis\n\n"

        f"Pilih maksimal {requested} clip.\n"

        f"Durasi setiap clip "
        f"{cfg.min_clip_s:.0f}-{cfg.max_clip_s:.0f} detik.\n\n"

        "Prioritas clip:\n"
        "- insight kuat\n"
        "- cerita menarik\n"
        "- pembelajaran\n"
        "- kesalahan yang bisa dipelajari\n"
        "- fakta mengejutkan\n"
        "- strategi praktis\n\n"

        "Schema contoh:\n"

        + json.dumps(
            schema,
            ensure_ascii=False,
        )
    )

# ============================================================
# OLLAMA REQUEST
# ============================================================


def _call_ollama(
    cfg: Config,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> str:
    """
    Send request to local Ollama.

    Uses JSON mode and disables Qwen thinking mode because
    reasoning output can break strict JSON parsing.
    """


    payload: Dict[str, Any] = {

        "model": cfg.model,

        "system": system_prompt,

        "prompt": user_prompt,

        "stream": False,

        "format": "json",

        "think": False,


        "options": {

            "temperature": temperature,

            "top_p": 0.9,

            "num_ctx": 4096,

            "num_predict": _MAX_RESPONSE_TOKENS,
        },
    }



    response = requests.post(
        f"{cfg.ollama_url.rstrip('/')}/api/generate",
        json=payload,
        timeout=_OLLAMA_TIMEOUT_S,
    )


    response.raise_for_status()


    data = response.json()


    result = data.get(
        "response",
        ""
    )


    if not isinstance(
        result,
        str,
    ):
        return ""


    return result.strip()



# ============================================================
# JSON PARSER
# ============================================================


def _parse_json_object(
    raw: str
) -> Dict[str, Any]:
    """
    Parse JSON from LLM output.

    Handles:

    1. pure JSON
    2. JSON surrounded by text
    3. JSON list output
    """


    if not raw:
        return {}



    text = raw.strip()



    try:

        data = json.loads(
            text
        )


        if isinstance(
            data,
            dict,
        ):
            return data


        if isinstance(
            data,
            list,
        ):
            return {
                "clips": data
            }


    except json.JSONDecodeError:
        pass



    decoder = json.JSONDecoder()



    for index, char in enumerate(text):

        if char not in "{[":
            continue


        try:

            data, _ = decoder.raw_decode(
                text[index:]
            )


        except json.JSONDecodeError:

            continue



        if isinstance(
            data,
            dict,
        ):

            return data



        if isinstance(
            data,
            list,
        ):

            return {
                "clips": data
            }



    return {}



# ============================================================
# QUALITY HELPERS
# ============================================================


def _quality_penalty(
    title: str,
    hook: str,
) -> int:
    """
    Reduce score for weak openings.

    Example:

        "Jadi teman-teman..."
        "Nah sebenarnya..."

    are usually poor short-video hooks.
    """


    text = (
        f"{title} {hook}"
    ).lower().strip()



    penalty = 0



    for word in _WEAK_OPENERS:

        if text.startswith(word):

            penalty += 5



    return penalty



# ============================================================
# NORMALIZE + QUALITY GATE
# ============================================================


def _normalize_candidates(
    raw_clips: Any,
    duration: float,
    cfg: Config,
) -> List[Dict[str, Any]]:
    """
    Validate and filter LLM generated clips.

    New quality gates:

    - reject generic titles
    - reject empty hooks
    - reject weak metadata
    - adjust fake high scores
    """


    if not isinstance(
        raw_clips,
        list,
    ):
        return []



    output: List[
        Dict[str, Any]
    ] = []



    for item in raw_clips:


        if not isinstance(
            item,
            dict,
        ):
            continue



        try:

            start = float(
                item["start"]
            )

            end = float(
                item["end"]
            )


        except (
            KeyError,
            TypeError,
            ValueError,
        ):

            continue



        start = max(
            0.0,
            min(
                start,
                duration,
            )
        )


        end = max(
            0.0,
            min(
                end,
                duration,
            )
        )



        if end <= start:

            continue



        clip_duration = (
            end
            -
            start
        )



        if clip_duration < cfg.min_clip_s:

            continue



        if clip_duration > cfg.max_clip_s:

            end = (
                start
                +
                cfg.max_clip_s
            )



        title = str(
            item.get(
                "title",
                "",
            )
        ).strip()



        hook = str(
            item.get(
                "hook",
                "",
            )
        ).strip()



        reason = str(
            item.get(
                "reason",
                "",
            )
        ).strip()



        # Limit output size.

        title = title[:60]

        hook = hook[:100]

        reason = reason[:220]



        # ----------------------------
        # QUALITY GATE
        # ----------------------------


        if not title:

            continue



        if title.lower() in _GENERIC_TITLES:

            continue



        if len(title) < 8:

            continue



        if len(hook) < 15:

            continue



        if len(reason) < 5:

            continue



        try:

            score_value = int(
                float(
                    item.get(
                        "score",
                        50,
                    )
                )
            )


        except (
            TypeError,
            ValueError,
        ):

            score_value = 50



        score_value = max(
            0,
            min(
                100,
                score_value,
            )
        )



        score_value -= _quality_penalty(
            title,
            hook,
        )



        score_value = max(
            0,
            score_value,
        )



        output.append(
            {
                "start": round(
                    start,
                    2,
                ),

                "end": round(
                    end,
                    2,
                ),

                "title": title,

                "hook": hook,

                "reason": reason,

                "score": score_value,
            }
        )



    return output



# ============================================================
# CHUNK REQUEST
# ============================================================


def _request_chunk_candidates(
    chunk: List[Dict[str, Any]],
    cfg: Config,
    requested: int,
    chunk_index: int,
    chunk_count: int,
) -> List[Dict[str, Any]]:
    """
    Request clip candidates from one transcript chunk.

    Retry once with stricter instruction if Qwen returns invalid output.
    """


    chunk_start = float(
        chunk[0]["start"]
    )


    chunk_end = float(
        chunk[-1]["end"]
    )



    user_prompt = (
        f"Bagian transcript "
        f"{chunk_index}/{chunk_count}\n\n"

        f"Rentang waktu:\n"
        f"{chunk_start:.2f}"
        "-"
        f"{chunk_end:.2f} detik\n\n"

        "Transcript:\n"

        +
        _timestamped_text(
            chunk
        )
    )



    system_prompt = _system_prompt(
        cfg,
        requested,
    )



    for attempt in range(2):

        prompt = user_prompt


        if attempt == 1:

            prompt = (
                "OUTPUT SEBELUMNYA SALAH.\n"
                "Kembalikan hanya JSON clips.\n"
                "Jangan membuat summary.\n\n"
                +
                user_prompt
            )



        raw = _call_ollama(
            cfg,
            system_prompt,
            prompt,
            temperature=(
                0.15
                +
                (
                    attempt
                    *
                    0.05
                )
            ),
        )



        parsed = _parse_json_object(
            raw
        )



        candidates = _normalize_candidates(
            parsed.get(
                "clips",
                [],
            ),
            chunk_end,
            cfg,
        )



        valid = [
            c
            for c in candidates
            if (
                c["start"]
                >=
                chunk_start - 1
            )
            and (
                c["end"]
                <=
                chunk_end + 1
            )
        ]



        if valid:

            print(
                f"[score] chunk "
                f"{chunk_index}/{chunk_count}: "
                f"{len(valid)} kandidat valid"
            )

            return valid



        print(
            f"[score] chunk "
            f"{chunk_index}/{chunk_count}: "
            "tidak ada kandidat valid"
        )



    return []

# ============================================================
# OVERLAP / RANKING
# ============================================================


def _overlap_ratio(
    first: Dict[str, Any],
    second: Dict[str, Any],
) -> float:
    """
    Calculate temporal overlap between two clips.
    """


    overlap = max(
        0.0,
        min(
            first["end"],
            second["end"],
        )
        -
        max(
            first["start"],
            second["start"],
        )
    )


    if overlap <= 0:

        return 0.0



    first_length = max(
        0.001,
        first["end"] - first["start"],
    )


    second_length = max(
        0.001,
        second["end"] - second["start"],
    )


    return (
        overlap
        /
        min(
            first_length,
            second_length,
        )
    )



def _dedupe_and_rank(
    clips: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    """
    Rank clips by score and remove duplicates.
    """


    ranked = sorted(
        clips,
        key=lambda x: (
            x["score"],
            x["end"] - x["start"],
        ),
        reverse=True,
    )



    selected: List[
        Dict[str, Any]
    ] = []



    for clip in ranked:


        duplicated = any(
            _overlap_ratio(
                clip,
                existing,
            )
            >= 0.45

            for existing in selected
        )


        if duplicated:

            continue



        selected.append(
            clip
        )



        if len(selected) >= limit:

            break



    return selected



# ============================================================
# FALLBACK
# ============================================================


def _nearest_word_index(
    words: List[Dict[str, Any]],
    timestamp: float,
) -> int:
    """
    Find closest word index.
    """


    best_index = 0

    best_distance = float(
        "inf"
    )


    for index, word in enumerate(words):

        distance = abs(
            word["start"]
            -
            timestamp
        )


        if distance < best_distance:

            best_distance = distance

            best_index = index



    return best_index



def _heuristic_fallback(
    words: List[Dict[str, Any]],
    duration: float,
    cfg: Config,
) -> List[Dict[str, Any]]:
    """
    Emergency fallback.

    Used only when Ollama cannot return valid clips.
    """


    if not words:

        return []



    target_duration = max(
        cfg.min_clip_s,
        min(
            cfg.max_clip_s,
            30.0,
        ),
    )



    result: List[
        Dict[str, Any]
    ] = []



    for index in range(
        cfg.num_clips
    ):


        ratio = (
            index + 1
        ) / (
            cfg.num_clips + 1
        )



        center = (
            duration
            *
            ratio
        )



        start = max(
            0.0,
            center
            -
            target_duration / 2,
        )


        end = min(
            duration,
            start
            +
            target_duration,
        )



        result.append(
            {
                "start": round(
                    start,
                    2,
                ),

                "end": round(
                    end,
                    2,
                ),

                "title": (
                    f"Pembahasan "
                    f"menarik {index+1}"
                ),

                "hook": (
                    "Bagian penting "
                    "dari pembahasan"
                ),

                "reason": (
                    "Fallback karena "
                    "model tidak memberikan "
                    "clip valid."
                ),

                "score": 40,
            }
        )



    return result



# ============================================================
# PUBLIC FUNCTION
# ============================================================


def score(
    transcript: Dict[str, Any],
    cfg: Config,
) -> List[Dict[str, Any]]:
    """
    Main entry point used by pipeline.py.

    Input:
        Whisper transcript.

    Output:
        Ranked valid clips.
    """


    words = _safe_words(
        transcript
    )


    if not words:

        return []



    try:

        duration = float(
            transcript.get(
                "duration",
                words[-1]["end"],
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        duration = words[-1]["end"]



    duration = max(
        duration,
        words[-1]["end"],
    )



    chunks = _make_chunks(
        words
    )


    if not chunks:

        return []



    print(
        "[score]"
        f" model={cfg.model}"
        f" words={len(words)}"
        f" duration={duration:.2f}s"
        f" chunks={len(chunks)}"
        f" requested={cfg.num_clips}"
    )



    candidates: List[
        Dict[str, Any]
    ] = []



    for index, chunk in enumerate(
        chunks,
        start=1,
    ):


        try:

            found = _request_chunk_candidates(
                chunk,
                cfg,
                max(
                    1,
                    cfg.num_clips,
                ),
                index,
                len(chunks),
            )


            candidates.extend(
                found
            )



        except requests.RequestException as exc:

            print(
                "[score] Ollama error:",
                exc,
            )



    selected = _dedupe_and_rank(
        candidates,
        cfg.num_clips,
    )



    if selected:


        print(
            f"[score] "
            f"{len(selected)} "
            "clip final dipilih"
        )


        for clip in selected:

            print(
                clip
            )


        return selected



    print(
        "[score] "
        "menggunakan fallback"
    )



    return _heuristic_fallback(
        words,
        duration,
        cfg,
    )



# ============================================================
# SANITY TEST
# ============================================================


def _self_test() -> None:
    """
    Test without Ollama and video.
    """


    words: List[
        Dict[str, Any]
    ] = []



    for index in range(
        2500
    ):

        start = index * 0.4


        words.append(
            {
                "word": (
                    f"kata{index}"
                ),

                "start": start,

                "end": start + 0.3,
            }
        )



    transcript = {

        "words": words,

        "duration": 1200.0,
    }



    cfg = Config(
        num_clips=3,
        min_clip_s=15.0,
        max_clip_s=60.0,
    )



    clean = _safe_words(
        transcript
    )


    chunks = _make_chunks(
        clean
    )


    fallback = _heuristic_fallback(
        clean,
        1200.0,
        cfg,
    )



    assert len(clean) == 2500


    assert len(chunks) > 1


    assert len(fallback) == 3



    print(
        "score.py sanity check: OK"
    )


    print(
        fallback
    )



if __name__ == "__main__":

    _self_test()
