"""Diagnostic (not a pytest test): verify the correct emergentintegrations API for
Claude Vision + usage reporting, to guide the autofill fix.
Run: python3 /app/backend/tests/diag_vision.py
"""
import asyncio
import base64
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")
from dotenv import dotenv_values
from emergentintegrations.llm.chat import (
    LlmChat, UserMessage, ImageContent, TextDelta, StreamDone,
)

KEY = dotenv_values("/app/backend/.env").get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_LLM_KEY")


def png_b64() -> str:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (620, 200), "white")
    d = ImageDraw.Draw(img)
    f = None
    p = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if Path(p).exists():
        from PIL import ImageFont as IF
        f = IF.truetype(p, 24)
    d.text((15, 30), "Tapu No: 12345", fill="black", font=f)
    d.text((15, 80), "Il: Ankara  Ilce: Cankaya", fill="black", font=f)
    d.text((15, 130), "Ada/Parsel: 1234/56", fill="black", font=f)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def main():
    llm = (
        LlmChat(api_key=KEY, session_id="diag_vision", system_message="Sadece JSON dön.")
        .with_model("anthropic", "claude-sonnet-5")
        .with_params(max_tokens=512)
    )
    msg = UserMessage(
        text='Görseldeki bilgileri JSON olarak çıkar: {"tapu_no":..,"il":..,"ada_parsel":..}',
        file_contents=[ImageContent(image_base64=png_b64())],
    )
    text, usage = "", None
    async for ev in llm.stream_message(msg):
        if isinstance(ev, TextDelta):
            text += ev.content
        elif isinstance(ev, StreamDone):
            usage = ev.usage
    print("TEXT:", text[:500])
    print("USAGE:", usage)


asyncio.run(main())
