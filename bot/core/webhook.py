import logging
import asyncio

from contextlib import asynccontextmanager
from aiogram.types import Update
from aiogram import Bot,Dispatcher

from fastapi import FastAPI , Request , HTTPException
from fastapi.responses import JSONResponse

from bot.config.config import WEBHOOK_PATH,WEBHOOK_SECRET,WEBHOOK_URL
from bot.DB.engine import engine

logger=logging.getLogger(__name__)

def setup_webhook(bot:Bot,dp:Dispatcher):
    
    @asynccontextmanager
    async def lifespan(app:FastAPI):
        try:
            current=await bot.get_webhook_info()
            if current.url:
                await bot.delete_webhook(drop_pending_updates=True)
            
            await bot.set_webhook(
                url=WEBHOOK_URL+WEBHOOK_PATH,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True
            )
            logger.info(f"Webhook set to {WEBHOOK_URL + WEBHOOK_PATH}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}", exc_info=True)
            raise
        yield
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.session.close()
        await engine.dispose()
        logger.info("Bot session and DB closed ")
        
    app=FastAPI(title="Bot Webhook", lifespan=lifespan)
    
    @app.post(WEBHOOK_PATH)
    async def handle_update(request: Request):
        try:
            token = request.headers.get("X-Telegram-Bot-API-Secret-Token")
            if token != WEBHOOK_SECRET:
                logger.warning("Invalid webhook secret token")
                raise HTTPException(status_code=401, detail="Unauthorized")
            
            update=await request.json()
            update=Update(**update)
            await dp.feed_update(bot=bot,update=update)
            return JSONResponse({"ok": True})
        
        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
        
    @app.head("/")
    async def head():
        return JSONResponse({"status": "ok"})
    
    @app.get("/")
    async def _get():
        return JSONResponse({"status": "ok"})
    
    return app
    
    
def setup_polling(bot:Bot,dp:Dispatcher):
    
    @asynccontextmanager
    async def lifespan(app:FastAPI):
        polling_task = None
        try:
            polling_task = asyncio.create_task(dp.start_polling(bot))
            yield
        finally:
            if polling_task:
                polling_task.cancel()
                try:
                    await polling_task
                except asyncio.CancelledError:
                    pass
            await bot.session.close()
            await engine.dispose()
            logger.info("Bot polling stopped and session closed")
    
    app=FastAPI(title="Bot Polling", lifespan=lifespan)
    
    @app.head("/")
    async def head():
        return JSONResponse({"status": "ok"})
    
    @app.get("/")
    async def _get():
        return JSONResponse({"status": "ok"})
    
    return app