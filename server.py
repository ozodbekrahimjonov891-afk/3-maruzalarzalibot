import asyncio
import json
import os
import logging
from datetime import datetime
from pathlib import Path

from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9004196402:AAErmv1QGF5LEU52w2M-RVJfC6BIuTaR8Yo")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "5782290811"))
DATA_FILE  = Path("materials.json")
MAX_ITEMS  = 100
PORT       = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── DATA HELPERS ─────────────────────────────────────────────────────────────
def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"teachers": {}, "materials": []}

def save_data(data: dict):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── BOT HANDLERS ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load_data()
    if uid == str(ADMIN_ID):
        await update.message.reply_text(
            "👋 Xush kelibsiz, Admin!\n\n"
            "Buyruqlar:\n"
            "/addteacher — ustoz qo'shish\n"
            "/removeteacher — ustoz o'chirish\n"
            "/listteachers — ro'yxat ko'rish"
        )
    elif uid in data["teachers"]:
        t = data["teachers"][uid]
        await update.message.reply_text(
            f"👋 Xush kelibsiz, {t['name']}!\n"
            f"📚 Fan: {t['subject']}\n\n"
            "Material yuborish uchun shunchaki matn, rasm, fayl yoki video yuboring."
        )
    else:
        await update.message.reply_text(
            "❌ Siz ro'yxatda yo'qsiz.\n"
            "Admin: @mr_liberty1"
        )

# ── Admin: add teacher ──
_pending_add: dict = {}  # admin_id -> step

async def cmd_addteacher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return
    _pending_add[uid] = {"step": "id"}
    await update.message.reply_text(
        "➕ Ustoz qo'shish\n\nUstoz Telegram ID sini yuboring:\n"
        "(Ustoz @userinfobot ga /start yozsa, IDsi chiqadi)"
    )

async def cmd_removeteacher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return
    data = load_data()
    if not data["teachers"]:
        await update.message.reply_text("Ro'yxat bo'sh.")
        return
    buttons = []
    for tid, t in data["teachers"].items():
        buttons.append([InlineKeyboardButton(
            f"❌ {t['name']} — {t['subject']}", callback_data=f"remove_{tid}"
        )])
    buttons.append([InlineKeyboardButton("🚫 Bekor qilish", callback_data="remove_cancel")])
    await update.message.reply_text(
        "O'chirmoqchi bo'lgan ustodni tanlang:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def cmd_listteachers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return
    data = load_data()
    if not data["teachers"]:
        await update.message.reply_text("Ro'yxat bo'sh.")
        return
    lines = ["👥 Ustozlar ro'yxati:\n"]
    for i, (tid, t) in enumerate(data["teachers"].items(), 1):
        lines.append(f"{i}. {t['name']} — {t['subject']}\n   ID: {tid}")
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

# ── Incoming messages ──
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message

    # Admin add-teacher flow
    if uid == ADMIN_ID and uid in _pending_add:
        step = _pending_add[uid]["step"]
        text = msg.text or ""
        if step == "id":
            _pending_add[uid]["teacher_id"] = text.strip()
            _pending_add[uid]["step"] = "name"
            await msg.reply_text("Ustoz ismini yuboring:")
        elif step == "name":
            _pending_add[uid]["name"] = text.strip()
            _pending_add[uid]["step"] = "subject"
            await msg.reply_text("Fan nomini yuboring:")
        elif step == "subject":
            info = _pending_add.pop(uid)
            data = load_data()
            data["teachers"][info["teacher_id"]] = {
                "name": info["name"],
                "subject": text.strip()
            }
            save_data(data)
            await msg.reply_text(
                f"✅ Qo'shildi!\n👨‍🏫 {info['name']} — {text.strip()}\nID: {info['teacher_id']}"
            )
        return

    # Teacher material flow
    data = load_data()
    teacher_id = str(uid)
    if teacher_id not in data["teachers"]:
        await msg.reply_text(
            "❌ Siz ro'yxatda yo'qsiz.\nAdmin: @mr_liberty1"
        )
        return

    teacher = data["teachers"][teacher_id]
    material = {
        "id": int(datetime.now().timestamp() * 1000),
        "teacher_name": teacher["name"],
        "subject": teacher["subject"],
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

    # Prepend and trim
    data["materials"].insert(0, material)
    data["materials"] = data["materials"][:MAX_ITEMS]
    save_data(data)
    await msg.reply_text("✅ Material doskaga yuborildi!")

# ─── WEB SERVER ───────────────────────────────────────────────────────────────

async def handle_index(request):
    html = Path("doska.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")

async def handle_materials(request):
    data = load_data()
    # Mark "new" items as seen after fetch (they were new for 5 s)
    return web.Response(
        text=json.dumps(data["materials"], ensure_ascii=False),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"}
    )

async def handle_health(request):
    return web.Response(text="OK")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    # Ensure data file exists
    if not DATA_FILE.exists():
        save_data({"teachers": {}, "materials": []})

    # Build bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("addteacher", cmd_addteacher))
    app.add_handler(CommandHandler("removeteacher", cmd_removeteacher))
    app.add_handler(CommandHandler("listteachers", cmd_listteachers))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))

    await app.initialize()
    await app.start()

    # Telegram webhook / polling decision
    webhook_url = os.environ.get("WEBHOOK_URL")  # set on Render

    if webhook_url:
        await app.bot.set_webhook(f"{webhook_url}/webhook")
        logger.info(f"Webhook set: {webhook_url}/webhook")
    else:
        # Local: use polling
        await app.updater.start_polling()
        logger.info("Polling started")

    # Build web server
    web_app = web.Application()
    web_app.router.add_get("/", handle_index)
    web_app.router.add_get("/materials.json", handle_materials)
    web_app.router.add_get("/health", handle_health)

    if webhook_url:
        # Receive webhook updates
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
    logger.info(f"Web server running on port {PORT}")

    # Keep alive
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
