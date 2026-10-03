"""صوت «مساعد BotYalla»: تفريغ كلام المستخدم (STT) ونطق ردّ المساعد (TTS) بمفاتيح المنصة.

المتصفح هو المسار الأول دائماً (SpeechRecognition / speechSynthesis — مجاني وفوري)، وهذه
الوحدة احتياط له:
- **التفريغ**: متصفح بلا SpeechRecognition (Firefox) يسجّل مقطعاً ويرسله. Gemini يفهم العامية
  المصرية جيداً؛ Whisper على Groq ضعيف في العربية (قياسات 2026) فيبقى آخر خيار.
- **النطق**: صوت Gemini أطبع بكثير من أصوات أنظمة التشغيل العربية. لا طبقة مجانية له، فالمسار
  محدود الطول والمعدّل، وأي فشل يُرجع None فيعود المتصفح لصوته المحلي.

لا يُحفظ الصوت على القرص ولا يُسجَّل — يمرّ في الذاكرة إلى المزوّد ويُنسى. لا يرمي أبداً."""
import base64
import json as _json
import logging
import re
import struct
import urllib.error
import urllib.request
import uuid

import ai_agent

log = logging.getLogger("botyalla.voice")

MAX_AUDIO = 2 * 1024 * 1024          # ~60ث opus — أطول من أي سؤال منطوق
MAX_TTS_CHARS = 700
AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/aac")
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
# أسماء جوجل تتغيّر (سُحب gemini-2.5-flash فجأة 2026-09) — قائمة بالترتيب والأول المتاح يفوز
TTS_INTERACTIONS = ("gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts")
TTS_LEGACY = ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts")
TTS_VOICE = "Kore"
_STYLE = {"ar": "warm, friendly and clear Egyptian Arabic customer-support voice, natural relaxed pace",
          "en": "warm, friendly and clear customer-support voice, natural relaxed pace"}


def has_gemini(chain):
    return any(s.get("p") == "gemini" and s.get("key") for s in chain or [])


def can_transcribe(chain):
    return any(s.get("p") in ("gemini", "groq") and s.get("key") for s in chain or [])


def base_mime(mime):
    m = str(mime or "").split(";")[0].strip().lower()
    return m if m in AUDIO_TYPES else ""


# ------------------------------------------------------------------ التفريغ
_STT_PROMPT = ("Transcribe this voice message word for word, in the language spoken (often Egyptian Arabic, "
               "sometimes mixed with English product words). Output ONLY the transcript text — no quotes, no "
               "labels, no translation. If there is no intelligible speech, output nothing.")


def _gemini_stt(key, models, audio, mime):
    payload = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
        {"text": _STT_PROMPT}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 600}}
    for m in models:
        try:
            data = ai_agent._post_json(f"{GEMINI}/models/{m}:generateContent", payload,
                                       {"Content-Type": "application/json", "x-goog-api-key": key}, timeout=20)
        except ai_agent.AIError as e:
            if ai_agent._is_auth(e):
                return None
            continue
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return None


