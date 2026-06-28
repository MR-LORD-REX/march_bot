from typing import Literal , List , Dict

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton 

def make_report_keboard(tele_id:int , uid:int , r_type:Literal['PFP','CHAR']='PFP'):
    kb=InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="report",callback_data=f"report:{r_type}:{tele_id}:{uid}"))
    return kb.as_markup()

def make_profile_keyboard(tele_id:int,chars:List[Dict[str,int]]):
    kb=InlineKeyboardBuilder()
    row=[]
    for char in chars:
        row.append(
            InlineKeyboardButton(
                text=f"{char.get('name')}",
                callback_data=f"C_card:{tele_id}:{char.get('slot')}"
        ))
        if len(row)==2:
            kb.row(*row)
            row=[]
    if row:
        kb.row(*row)
    return kb.as_markup()

def make_back_kb(tele_id:int):
    kb=InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="back",callback_data=f"back_P:{tele_id}"))
    return kb.as_markup()

def make_endgame_keyboard(tele_id:int, c_type:Literal['MOC','PF','AS'], active:Literal['1','2']='1'):
    """Inline keyboard with Current (1) and Previous (2) schedule buttons.
    The active button is marked with a bullet to indicate the current view."""
    kb=InlineKeyboardBuilder()
    cur_label = "• Current" if active == '1' else "Current"
    prv_label = "• Previous" if active == '2' else "Previous"
    kb.row(
        InlineKeyboardButton(text=cur_label, callback_data=f"EG:{c_type}:{tele_id}:1"),
        InlineKeyboardButton(text=prv_label, callback_data=f"EG:{c_type}:{tele_id}:2"),
    )
    return kb.as_markup()