"""
ElevenLabs 나레이션 생성 (쇼핑쇼츠용 기본값 고정)

.env 파일에서 ELEVENLABS_API_KEY를 읽는다.
"""

import os
import subprocess

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_VOICE_ID = "5I7B1di44aCL15NkP0jn"  # Kanna - Calm & Friendly (한국어 여성)
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.52,
    "similarity_boost": 0.57,
    "style": 0.10,
    "speed": 1.19,
    "use_speaker_boost": True,
}


def _load_api_key() -> str:
    env_path = os.path.join(SCRIPT_DIR, ".env")
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.strip().split("=", 1)[1]
    raise RuntimeError(".env에서 ELEVENLABS_API_KEY를 찾지 못함")


def generate_narration(
    script_text: str,
    out_path: str,
    voice_id: str = DEFAULT_VOICE_ID,
    voice_settings: dict = None,
    trim_silence: bool = True,
) -> str:
    """대본을 나레이션 mp3로 만든다. trim_silence=True면 문장 사이 긴 무음 구간을
    ffmpeg로 압축해서 시청 이탈로 이어질 만한 공백을 줄인다."""
    key = _load_api_key()
    settings = dict(DEFAULT_VOICE_SETTINGS)
    if voice_settings:
        settings.update(voice_settings)

    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": script_text, "model_id": DEFAULT_MODEL_ID, "voice_settings": settings},
    )
    r.raise_for_status()

    if not trim_silence:
        with open(out_path, "wb") as f:
            f.write(r.content)
        return out_path

    raw_path = out_path + ".raw.mp3"
    with open(raw_path, "wb") as f:
        f.write(r.content)
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw_path,
         "-af", "silenceremove=stop_periods=-1:stop_duration=0.08:stop_threshold=-35dB:stop_silence=0.02",
         out_path, "-loglevel", "error"],
        check=True,
    )
    os.remove(raw_path)
    return out_path