def _multipart(fields, file_field, filename, content, mime):
    b = "----by" + uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    out += (f"--{b}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{b}--\r\n".encode()
    return out, "multipart/form-data; boundary=" + b


def _groq_stt(key, audio, mime, lang):
    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3",
           "audio/aac": "m4a"}.get(mime, "wav")
    body, ctype = _multipart({"model": "whisper-large-v3-turbo", "language": "en" if lang == "en" else "ar",
                              "response_format": "json", "temperature": "0"}, "file", "voice." + ext, audio, mime)
    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=body, method="POST",
                                 headers={"Content-Type": ctype, "Authorization": "Bearer " + key,
                                          "User-Agent": ai_agent.USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return _json.loads(r.read().decode("utf-8")).get("text")
    except (urllib.error.URLError, OSError, ValueError) as e:
        log.warning("groq stt failed: %s", str(getattr(e, "code", "")) or type(e).__name__)
        return None


def transcribe(audio, mime, lang, chain):
    """نص ما قيل (مقصوص 1200 حرف) أو "" لصمت أو None لتعذّر التفريغ."""
    mime = base_mime(mime)
    if not audio or not mime or len(audio) > MAX_AUDIO:
        return None
    for s in chain or []:
        if not s.get("key"):
            continue
        try:
            if s["p"] == "gemini":
                txt = _gemini_stt(s["key"], ai_agent.GEMINI_FAST_MODELS, audio, mime)
            elif s["p"] == "groq":
                txt = _groq_stt(s["key"], audio, mime, lang)
            else:
                continue
        except Exception:
            log.exception("stt provider %s crashed", s.get("p"))
            continue
        if txt is not None:
            return re.sub(r"\s+", " ", txt).strip().strip('"«»')[:1200]
    return None


# ------------------------------------------------------------------ النطق
def speakable(text):
    """النص كما يُقال: بلا رموز تعبيرية ولا أقواس اقتباس ولا روابط ولا ترقيم قوائم."""
    t = re.sub(r"https?://\S+", "", str(text or ""))
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️‍]", "", t)
    t = re.sub(r"^\s*(\d+)[.)]\s*", r"\1، ", t, flags=re.M)
    t = t.replace("«", "").replace("»", "").replace("“", "").replace("”", "").replace("*", "")
    return re.sub(r"[ \t]+", " ", t).strip()[:MAX_TTS_CHARS]


def _wav(pcm, rate=24000):
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


def _find_audio(node):
    """أول (بايتات، نوع) صوتية في رد جوجل أياً كان شكله (interactions أو generateContent)."""
    if isinstance(node, dict):
        inline = node.get("inlineData") or node.get("inline_data")
        if isinstance(inline, dict) and inline.get("data"):
            return inline["data"], str(inline.get("mimeType") or inline.get("mime_type") or "")
        mt = str(node.get("mime_type") or node.get("mimeType") or "")
        if isinstance(node.get("data"), str) and (node.get("type") == "audio" or mt.startswith("audio")):
            return node["data"], mt or "audio/wav"
        for v in node.values():
            hit = _find_audio(v)
            if hit:
                return hit
    elif isinstance(node, list):
        for v in node:
            hit = _find_audio(v)
            if hit:
                return hit
    return None


def _as_wav(b64, mime):
    try:
        raw = base64.b64decode(b64)
    except (ValueError, TypeError):
        return None
    if raw[:4] == b"RIFF":
        return raw
    m = re.search(r"rate=(\d+)", mime or "")
    return _wav(raw, int(m.group(1)) if m else 24000)       # L16 PCM بلا ترويسة


def speak(text, lang, chain):
    """بايتات WAV أو None (لا مفتاح Gemini · نص فارغ · كل النماذج فشلت)."""
    text = speakable(text)
    key = next((s["key"] for s in chain or [] if s.get("p") == "gemini" and s.get("key")), "")
    if not text or not key:
        return None
    style = _STYLE["en" if lang == "en" else "ar"]
    hdr = {"Content-Type": "application/json", "x-goog-api-key": key}
    for m in TTS_INTERACTIONS:
        payload = {"model": m, "input": [{"type": "user_input", "content": [{
            "type": "text", "text": text, "annotations": [{"type": "speech_metadata", "style": style}]}]}],
            "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": TTS_VOICE}]}}
        try:
            hit = _find_audio(ai_agent._post_json(f"{GEMINI}/interactions", payload, hdr, timeout=25))
        except ai_agent.AIError as e:
            if ai_agent._is_auth(e):
                return None
            continue
        if hit:
            return _as_wav(*hit)
    for m in TTS_LEGACY:
        payload = {"contents": [{"parts": [{"text": f"Say in a {style}: {text}"}]}],
                   "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                       "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}}}
        try:
            hit = _find_audio(ai_agent._post_json(f"{GEMINI}/models/{m}:generateContent", payload, hdr, timeout=25))
        except ai_agent.AIError as e:
            if ai_agent._is_auth(e):
                return None
            continue
        if hit:
            return _as_wav(*hit)
    return None
