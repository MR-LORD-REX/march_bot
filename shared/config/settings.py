from dotenv import load_dotenv
load_dotenv()

from typing import Dict , Any 
import json
import os
import sys
import logging

from shared.runtime import CommandsAvailability, UsersRecord, GroupsRecord

from shared.scheduling import Scheduler


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
ENV=os.getenv('ENV', 'local').strip().lower()
if ENV in {'dev', 'development'}:
    ENV = 'local'

FERNET_KEY=os.getenv('FERNET_KEY')

REDIS_HOST=os.getenv('REDIS_HOST')
REDIS_PORT=int(os.getenv('REDIS_PORT', 6379))
REDIS_PASS=os.getenv('REDIS_PASS')
REDIS_USERNAME=os.getenv('REDIS_USERNAME', 'default')
REDIS_SSL=os.getenv('REDIS_SSL', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}

WEBHOOK_PATH=os.getenv("WEBHOOK_PATH","/webhook")
WEBHOOK_SECRET=os.getenv("WEBHOOK_SECRET","Nous")
# Application-owned schema adoption. Disable only when a separate deployment
# job runs Alembic under its own advisory lock.
AUTO_MIGRATE=os.getenv("AUTO_MIGRATE", "true").strip().lower() in {"1", "true", "yes", "on"}

OWNER_TELE_ID=int(os.getenv("OWNER_TELE_ID","5103772471"))
ADMIN_GC_ID=int(os.getenv("ADMIN_GC_ID","-1003477499464"))
CHANNEL_LINK="https://t.me/hsr_updates"

QDRANT_API_KEY=os.getenv("QDRANT_API_KEY","")
QDRANT_URL=os.getenv("QDRANT_URL","")
EMBEDDING_URL=os.getenv("EMBEDDING_URL","")
COLLECTION=os.getenv("COLLECTION","hsr_lore-bge-m3")

GEMINI_API_KEY=os.getenv("GEMINI_API_KEY","")

PORT=os.getenv("PORT",8000)

_render_url = os.getenv("RENDER_EXTERNAL_URL")
BACKEND_URL = (
    os.getenv("BACKEND_URL")
    or os.getenv("WEBHOOK_URL")
    or _render_url
    or f"http://localhost:{PORT}"
).rstrip("/")
BACKEND_TYPE = os.getenv("BACKEND_TYPE", ENV).strip().lower()
if BACKEND_TYPE not in {"local", "prod"}:
    BACKEND_TYPE = ENV
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or BACKEND_URL).rstrip("/")
PANEL_URL = (os.getenv("PANEL_URL") or BACKEND_URL).rstrip("/")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "https://mr-lord-rex.github.io,https://tele-bots.visihost.net",
    ).split(",")
    if origin.strip()
]

PROXY=os.getenv("proxy")

cmdavailability: CommandsAvailability=CommandsAvailability()

users_record:UsersRecord=UsersRecord()
groups_record:GroupsRecord=GroupsRecord()
scheduler=Scheduler()

