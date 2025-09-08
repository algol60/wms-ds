from io import BytesIO
from PIL import Image, ImageDraw#, ImageFont
from pathlib import Path

import util
from util import wms

# Demonstrate georeferencing an image.
#

FNAM = 'D:/Users/pjmayne/Pictures/Desktops/Serenity.jpg'
FNAM2 = 'D:/Users/pjmayne/Pictures/i-am-altering-the-deal.jpg'

class BaseImage:
    """Base image.

    Subclasses must define self.geo_x, self.geo_y, self.geo_w, self.geo_h
    """

    def __init__(self, fnam):
        self.fnam = fnam
        self.img = Image.open(fnam)
        self.width, self.height = self.img.size

        self.geo_x = None
        self.geo_y = None
        self.geo_w = None
        self.geo_h = None

        print('IMG', fnam)

    def __str__(self):
        return f'{self.fnam} w={self.width} h={self.height} geox {self.geo_x}+{self.geo_w} geoy {self.geo_y}+{self.geo_h}'

    def draw_image(self, w, h, bbox, path, layer_name):
        """Make a georeferenced image."""

        west, south, east, north = bbox

        # Determine the geo indents on the left, eight, bottom, top of the image.
        #
        in_l = west - self.geo_x if west>self.geo_x else 0.0
        in_r = self.geo_x+self.geo_w - east if east<(self.geo_x+self.geo_w) else 0.0
        in_b = south - self.geo_y if south>self.geo_y else 0.0
        in_t = self.geo_y+self.geo_h - north if north<(self.geo_y+self.geo_h) else 0.0

        if in_l!=0 or in_r!=0 or in_b!=0 or in_t!=0:
            # Convert geo to pixels.
            #
            in_l = int(in_l*self.width/self.geo_w)
            in_r = int(in_r*self.width/self.geo_w)
            in_b = int(in_b*self.height/self.geo_h)
            in_t = int(in_t*self.height/self.geo_h)
            new_img = self.img.crop((in_l, in_t, self.width-in_r, self.height-in_b))
        else:
            new_img = self.img.copy()

        new_img = new_img.resize((w, h), resample=Image.BICUBIC)

        return new_img

class EqualAspectImage(BaseImage):
    def __init__(self, fnam):
        super().__init__(fnam)

        # Bottom-left corner of the image.
        #
        self.geo_x = 2.0
        self.geo_y = 45.0

        # Make the georeferencing proportional to the size of the image.
        #
        self.geo_w = self.width
        self.geo_h = self.height

        while self.geo_w>18 or self.geo_h>9:
            self.geo_w /= 2.0
            self.geo_h /= 2.0
        print('IMG', self.geo_w, self.geo_h)

ea_img = EqualAspectImage(FNAM)

@wms.layer('georef_layer',
        abstract='A georeferenced image with equal aspect.',
        title=Path(ea_img.fnam).stem,
        minx=ea_img.geo_x,
        miny=ea_img.geo_y,
        maxx=ea_img.geo_x+ea_img.geo_w,
        maxy=ea_img.geo_y+ea_img.geo_h,
        priority=50)
def ea_layer(request, w, h, bbox, path, layer_name, style_name):
    return ea_img.draw_image(w, h, bbox, path, layer_name)

class CornerImage(BaseImage):
    """An image with TL in London, height to Paris, proportionate width."""

    def __init__(self, fnam):
        self.fnam = fnam
        self.img = Image.open(fnam)
        self.width, self.height = self.img.size

        # The zero points.
        #
        london_lon, london_lat = -0.12766, 51.50731
        paris_lon, paris_lat = 2.34886,48.85336

        self.geo_x = london_lon
        self.geo_y = paris_lat
        self.geo_h = london_lat - paris_lat
        self.geo_w = (self.width/self.height) * self.geo_h

c_img = CornerImage(FNAM2)

@wms.layer('corner_layer',
        abstract='An image with one corner in London.',
        title='Corner in London',
        minx=c_img.geo_x,
        miny=c_img.geo_y,
        maxx=c_img.geo_x+c_img.geo_w,
        maxy=c_img.geo_y+c_img.geo_h,
        priority=40)
def c_layer(request, w, h, bbox, path, layer_name, style_name):
    return c_img.draw_image(w, h, bbox, path, layer_name)

@wms.layer_provider
def _layers():
    layer1 = util.LayerNode('georef_layer')
    layer2 = util.LayerNode('corner_layer')

    return [layer1, layer2]
