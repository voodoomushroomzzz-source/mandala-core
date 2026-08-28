# -*- coding: utf-8 -*-
"""
main.py — Entry Point
Startup, shutdown, webhook, health check, router/middleware registration.

Part of: honeycombs/fruits/gentle_companion/
Phase: 7 (depends on all other modules)

Key functions:
  on_startup()     — load store, set webhook, register bot commands
  on_shutdown()    — graceful stop, close HTTP session
  _check_webhook() — periodic webhook health monitor
  health()         — HTTP health check endpoint /health
  main()           — aiohttp app + APScheduler bootstrap
"""


async def on_startup():
    """Called when bot starts."""
    await _load_store()
    # Restore daily_stats after redeploy/crash
    try:
        live = await _github_get("honeycombs/sessions/daily_stats_live.json", force=True)
        from datetime import datetime as _dt_restore
        today_restore = _dt_restore.now().strftime("%Y-%m-%d")
        if isinstance(live, dict) and live.get("_date") == today_restore:
            restored = {k: v for k, v in live.items() if k != "_date"}
            _daily_stats.update(restored)
            logger.info(f"Daily stats restored: {len(restored)} gardener(s)")
    except Exception as e:
        logger.warning(f"Daily stats restore skipped: {e}")
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set: {WEBHOOK_URL}")
    # Регистрируем команды в меню Telegram
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start",     description="🌱 Войти в сад"),
        BotCommand(command="privacy",   description="🔐 Мои данные"),
        BotCommand(command="leave",     description="🚪 Покинуть сад"),
    ])
    logger.info("Bot commands registered")


    # Scheduler setup
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_reminder_scheduler, "interval", minutes=1, id="reminders")
    scheduler.add_job(run_proactive_scheduler, "interval", minutes=1, id="proactive")
    scheduler.add_job(run_resonance_decay, "cron", hour=3, minute=0, id="decay")
    scheduler.add_job(_send_daily_report, "cron", hour=18, minute=0, id="daily_report",
                      timezone="UTC")  # 18:00 UTC = 21:00 MSK
    scheduler.add_job(_sync_pending, "interval", minutes=2, id="sync")
    scheduler.add_job(_check_webhook, "interval", minutes=5, id="webhook_check")
    scheduler.start()
    logger.info("Scheduler started")

async def on_shutdown():
    """Called when bot stops."""
    if _pending_writes:
        logger.info(f"Flushing {len(_pending_writes)} pending write(s) before shutdown...")
        await _sync_pending()
    await bot.delete_webhook()
    await bot.session.close()
    if _http_session:
        await _http_session.close()
    logger.info("Bot shut down")

# ─── Main ─────────────────────────────────────────────────────────────────────


async def health(request: web.Request) -> web.Response:
    status = "ready" if any(us.get("ready") for us in _store.values() if isinstance(us, dict)) else "loading"
    name = "none"
    for uid, us in _store.items():
        if isinstance(us, dict) and us.get("ready") and us.get("profile"):
            name = us["profile"].get("name", "none")
            break
    # Auto-restore webhook if missing
    try:
        info = await bot.get_webhook_info()
        if not info.url:
            await bot.set_webhook(WEBHOOK_URL)
            logger.info("Webhook auto-restored")
    except Exception:
        pass
    return web.Response(text=f"ok|{status}|gardener={name}")

def main():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup())
    app.on_shutdown.append(lambda _: on_shutdown())
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()