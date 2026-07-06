from typing import List,Dict,Any,Union , Literal
import starrailcard
from hsr_cards import HonkaiStarrail
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from pydantic import BaseModel , ConfigDict
from PIL import Image
import ast
import random

from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.DB.repo.user_setting_repo import UserSettingsRepo
from bot.DB.repo.cache_repo import CacheRepo
from bot.config.config import proxies

logger=logging.getLogger(__name__)

class ProfileRes(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
        
    cached:bool
    card:str| Image.Image
    data: List[Dict[str,str|int]]
    
class CharRes(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    cached:bool
    card:str| Image.Image
    data: str|None
    
class EndRes(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    cached:bool
    card:str|Image.Image
    data:str|None
    
async def get_profile_card(session:AsyncSession,tele_id:int)->ProfileRes|None:
    uid=await GameIDs_repo(session).get_active_UID(tele_id)
    settings=await UserSettingsRepo(session).get_user_settings(tele_id)
    if not uid:
        return None
    cached=await CacheRepo(session).get_cache(tele_id,cache_type='PFP')
    card=None
    if cached:
        chars=ast.literal_eval(cached.data)
        return ProfileRes(
            cached=True,
            card=cached.file_id,
            data=chars
        )
    try:
        px=random.choice(proxies) if proxies else None
        async with starrailcard.Card(asset_save=True,proxy=px) as cards:
            card = await cards.create_profile(uid.game_id)
            chars=[]
            for cn , cid in zip(card.character_name,card.character_id):
                chars.append({"name":cn,"slot":cid})
            return ProfileRes(
                cached=False,
                card=card.card,
                data=chars
            )
    except Exception as e:
        logging.error(f"error while generating profile card : {e}")
        return None
    
async def get_character_card(session:AsyncSession,tele_id:int,slot:int)-> CharRes|None:
    uid=await GameIDs_repo(session).get_active_UID(tele_id)
    settings=await UserSettingsRepo(session).get_user_settings(tele_id)
    if not uid:
        return None   
    cached=await CacheRepo(session).get_cache(tele_id,cache_type='CHAR',slot=slot)
    card=None
    if cached:
            return CharRes(
                cached=True,
                card=cached.file_id,
                data=cached.data
            )
    try: 
        px=random.choice(proxies) if proxies else None
        async with starrailcard.Card(character_id=str(slot), seeleland=True,proxy=px) as cards:
            card = await cards.create(uid.game_id,style=settings.character_template)

            return CharRes(
                cached=False,
                card=card.card if type(card.card)==Image.Image else card.card[0].card,
                data=str(slot)
            )
    except Exception as e:
        logging.error(f"error while generating profile card : {e}")
        return None
    
async def get_endgame_card(
    session:AsyncSession,
    tele_id:int,
    c_type:Literal['MOC','PF','ANO','AS'],
    sched:Literal['1','2']='1'
)->EndRes|None:
    uid=await GameIDs_repo(session).get_active_UID(tele_id)
    if not uid:
        return None
    cache_slot = int(sched) if c_type != 'ANO' else None
    cached=await CacheRepo(session).get_cache(tele_id, cache_type=c_type, slot=cache_slot)
    card=None
    if cached:
        return EndRes(
            cached=True,
            card=cached.file_id,
            data=cached.data
        )
    try: 
        async with HonkaiStarrail(uid=uid.game_id) as HSR:
            if c_type=='ANO':
                card=await HSR.anomaly()
            elif c_type=='AS':
                card=await HSR.shadow(sched)
            elif c_type=='MOC':
                card=await HSR.MOC(sched)
            elif c_type=='PF':
                card= await HSR.PF(sched)
            else:
                return None

        return EndRes(
            cached=False,
            card=card,
            data=sched
        )
    except Exception as e:
        logger.error(f"error building end cards : {e}")
        return None