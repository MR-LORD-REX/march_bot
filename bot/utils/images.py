from aiogram.types import BufferedInputFile
from io import BytesIO
import asyncio 
from PIL import Image

def image_to_bytes(img:Image.Image)->bytes:
    buff=BytesIO()
    img.save(buff,format="PNG")
    return buff.getvalue()

async def image_to_tgFile(img:Image.Image)->BufferedInputFile:
    file=await asyncio.to_thread(image_to_bytes,img)
    file=BufferedInputFile(
        file=file,
        filename="card.png"
    )
    return file
