import pygame
from PIL import Image, ImageDraw, ImageFont


class SurfaceFont:
    def __init__(self, path, size):
        self.font = ImageFont.truetype(path, size)
        self.cache = {}

    def _surface(self, value, color):
        color = tuple(color)
        if len(color) == 3:
            color = (*color, 255)
        key = value, color
        if key not in self.cache:
            box = self.font.getbbox(value)
            width = max(1, box[2] - box[0] + 4)
            height = max(1, box[3] - box[1] + 4)
            image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.text((2 - box[0], 2 - box[1]), value, font=self.font, fill=color)
            self.cache[key] = pygame.image.fromstring(image.tobytes(), image.size, "RGBA")
        return self.cache[key]

    def render(self, value, _antialias, color):
        return self._surface(str(value), color).copy()

    def size(self, value):
        return self._surface(str(value), (255, 255, 255)).get_size()
