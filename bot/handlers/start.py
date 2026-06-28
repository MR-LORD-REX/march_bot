from aiogram import Router
from aiogram.types import Message , InlineKeyboardMarkup , InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.config import CHANNEL_LINK

rt=Router()



@rt.message(Command("start"))
async def start(msg: Message, db_session: AsyncSession):
    kb = InlineKeyboardBuilder()
    kb.button(text="Join our channel", url=CHANNEL_LINK)
    text = (
        "Welcome , Trailblazer! . I'm March 7th \n\n"
        "Tap /help to see everything I can do for you.\n"
        "Join our channel below for the latest updates on the game and the bot."
    )
    await msg.reply(text, reply_markup=kb.as_markup(), parse_mode=None)
    
    
@rt.message(Command("help"))
async def help(msg: Message):
    text = (
        "Here are the commands you can use:\n\n"
        "/start - start the bot and see welcome message\n"
        "/help - see this message again\n"
        "/login - link your game account with the bot (UID required)\n"
        "/logout - unlink your game account from the bot\n"
        "/switch - switch between linked game accounts (if you have multiple)\n"
        "/token_login - link your account using Cookies (for notes access)\n"
        "/token_logout - unlink your endfield account from the bot\n"
        "/token_help - see instructions to get your cookies\n"
        "/myuid - see your linked game account UID\n"
        "/myc - see your profile cards\n"
        "/notes - see your live in-game notes (cookies required)\n"
        "/settings - customize your preferences for reminders and character template\n"
        "/admin_help - see admin commands (admins and bot owner only)\n"
        "/moc - Memory of chaos card\n"
        "/apoc - apocyliptic shadow card\n"
        "/anomaly - anomaly card\n"
        "/purefiction - PF card\n"
    )
    await msg.reply(text, parse_mode=None)
    
@rt.message(Command("token_help"))
async def token_help(msg: Message):
    if msg.chat.type != "private":
        await msg.reply("Please use this command in private chat.")
        return
    vidlink="https://t.me/Neuvillette_help/81"
    kb=InlineKeyboardBuilder()
    kb.button(text="watch Guide",url=vidlink)
    text = (
        "Follow these steps to get your cookies:\n\n"
        "And send the values seperated by // \n\n"
        "example: /token_login v2_CAISDGM5b3FhcTNzM2d1OBokNGQ4YT//206773753"
    )
    await msg.reply(text, parse_mode="HTML", reply_markup=kb.as_markup())