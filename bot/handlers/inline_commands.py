from aiogram.types import (
    inline_query,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram import Router, F 
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.DB.repo.cache_repo import CacheRepo
from bot.DB.asyncsessions import session_factory
from bot.config.config import users_record , BOT_TOKEN

rt = Router()

cache_map = {
    'PFP': 'Profile card',
    'CHAR': 'Character ',
    'MOC': 'Memory of chaos',
    'PF': 'Pure Fiction',
    'ANO': 'Anomaly Arbitration',
    'AS': 'Apocalyptic Shadow',
}

@rt.inline_query(F.query.is_empty())
async def handle_query(inline_query: inline_query.InlineQuery):
    query = inline_query.query
    telegram_id = inline_query.from_user.id
    results = []

    if not users_record.is_registered(telegram_id):
        results.append(
            InlineQueryResultArticle(
                id="not_registered",
                title="You are not logged in",
                input_message_content=InputTextMessageContent(
                    message_text="Please register a UID first using /login in DM ."
                ),
            )
        )
        await inline_query.answer(results, cache_time=1, is_personal=True)
        return
    kb=InlineKeyboardBuilder()
    text="Available inline commands"
    for cache_type, name in cache_map.items():
        kb.button(
            text=name,
            switch_inline_query_current_chat=f"{cache_type}"
        )
    kb.adjust(2)
    results.append(
        InlineQueryResultArticle(
            id="cache_types",
            title="Tap to available inline commands",
            input_message_content=InputTextMessageContent(
                message_text=text
            ),
            reply_markup=kb.as_markup()
        )
    )
    await inline_query.answer(results, cache_time=1, is_personal=True)
    
@rt.inline_query(F.query.in_(cache_map.keys()))
async def handle_cache_query(inline_query: inline_query.InlineQuery):
    query = inline_query.query
    telegram_id = inline_query.from_user.id
    results = []
    cache_type = query.strip().upper()
    print(f"inline query received from {telegram_id} for cache type {cache_type}")
    if cache_type not in cache_map:
        return
    if not users_record.is_registered(telegram_id):
        results.append(
            InlineQueryResultArticle(
                id="not_registered",
                title="You are not logged in",
                input_message_content=InputTextMessageContent(
                    message_text="Please register a UID first using /login in DM ."
                ),
            )
        )
        await inline_query.answer(results, cache_time=1, is_personal=True)
        return
    async with session_factory() as db_session:
        if cache_type=='CHAR':
            for slot in range(1, 8):
                cached = await CacheRepo(db_session).get_cache(telegram_id, cache_type=cache_type, slot=slot)
                if cached:
                    results.append(
                        InlineQueryResultCachedPhoto(
                            id=f"{cache_type}_cached",
                            photo_file_id=cached.file_id if cached else ""
                        )
                    )
        if cache_type in ['MOC', 'PF', 'AS']:
            for slot in range(1, 2):
                cached = await CacheRepo(db_session).get_cache(telegram_id, cache_type=cache_type, slot=slot+1)
                if cached:
                    results.append(
                        InlineQueryResultCachedPhoto(
                            id=f"{cache_type}_cached",
                            photo_file_id=cached.file_id if cached else ""
                        )
                    )
        if cache_type in ['ANO','PFP']:
            cached = await CacheRepo(db_session).get_cache(telegram_id, cache_type=cache_type)
            if cached:
                results.append(
                    InlineQueryResultCachedPhoto(
                        id=f"{cache_type}_cached",
                        photo_file_id=cached.file_id if cached else ""
                    )
                )
                
    await inline_query.answer(results, cache_time=1, is_personal=True)