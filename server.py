import asyncio
import json
import os
import logging
from datetime import datetime
from pathlib import Path

from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import telegram

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9004196402:AAErmv1QGF5LEU52w2M-RVJfC6BIuTaR8Yo")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "5782290811"))
DATA_FILE  = Path("materials.json")
MAX_ITEMS  = 200
PORT       = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"teachers": {}, "materials": []}

def save_data(data: dict):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

_pending_add: dict = {}

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load_data()
    if uid == str(ADMIN_ID):
        await update.message.reply_text(
            "👋 Xush kelibsiz, Admin!\n\n"
            "/addteacher — ustoz qo'shish\n"
            "/removeteacher — ustoz o'chirish\n"
            "/listteachers — ro'yxat ko'rish"
        )
    elif uid in data["teachers"]:
        t = data["teachers"][uid]
        await update.message.reply_text(
            f"👋 Xush kelibsiz, {t['name']}!\n\n"
            "Material yuborish uchun matn, rasm, fayl yoki video yuboring."
        )
    else:
        await update.message.reply_text(
            "❌ Siz ro'yxatda yo'qsiz.\nAdmin: @mr_liberty1"
        )

async def cmd_addteacher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    _pending_add[ADMIN_ID] = {"step": "id"}
    await update.message.reply_text(
        "➕ Ustoz qo'shish\n\nUstoz Telegram ID sini yuboring:"
    )

async def cmd_removeteacher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    if not data["teachers"]:
        await update.message.reply_text("Ro'yxat bo'sh.")
        return
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = [[InlineKeyboardButton(f"❌ {t['name']}", callback_data=f"remove_{tid}")]
               for tid, t in data["teachers"].items()]
    buttons.append([InlineKeyboardButton("🚫 Bekor qilish", callback_data="remove_cancel")])
    await update.message.reply_text("O'chirmoqchi bo'lgan ustodni tanlang:",
        reply_markup=InlineKeyboardMarkup(buttons))

async def cmd_listteachers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    if not data["teachers"]:
        await update.message.reply_text("Ro'yxat bo'sh.")
        return
    lines = ["👥 Ustozlar ro'yxati:\n"]
    for i, (tid, t) in enumerate(data["teachers"].items(), 1):
        lines.append(f"{i}. {t['name']}\n   ID: {tid}")
    await update.message.reply_text("\n".join(lines))

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("remove_"):
        tid = query.data[7:]
        if tid == "cancel":
            await query.edit_message_text("❌ Bekor qilindi.")
            return
        data = load_data()
        t = data["teachers"].pop(tid, None)
        if t:
            save_data(data)
            await query.edit_message_text(f"✅ {t['name']} o'chirildi.")
        else:
            await query.edit_message_text("Topilmadi.")

