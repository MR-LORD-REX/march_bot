from pathlib import Path
from typing import Literal

from aiogram.types import BufferedInputFile

GifName = Literal["error_1", "error_2", "error_3", "noted", "loading"]

_GIF_DIR = Path(__file__).parent.parent / "assets" / "gif"
_gif_bytes: dict[GifName, bytes] = {}


def _load_gifs() -> None:
    for name in ("error_1", "error_2","error_3","noted", "loading"):
        path = _GIF_DIR / f"{name}.mp4"
        _gif_bytes[name] = path.read_bytes()


_load_gifs()


def get_gif(name: GifName) -> BufferedInputFile:
    return BufferedInputFile(file=_gif_bytes[name], filename=f"{name}.mp4")
