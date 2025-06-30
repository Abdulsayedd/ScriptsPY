import os
import sys
import json
import time
import psutil
import subprocess
import random
import asyncio
import logging
import requests
from PIL import Image

from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# External notifier
sys.path.append(r"I:\pythonscripts\1notifier")
from config import BOTS  # type: ignore
from notify import send_telegram  # type: ignore

CONFIG_KEY = "ComfeyFluxKontext"
author_data = BOTS.get(CONFIG_KEY, {})
TOKEN = author_data.get("token")
AUTHORIZED_USER_ID = author_data.get("user_id")
if not TOKEN or not AUTHORIZED_USER_ID:
    raise RuntimeError(f"{CONFIG_KEY} config missing in BOTS")

# Paths
COMFY_RUN = r"A:\ComfeyUI\ComfyUI_windows_portable\run_nvidia_gpu.bat"
OUTPUT_DIR = r"A:\ComfeyUI\ComfyUI_windows_portable\ComfyUI\output"
ENDPOINT = "http://127.0.0.1:8188/prompt"
FLOW_PATH = os.path.join(os.path.dirname(__file__), "fluxknotext_base.json")
TIMEOUT = 300

# Conversation states
IMAGE, TEXT = range(2)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def ensure_comfy() -> None:
    """Launch ComfyUI if the run script is not active."""
    for p in psutil.process_iter(["cmdline"]):
        try:
            if "run_nvidia_gpu.bat" in " ".join(p.info.get("cmdline", [])):
                return
        except Exception:
            continue
    try:
        subprocess.Popen(
            COMFY_RUN,
            cwd=os.path.dirname(COMFY_RUN),
            shell=True,
        )
        logger.info("Launched ComfyUI")
    except Exception as e:
        logger.error(f"Failed to launch ComfyUI: {e}")


async def run_flow(prompt_text: str, img_path: str) -> tuple[list[str], str | None]:
    """Run the ComfyUI flow and wait for a generated image."""
    try:
        base = json.load(open(FLOW_PATH, "r", encoding="utf-8"))
    except Exception as e:
        return [], f"Failed to load flow JSON: {e}"

    # Patch nodes
    base["6"]["inputs"]["text"] = prompt_text
    base["41"]["inputs"]["image"] = img_path

    # Determine image dimensions for width/height nodes
    try:
        with Image.open(img_path) as im:
            width, height = im.size
    except Exception as e:
        return [], f"Failed to open image: {e}"

    if "27" in base and "inputs" in base["27"]:
        base["27"]["inputs"]["width"] = width
        base["27"]["inputs"]["height"] = height
    if "30" in base and "inputs" in base["30"]:
        base["30"]["inputs"]["width"] = width
        base["30"]["inputs"]["height"] = height
    seed = random.randint(0, 2 ** 63 - 1)
    base["25"]["inputs"]["noise_seed"] = seed
    if "9" in base:
        base["9"]["inputs"]["filename_prefix"] = f"FluxKontext_{seed}"

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    before = set(os.listdir(OUTPUT_DIR))

    try:
        resp = requests.post(ENDPOINT, json={"prompt": base}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return [], f"Error posting to ComfyUI: {e}"

    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        await asyncio.sleep(1)
        after = set(os.listdir(OUTPUT_DIR))
        new = after - before
        imgs = []
        for f in new:
            if not f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            path = os.path.join(OUTPUT_DIR, f)
            try:
                if os.path.getsize(path) > 0:
                    imgs.append(path)
            except OSError:
                continue
        if imgs:
            return sorted(imgs), None
    return [], "Timeout waiting for ComfyUI output"


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Launch ComfyUI."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    ensure_comfy()
    await update.message.reply_text("ComfyUI started.")


async def run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begin a run by asking for an image."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return ConversationHandler.END
    ensure_comfy()
    await update.message.reply_text("Send the image to edit:")
    return IMAGE


async def image_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the received image and ask for a prompt."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return ConversationHandler.END
    if not update.message.photo:
        await update.message.reply_text("Please send a photo.")
        return IMAGE

    photo = update.message.photo[-1]
    file_path = os.path.join(OUTPUT_DIR, f"input_{int(time.time())}.png")
    telegram_file = await photo.get_file()
    await telegram_file.download_to_drive(file_path)

    context.user_data["image_path"] = file_path
    await update.message.reply_text("Send your prompt text:")
    return TEXT


async def text_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Run the flow using the stored image and provided prompt."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return ConversationHandler.END

    prompt_text = update.message.text.strip()
    context.user_data["prompt"] = prompt_text
    img_path = context.user_data.get("image_path")
    if not img_path:
        await update.message.reply_text("No image found. Please /run again.")
        return ConversationHandler.END

    imgs, err = await run_flow(prompt_text, img_path)

    if err:
        await update.message.reply_text(f"❌ {err}")
    elif not imgs:
        await update.message.reply_text("⚠️ No images generated.")
    else:
        for img in imgs:
            if not os.path.getsize(img):
                continue
            try:
                with open(img, "rb") as f:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f)
            except Exception as e:
                logger.error(f"Failed to send photo: {e}")
                try:
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=InputFile(img))
                except Exception as e2:
                    logger.error(f"Failed to send as document: {e2}")

    os.remove(img_path)
    return ConversationHandler.END


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    for p in psutil.process_iter(["cmdline"]):
        try:
            if "run_nvidia_gpu.bat" in " ".join(p.info.get("cmdline", [])):
                p.terminate()
        except Exception:
            continue
    await update.message.reply_text("Stopped ComfyUI.")
    send_telegram("Regular", "Exited ComfyUI.")


if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("run", run_cmd)],
        states={
            IMAGE: [MessageHandler(filters.PHOTO, image_received)],
            TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, text_received)],
        },
        fallbacks=[CommandHandler("stop", stop_cmd)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("run", run_cmd))
    logger.info("FluxKontext bot running.")
    app.run_polling()