async def get_profile_photo_url(bot, user_id: int) -> str:
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file = await bot.get_file(photos.photos[0][-1].file_id)
            return file.file_path
    except Exception:
        pass
    return ""

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message

    if uid == ADMIN_ID and ADMIN_ID in _pending_add:
        step = _pending_add[ADMIN_ID]["step"]
        text = msg.text or ""
        if step == "id":
            _pending_add[ADMIN_ID]["teacher_id"] = text.strip()
            _pending_add[ADMIN_ID]["step"] = "name"
            await msg.reply_text("Ustoz ismini yuboring:")
        elif step == "name":
            _pending_add[ADMIN_ID]["name"] = text.strip()
            _pending_add[ADMIN_ID]["step"] = "done"
            info = _pending_add.pop(ADMIN_ID)
            tid = info["teacher_id"]
            # Get profile photo
            photo_url = await get_profile_photo_url(ctx.bot, int(tid))
            data = load_data()
            data["teachers"][tid] = {
                "name": info["name"],
                "photo": photo_url
            }
            save_data(data)
            await msg.reply_text(f"✅ Qo'shildi!\n👨‍🏫 {info['name']}\nID: {tid}")
        return

    data = load_data()
    teacher_id = str(uid)
    if teacher_id not in data["teachers"]:
        await msg.reply_text("❌ Siz ro'yxatda yo'qsiz.\nAdmin: @mr_liberty1")
        return

    teacher = data["teachers"][teacher_id]

    # Update profile photo each time
    photo_url = await get_profile_photo_url(ctx.bot, uid)
    if photo_url:
        data["teachers"][teacher_id]["photo"] = photo_url

    material = {
        "id": int(datetime.now().timestamp() * 1000),
        "teacher_id": teacher_id,
        "teacher_name": teacher["name"],
        "teacher_photo": photo_url or teacher.get("photo", ""),
        "time": datetime.now().strftime("%H:%M"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "is_new": True,
    }

    if msg.text:
        material["type"] = "text"
        material["content"] = msg.text
    elif msg.photo:
        photo = msg.photo[-1]
        file = await ctx.bot.get_file(photo.file_id)
        material["type"] = "image"
        material["file_url"] = file.file_path
        material["content"] = msg.caption or ""
    elif msg.video:
        file = await ctx.bot.get_file(msg.video.file_id)
        material["type"] = "video"
        material["file_url"] = file.file_path
        material["file_name"] = msg.video.file_name or "video.mp4"
        material["content"] = msg.caption or ""
    elif msg.document:
        file = await ctx.bot.get_file(msg.document.file_id)
        material["type"] = "file"
        material["file_url"] = file.file_path
        material["file_name"] = msg.document.file_name or "fayl"
        material["content"] = msg.caption or ""
    elif msg.voice:
        file = await ctx.bot.get_file(msg.voice.file_id)
        material["type"] = "voice"
        material["file_url"] = file.file_path
        material["content"] = ""
    else:
        await msg.reply_text("Bu turdagi material qo'llab-quvvatlanmaydi.")
        return

    data["materials"].insert(0, material)
    data["materials"] = data["materials"][:MAX_ITEMS]
    save_data(data)
    await msg.reply_text("✅ Material doskaga yuborildi!")

# ── WEB ──
async def handle_index(request):
    html = Path("doska.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")

async def handle_materials(request):
    data = load_data()
    return web.Response(
        text=json.dumps({"teachers": data["teachers"], "materials": data["materials"]}, ensure_ascii=False),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"}
    )

async def handle_feedback(request):
    try:
        body = await request.json()
        fb_file = Path("feedback.json")
        feedbacks = json.loads(fb_file.read_text(encoding="utf-8")) if fb_file.exists() else []
        feedbacks.insert(0, {
            "text": body.get("text", ""),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        fb_file.write_text(json.dumps(feedbacks[:100], ensure_ascii=False, indent=2), encoding="utf-8")
        return web.Response(text='{"ok":true}', content_type="application/json")
    except Exception as e:
        return web.Response(text='{"ok":false}', content_type="application/json")

async def handle_health(request):
    return web.Response(text="OK")

async def main():
    if not DATA_FILE.exists():
        save_data({"teachers": {}, "materials": []})

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("addteacher", cmd_addteacher))
    app.add_handler(CommandHandler("removeteacher", cmd_removeteacher))
    app.add_handler(CommandHandler("listteachers", cmd_listteachers))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))

    await app.initialize()
    await app.start()

    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        await app.bot.set_webhook(f"{webhook_url}/webhook")
        logger.info(f"Webhook: {webhook_url}/webhook")
    else:
        await app.updater.start_polling()
        logger.info("Polling started")

    web_app = web.Application()
    web_app.router.add_get("/", handle_index)
    web_app.router.add_get("/materials.json", handle_materials)
    web_app.router.add_post("/feedback", handle_feedback)
    web_app.router.add_get("/health", handle_health)

    if webhook_url:
        async def webhook_handler(request):
            data = await request.json()
            update = Update.de_json(data, app.bot)
            await app.process_update(update)
            return web.Response(text="OK")
        web_app.router.add_post("/webhook", webhook_handler)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Web server on port {PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
