from aiogram.types import Message
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
import enka
from pydantic import BaseModel
import logging
from hsr_cards import HonkaiStarrail
from hsr_cards.models.auth import Cookies


from bot.DB.repo.user_repo import UserRepo
from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.DB.repo.user_setting_repo import UserSettingsRepo
from bot.DB.repo.cache_repo import CacheRepo
from bot.utils.auth import encrypt_token , decrypt_token

logger=logging.getLogger(__name__)

class LoginResp(BaseModel):
    msg:str
    success:bool
    
class UidResp(BaseModel):
    success:bool
    name:str|None=None
    
async def check_user(session:AsyncSession,tele_id:int)->bool:
    user= await UserRepo(session).get_by_tele_id(tele_id)
    if not user:
        return False
    return True

async def verify_token(token:Dict[str,str],uid:int)->bool:
    try:
        lt=token.get("ltoken_v2","")
        id=token.get("ltuid_v2","")
        cookie=Cookies(
            ltoken_v2=lt,
            ltuid_v2=id
        )
        async with HonkaiStarrail(uid,cookie) as hsr:
            res=await hsr.verify_cookies()
        return res
    except Exception as e:
        logger.warning(f"error {e} while verifying token")
        return False
    
async def verify_uid(uid:int)->UidResp:
    async with enka.HSRClient() as en :
        try:
            data=await en.fetch_showcase(uid)
            name=data.player.nickname
            return UidResp(
                success=True,
                name=name
            )
        except Exception as e:
            logger.error(f"invalid uid :{uid} or server down" , "error:",e)
            return UidResp(
                success=False
            )

async def login(session:AsyncSession,tele_id:int,msg:Message,game_id:int)-> LoginResp:
    existing_uid=await GameIDs_repo(session).get_UID(tele_id, game_id)
    user=await check_user(session,tele_id)
    if existing_uid:
        return LoginResp(
            msg="user already logged in , use /logout or /switch",
            success=False
        )
    res=await verify_uid(game_id)
    if not res.success:
        return LoginResp(
            msg="Invalid Uid",
            success=False
        )
    username=msg.from_user.username
    display_name=msg.from_user.full_name
    if not user:
        await UserRepo(session).add_user(tele_id,user_name=username,display_name=display_name)
        await UserSettingsRepo(session=session).add_user_settings(tele_id)
    await GameIDs_repo(session).add_game_UID(tele_id,game_id)
    return LoginResp(
            msg=f"Logged in succesfully \n username:{res.name} \n UID:{game_id}",
            success=True
        )
    
async def logout(session:AsyncSession,tele_id) -> LoginResp:
    active_uid=await GameIDs_repo(session).get_active_UID(tele_id)
    if not active_uid:
        return LoginResp(
            msg="You dont have any UID set , please login via /login <UID> ",
            success=False
        )
    current=await GameIDs_repo(session).remove_game_UID(tele_id,active_uid.game_id)
    await CacheRepo(session).delete_all_cache(tele_id)
    if not current:
        return LoginResp(
            msg="logged out successfully ",
            success=True
        )
    return LoginResp(
        msg=f"Logged out successfully from uid : {active_uid.game_id} \n New active uid is : {current.game_id} .",
        success=True
    )
    
async def switch(session:AsyncSession,tele_id:int,game_id:int) -> LoginResp:
    switched=await GameIDs_repo(session).switch_uid(tele_id,game_id)
    if not switched:
        return LoginResp(
            msg="error occured while switching uid",
            success=True
        )
    await CacheRepo(session).delete_all_cache(tele_id)
    return LoginResp(
        msg=f"succesfully set {game_id} as an active uid",
        success=True
    )
    
async def token_login(session:AsyncSession,tele_id:int,token:Dict[str,str]) -> LoginResp:
    current=await GameIDs_repo(session).get_active_UID(tele_id)
    if not current :
        return LoginResp(
            msg=f"Please login using /login ",
            success=False
        )
    if current.auth_token:
        return LoginResp(
            msg=f"You have already set token for this UID use /switch or /token_logout",
            success=False
        )
    res=await verify_token(token,current.game_id)
    if not res:
        return LoginResp(
            success=False,
            msg="Invalid Token"
        )
    tk=f"{token.get('ltoken_v2')}||{token.get('ltuid_v2')}"
    enc_token=encrypt_token(tk)
    await GameIDs_repo(session).add_auth_token(tele_id,enc_token)
    return LoginResp(
        msg=f"successfully set token for the UID:{current.game_id}\nDo NOT share this token with anyone !!!\n Token expiry is 60 days or until you change your password , make sure to update it in the bot.",
        success=True
    )

async def token_logout(session:AsyncSession,tele_id:int) -> LoginResp:
    current=await GameIDs_repo(session).get_active_UID(tele_id)
    if not current :
        return LoginResp(
            msg=f"Please login using /login ",
            success=False
        )
    if not current.auth_token:
        return LoginResp(
            msg=f"You dont have any token set for this UID",
            success=False
        )
    await GameIDs_repo(session).remove_auth_token(tele_id)
    return LoginResp(
        msg=f"successfully removed token for UID:{current.game_id}",
        success=True
    )