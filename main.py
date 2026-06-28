from asyncio import run
import logging

from bot.core.main import start

logger = logging.getLogger(__name__)

if __name__=="__main__":
    try:
        run(start())
    
    except KeyboardInterrupt:
        logger.info("Bot manually stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"error while starting : {e}", exc_info=True)