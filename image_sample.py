from werkzeug.utils import safe_join
from PIL import Image, ImageDraw, ImageFont
import random
import colorcet

import util
from util import wms

from litestar import Litestar, get
from litestar.static_files import create_static_files_router

# Artificial images that draw wherever the display is looking at.
# The edge image also draws informational text.
#

FONT = ImageFont.truetype('arial.ttf', 12)

MINX, MINY, MAXX, MAXY = -180, -90, 180, 90

# STATE_FILE = '/tmp/image_sample.txt'

def _random_color():
    return tuple(random.randint(0, 191) for _ in range(3))

def _add_text(w, h, bbox, draw, text, fill=(0, 0, 0)):
    # tw, th = draw.multiline_textsize(text, font=FONT)
    _, _, tw, th = draw.multiline_textbbox((0,0), text, font=FONT)
    draw.rectangle([(1, 1), (tw+1, th+1)], fill=(255, 255, 255, 192))
    draw.text((1, 1), text, font=FONT, fill=fill)

@wms.style('linear')
def legend_lin(path, legend):
    print(f'**LEGEND {path} {legend}')
    return util.linear_legend(colorcet.blues[::2], 'Bottom', 'Top')

@wms.style('linear2')
def legend_inferno(path, legend):
    print(f'**LEGEND {path} {legend}')
    return util.linear_legend(colorcet.fire[::2], 'Cold', 'Hot')

@wms.style('categorical')
def legend_cat(path, legend):
    print(f'**LEGEND {path} {legend}')
    cats = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten_longer']
    pal = colorcet.b_glasbey_hv[:len(cats)]

    return util.categorical_legend(cats, pal)

@wms.layer('edge_layer',
        abstract='Provides a transparent image with multi-colored edges.',
        title='Edge layer',
        minx=MINX,
        miny=MINY,
        maxx=MAXX,
        maxy=MAXY,
        style=['linear', 'linear2'])
def _make_edge_image(request, w, h, bbox, path, layer_name, style_name):
    """Make a sample image consisting of colored edges and some text."""

    img = Image.new('RGBA', (w, h), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.line([(0,0), (w-1, 0)], fill=(255, 0, 0), width=0)
    draw.line([(w-1, 0), (w-1, h-1)], fill=(0, 255, 0), width=0)
    draw.line([(w-1, h-1), (0, h-1)], fill=(0, 0, 255), width=0)
    draw.line([(0, h-1), (0, 0)], fill=(0, 0, 0), width=0)

    color = _random_color()
    draw.line([(0,0), (w-1, h-1)], fill=color)
    draw.line([(0,h-1), (w-1, 0)], fill=color)

    west, south, east, north = bbox
    text = f'wxh={w}x{h}\nw={west} e={east}\ns={south} n={north}\npath={path}\nlayer={layer_name}'
    state = get_state(request)
    if state:
        text = f'{text}\nstate="{state}"'

    fill = (0, 0, 127) if style_name=='linear' else (127, 0, 0)
    _add_text(w, h, bbox, draw, text, fill)
    del draw

    return img

@wms.layer('ellipse_layer',
        abstract='An image consisting of an ellipse.',
        title='Ellipse layer',
        minx=MINX,
        miny=MINY,
        maxx=MAXX,
        maxy=MAXY,
        style='categorical')
def _make_ellipse_image(request, w, h, bbox, path, layer_name, style_name):
    """Make a sample image consisting of an ellipse touching the edge of the bounding box."""

    print(f'@ELLIPSE {w=} {h=}')
    img = Image.new('RGBA', (w, h), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = _random_color()
    draw.ellipse([(0, 0), (w-1, h-1)], outline=color)
    del draw

    return img

@wms.layer_provider
def sample_layers():
    text_layer = util.LayerNode(name='edge_layer')
    color_layer = util.LayerNode(name='ellipse_layer')

    layers = util.LayerNode(
        abstract='Provides some sample layers.',
        title='Sample layers',
        children=[text_layer, color_layer])

    return layers

@get('/sample/handler')
async def sample_handler() -> str:
    """An example of dynamically adding a route."""

    return 'This is an example of a handler.'

def register(app: Litestar):
    """Allow Litestar to register handlers."""

    print('sample register')
    app.register(sample_handler)

def get_state(request):
    """Get the current state of this image.

    Here to demonstrate dynamic layer drawing (apart from the actual image).

    :param request: The request.
    """

    import uuid
    return str(uuid.uuid4())

if __name__=='__main__':
    # Create an example tile.
    #
    img = _make_edge_image(256, 256, (1/2, 1/3, 1/4, 1/5), None, None, None)
    with open('/tmp/img.png', 'wb') as f:
        f.write(img.getbuffer())