from dotenv import load_dotenv
load_dotenv()

from typing import Dict , Any 
import json
import os
import sys
import logging

from bot.middleware.commands import CommandsAvailability
from bot.services.UG_cache import UsersRecord, GroupsRecord
from bot.utils.scheduler import Scheduler


logger=None

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
setup_logging()

logger = logging.getLogger(__name__)

ENVS=['DB_URL', 'BOT_TOKEN', 'MODE','ENV',"WEBHOOK_PATH","WEBHOOK_SECRET","PORT","FERNET_KEY","REDIS_HOST","REDIS_PORT","REDIS_PASS"]

CACHE_TTL=300 #10 mins in seconds

def check_envs():
    missing_envs = [env for env in ENVS if os.getenv(env) is None]
    if missing_envs:
        logging.error(f'Missing environment variables: {", ".join(missing_envs)}')
        sys.exit(1)

VAR_MODE = os.getenv("VAR_MODE", "SEP")
if VAR_MODE == "JSON":
    all_vars_json = os.getenv("ALL")
    if not all_vars_json:
        logging.error('VAR_MODE is JSON but "ALL" environment variable is missing or empty.')
        sys.exit(1)
    
    try:
        all_vars = json.loads(all_vars_json)
        for k, v in all_vars.items():
            os.environ[k] = str(v)
    except json.JSONDecodeError as e:
        logging.error(f'Failed to parse "ALL" environment variable as JSON: {e}')
        sys.exit(1)

check_envs()

DB_URL = os.getenv('DB_URL')
BOT_TOKEN = os.getenv('BOT_TOKEN')
MODE=os.getenv('MODE')
ENV=os.getenv('ENV')

FERNET_KEY=os.getenv('FERNET_KEY')

REDIS_HOST=os.getenv('REDIS_HOST')
REDIS_PORT=int(os.getenv('REDIS_PORT', 6379))
REDIS_PASS=os.getenv('REDIS_PASS')
REDIS_USERNAME=os.getenv('REDIS_USERNAME', 'default')

WEBHOOK_PATH=os.getenv("WEBHOOK_PATH","/webhook")
WEBHOOK_SECRET=os.getenv("WEBHOOK_SECRET","Nous")

OWNER_TELE_ID=int(os.getenv("OWNER_TELE_ID","5103772471"))
ADMIN_GC_ID=int(os.getenv("ADMIN_GC_ID","-1003477499464"))
CHANNEL_LINK="https://t.me/Neuvillette_help"

QDRANT_API_KEY=os.getenv("QDRANT_API_KEY","")
QDRANT_URL=os.getenv("QDRANT_URL","")
EMBEDDING_URL=os.getenv("EMBEDDING_URL","")
COLLECTION=os.getenv("COLLECTION","hsr_lore-bge-m3")

GEMINI_API_KEY=os.getenv("GEMINI_API_KEY","")

PORT=os.getenv("PORT",8000)

_render_url = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or (_render_url if _render_url else f"http://localhost:{PORT}")

PROXY=os.getenv("proxy")

cmdavailability: CommandsAvailability=CommandsAvailability()

users_record:UsersRecord=UsersRecord()
groups_record:GroupsRecord=GroupsRecord()
scheduler=Scheduler()


