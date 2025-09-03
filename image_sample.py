import flask
import jinja2
from werkzeug.utils import safe_join
from io import BytesIO
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random
import colorcet
from datashader.colors import inferno, Hot, viridis

import util
from util import wms

# Artificial images that draw wherever the display is looking at.
# The edge image also draws informational text.
#
# Requires database schema:
#
# CREATE TABLE sample_layers(user TEXT, enabled TEXT);
#

FONT = ImageFont.truetype('arial.ttf', 12)

MINX, MINY, MAXX, MAXY = -180, -90, 180, 90

STATE_FILE = '/tmp/image_sample.txt'

##
# Blueprint start.
##
BP_STATIC = './static_sample'
BP_TEMPLATE = str(Path(__file__).parent / 'templates_sample')
print(f'@SAMPLE TEMPLATE {BP_TEMPLATE=}')
sample_bp = flask.Blueprint('sample', __name__, static_folder=BP_STATIC, template_folder=BP_TEMPLATE)

# @sample_bp.route('/sample/html', defaults={'page': 'index.html'})
@sample_bp.route('/sample/html/<page>')
def show(page):
    # print('SHOW', page, flask.safe_join(BP_TEMPLATE, page))
    print('SHOW', page, safe_join(BP_TEMPLATE, page))
    try:
        if page.lower().endswith('.html'):
            return flask.render_template(page)
        else:
            return flask.send_from_directory(BP_STATIC, page)
    except jinja2.TemplateNotFound:
        flask.abort(404)

@sample_bp.route('/sample/layers')
def layers():
    """REST API for layer selection

    If no 'layers' parameter, return enabled layers.
    If 'layers' parameter, set enabled layers and return them.
    """

    date = flask.request.args.get('date')
    time = flask.request.args.get('time')
    hour = flask.request.args.get('hour')
    text = flask.request.args.get('text')
    print(f'date [{date}]; time [{time}]; hour [{hour}]; text [{text}]')

    lyrs = flask.request.args.get('layers')
    if lyrs is None:
        row = util.query_db('SELECT enabled FROM sample_layers', [], one=True)
        enabled = row['enabled'] if row else ''
    else:
        conn = util.get_db()
        conn.execute('DELETE FROM sample_layers')
        conn.execute('INSERT INTO sample_layers (user, enabled) VALUES (?,?)', ['', lyrs])
        conn.commit()
        enabled = lyrs

    return flask.jsonify({'layers':enabled})

def get_blueprint():
    """Export the blueprint to the WMS server."""

    return sample_bp

##
# Blueprint end.
##

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
#     return util.linear_legend(colorcet.fire[::2], 'Bottom', 'Top')
    return util.linear_legend(util.tuple_to_rgb(viridis)[::2], 'Bottom', 'Top')

@wms.style('linear2')
def legend_inferno(path, legend):
    return util.linear_legend(util.tuple_to_rgb(inferno)[::2], 'Cold', 'Hot')

@wms.style('categorical')
def legend_cat(path, legend):
    print(f'**LEGEND {path} {legend}')
    cats = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten_longer']
    pal = [(2, 62, 255), (255, 124, 0), (26, 201, 56), (232, 0, 11), (139, 43, 226), (159, 72, 0), (241, 76, 193), (163, 163, 163), (255, 196, 0), (0, 215, 255)]

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

# @wms.layer_provider
# def sample_layers():
#     text_layer = util.LayerNode(name='edge_layer')
#     color_layer = util.LayerNode(name='ellipse_layer')

#     # layers = [text_layer, color_layer]

#     layers = util.LayerNode(
#         abstract='Provides some sample layers.',
#         title='Sample layers',
#         children=[text_layer, color_layer])

#     return layers

def get_state(request):
    """Get the current state of this image.

    :param rqeuest: The Flask request.
    """

    return True

    row = util.query_db('SELECT enabled FROM sample_layers', [], one=True)
    return row['enabled'] if row else None

if __name__=='__main__':
    # Create an example tile.
    #
    img = _make_edge_image(256, 256, (1/2, 1/3, 1/4, 1/5), None, None, None)
    with open('/tmp/img.png', 'wb') as f:
        f.write(img.getbuffer())