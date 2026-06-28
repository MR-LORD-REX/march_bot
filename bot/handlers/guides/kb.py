from aiogram.types import InlineKeyboardMarkup , InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_guides_kb()->InlineKeyboardMarkup:
    kb=InlineKeyboardBuilder()
    kb.button(text="Guides",switch_inline_query_current_chat="guide:")
    kb.adjust(1)
    return kb.as_markup()