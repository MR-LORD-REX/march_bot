from hsr_cards import HonkaiStarrail
from pydantic import BaseModel, ConfigDict
from PIL import Image
from datetime import datetime, timezone
import logging
import asyncio

from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.DB.repo.user_setting_repo import UserSettingsRepo
from bot.utils.images import image_to_tgFile
from bot.utils.auth import decrypt_token

logger=logging.getLogger(__name__)

class LiveStatsRes(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    card: Image.Image | None
    time: datetime | None
    seconds: int | None = None
    success: bool
    msg: str


class BannersRes(BaseModel):
    """Result model for the /banners command (no auth required)."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    card: Image.Image | None
    success: bool
    msg: str


class EventsRes(BaseModel):
    """Result model for the /events command (no auth required)."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    card: Image.Image | None
    success: bool
    msg: str
    
async def get_live_stats_card(db_session,tele_id:int)->LiveStatsRes:
    ## Don't use caching , it uses internal cache
    game_id=await GameIDs_repo(db_session).get_active_UID(tele_id)
    if not game_id:
        return LiveStatsRes(
            card=None,
            time=None,
            success=False,
            msg="No active game ID found. Please login using /login or /switch."
        )
    token=game_id.auth_token
    if not token:
        return LiveStatsRes(
            card=None,
            time=None,
            success=False,
            msg="Please login with /token_login to access live stats."
        )
    try:
        token=decrypt_token(token)
        async with HonkaiStarrail(uid=game_id.game_id,cookie=token) as hsr:
            card=await hsr.notes(raw=True)
            t=datetime.fromtimestamp(card[1].stamina_full_ts,timezone.utc)
            if card:
                return LiveStatsRes(
                    card=card[0],
                    time=t,
                    seconds=card[1].stamina_recover_time,
                    success=True,
                    msg="Notes"
                )
            else:
                return LiveStatsRes(
                    card=None,
                    time=None,
                    success=False,
                    msg="Failed to retrieve live stats card. Please try again later."
                )
    except Exception as e:
        logger.error(f"Error fetching live stats card: {str(e)}")
        return LiveStatsRes(
            card=None,
            time=None,
            success=False,
            msg=f"An error occurred while fetching live stats"
        )


async def send_recovery_notification(tele_id:int, retries:int=3):
    from bot.core.main import bot
    from bot.DB.asyncsessions import session_factory
    
    async with session_factory() as db_session:
        for attempt in range(retries):
            try:
                live_stats = await get_live_stats_card(db_session, tele_id)
                if not live_stats.success:
                    await asyncio.sleep(10)
                    continue
                now = datetime.now(tz=timezone.utc)
                if live_stats.time is None or live_stats.time <= now:
                    text = "Your TP have fully recovered!\nYou can check your live stats with /notes"
                    if live_stats.card:
                        card_file = await image_to_tgFile(live_stats.card)
                        await bot.send_photo(tele_id, card_file, caption=text)
                    else:
                        await bot.send_message(tele_id, text)
                    logger.info(f"Sent recovery notification to user {tele_id}")
                    break
                else:
                    remaining_seconds = (live_stats.time - now).total_seconds()
                    sleep_time = min(remaining_seconds, 300)
                    await asyncio.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Error sending recovery notification to user {tele_id} on attempt {attempt+1}: {str(e)}")
                await asyncio.sleep(10)
                if attempt == retries - 1:
                    logger.error(f"Failed to send recovery notification to user {tele_id} after {retries} attempts.")
                    
# daily reminder of daily tasks IST 10:00 PM 

async def send_daily_reminder():
    from bot.core.main import bot
    from bot.DB.asyncsessions import session_factory
    
    async with session_factory() as db_session:
        users=await UserSettingsRepo(db_session).get_all_users_with_daily_reminder()
        for tele_id in users:
            try:
                token=await GameIDs_repo(db_session).get_active_UID(tele_id)
                game_id=token.game_id
                if not token or not token.auth_token:
                    await bot.send_message(tele_id, "Make sure to complete your daily tasks or you can login with /token_login to get detailed reminder in future")
                    await asyncio.sleep(10)
                    continue
                else:
                    token=decrypt_token(token.auth_token)
                    async with HonkaiStarrail(game_id,token) as hsr:
                        data=await hsr.notes(raw=True)
                        card=await image_to_tgFile(data[0])
                        data=data[1]
                        if data.current_train_score<data.max_train_score:
                            text=f"Your daily points are : {data.current_train_score}/{data.max_train_score}"
                            text+="\n make sure to comple your dailies"
                            await bot.send_photo(tele_id,photo=card,caption=text)
                        else:
                            continue
                await asyncio.sleep(10)  # Sleep to avoid hitting game API rate limits
            except Exception as e:
                logger.error(f"Error sending daily reminder to user {tele_id}: {str(e)}")
                await asyncio.sleep(10)

                
# ---------------------------------------------------------------------------
# Public (no-cookie) card generators — Banners & Events
# ---------------------------------------------------------------------------

async def get_banners_card(uid: str) -> BannersRes:
    """Render the current HSR banner card.

    No authentication required — the calendar API is public.
    ``uid`` is only used to resolve the correct server region.
    """
    try:
        async with HonkaiStarrail(uid=uid) as hsr:
            card = await hsr.banners()
        return BannersRes(
            card=card,
            success=True,
            msg="Current Honkai: Star Rail banners",
        )
    except Exception as e:
        logger.error(f"Error fetching banners card: {e}")
        return BannersRes(
            card=None,
            success=False,
            msg="Failed to fetch banners. Please try again later.",
        )


async def get_events_card(uid: str) -> EventsRes:
    """Render the current HSR in-game events card.

    No authentication required — the calendar API is public.
    ``uid`` is only used to resolve the correct server region.
    """
    try:
        async with HonkaiStarrail(uid=uid) as hsr:
            card = await hsr.events()
        return EventsRes(
            card=card,
            success=True,
            msg="Current Honkai: Star Rail events",
        )
    except Exception as e:
        logger.error(f"Error fetching events card: {e}")
        return EventsRes(
            card=None,
            success=False,
            msg="Failed to fetch events. Please try again later.",
        )
        
async def get_endgame_card(uid: str) -> EventsRes:
    """Render the current HSR endgame card.

    No authentication required — the calendar API is public.
    ``uid`` is only used to resolve the correct server region.
    """
    try:
        async with HonkaiStarrail(uid=uid) as hsr:
            card = await hsr.endgame()
        return EventsRes(
            card=card,
            success=True,
            msg="Current Honkai: Star Rail endgame",
        )
    except Exception as e:
        logger.error(f"Error fetching endgame card: {e}")
        return EventsRes(
            card=None,
            success=False,
            msg="Failed to fetch endgame. Please try again later.",
        )