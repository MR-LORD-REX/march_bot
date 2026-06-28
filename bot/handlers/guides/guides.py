# from aiogram import Router, F
# from aiogram.types import (
#     Message,
#     InlineQuery,
#     InlineQueryResultArticle,
#     InputTextMessageContent,
#     CallbackQuery,
#     InputMediaPhoto,
# )
# from aiogram.filters import Command
# from sqlalchemy.ext.asyncio import AsyncSession
# import logging

# from endfield_cards.builds.map import builds_map
# from endfield_cards import EFCard

# from bot.handlers.guides.kb import get_guides_kb

# builds_map_list = builds_map.__args__
# # names from literal as command names /mifu
# pattern = tuple("/" + c for c in builds_map_list)

# rt= Router()
# logger = logging.getLogger(__name__)

# def is_guide_command(msg: Message) -> bool:
#     """Check if message starts with a guide command (partial match in name)"""
#     if not msg.text:
#         return False
#     first_word = msg.text.split()[0]
#     if not first_word.startswith('/'):
#         return False
#     # Check if the typed text is contained in any command name
#     first_word_content = first_word[1:].lower()
#     return any(first_word_content in cmd[1:].lower() for cmd in pattern)

# @rt.message(Command("guides"))
# async def guides_handler(message:Message):
#     kb=get_guides_kb()
#     await message.reply("Please tap on below buttons to view guides for each character:\n\nStart writing the name of a character for suggetions",reply_markup=kb)
    
# @rt.inline_query(F.query.startswith("guide:"))
# async def handle_guide_region(inline_query: InlineQuery):
#     result=[]
#     # Parse character name: "guide:CharacterName"
#     parts = inline_query.query.split(":", 2)
#     if len(parts) < 2:
#         all_characters = None
#         async with EFCard() as ef_card:
#             all_characters = await ef_card.available_builds()
#             # name : {icon_url:...}
#             for c , info in all_characters.items():
#                 result.append(
#                     InlineQueryResultArticle(
#                         id=c,
#                         title=c,
#                         description=f"view guides of {c}",
#                         thumbnail_url=info["icon_url"],
#                         thumbnail_width=100,
#                         thumbnail_height=100,
#                         input_message_content=InputTextMessageContent(
#                             message_text=f"/{c.lower()}"
#                         )
#                     )
#                 )
#         return inline_query.answer(results=result, cache_time=30, is_personal=True)
#     else:
#         character = parts[1].strip().lower()
#         async with EFCard() as ef_card:
#             all_characters = await ef_card.available_builds()
#             for c , info in all_characters.items():
#                 if character in c.lower():
#                     result.append(
#                         InlineQueryResultArticle(
#                             id=c,
#                             title=c,
#                             description=f"view guides of {c}",
#                             thumbnail_url=info["icon_url"],
#                             thumbnail_width=100,
#                             thumbnail_height=100,
#                             input_message_content=InputTextMessageContent(
#                                 message_text=f"/{c.lower()}"
#                             )
#                         )
#                     )
#         return inline_query.answer(results=result, cache_time=30, is_personal=True)
    
# @rt.message(is_guide_command)
# async def handle_guide_selection(message:Message):
#     print("guide")
#     first_word = message.text.split()[0]
#     first_word_content = first_word[1:].lower()
    
#     matching_cmd = None
#     for cmd in pattern:
#         if first_word_content in cmd[1:].lower():
#             matching_cmd = cmd
#             break
    
#     if not matching_cmd:
#         await message.reply("No guide found for this command.")
#         return
    
#     character_name = matching_cmd[1:].strip().lower() 
#     try:
#         async with EFCard() as ef_card:
#             card= await ef_card.get_character_build(character_name)
#             if not card:
#                 await message.reply("No guide found for this character.")
#                 return  
#             media = InputMediaPhoto(media=card[1] , caption=character_name)
#             await message.reply_media_group(media=[media])
#     except Exception as e:
#         await message.reply("An error occurred while fetching the guide. Please try again later.")
#         logger.error(f"Error fetching guide for {character_name}: {e}", exc_info=True)