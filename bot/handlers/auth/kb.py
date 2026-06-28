from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton 

def make_switch_kb(tele_id:int,uids:list[int]):
    kb=InlineKeyboardBuilder()
    for uid in uids:
        kb.row(InlineKeyboardButton(text=f"{uid}",callback_data=f"switch:{tele_id}:{uid}"))
    return kb.as_markup()