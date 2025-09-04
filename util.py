from dataclasses import dataclass
from typing import List, Optional, Callable
from PIL import Image, ImageColor, ImageDraw, ImageFont
import sqlite3

from io import BytesIO

import xml.etree.ElementTree as ET

import flask

FONT = ImageFont.truetype('arial.ttf', 12)

NS = 'http://www.opengis.net/wms'
NS_MS = '"http://mapserver.gis.umn.edu/mapserver'
NS_SLD = 'http://www.opengis.net/sld'
NS_XSI = 'http://www.w3.org/2001/XMLSchema-instance'
NS_XLINK = 'http://www.w3.org/1999/xlink'
ET.register_namespace('', NS)
ET.register_namespace('ms', NS_MS)
ET.register_namespace('sld', NS_SLD)
ET.register_namespace('xlink', NS_XLINK)
ET.register_namespace('xsi', NS_XSI)

ns = {'wms':NS, 'sld':NS_SLD}

class WmsError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message

@dataclass(frozen=True)
class Layer:
    """Holder class for a layer function and its priority."""

    img_func: Callable
    name: Optional[str] = None
    abstract: str = 'Abstract'
    title: str = 'Title'
    minx: float = -180.0
    miny: float = -90.0
    maxx: float = 180.0
    maxy: float = 90.0
    attribution: str = 'WMS server'
    priority: Optional[int] = None
    style: Optional[str] = None

def intersects(bbox, layer):
    """Do the bounding box and layer intersect?"""

    west, south, east, north = bbox
    if layer.minx>east or layer.miny>north or layer.maxx<west or layer.maxy<south:
        # No overlap.
        #
        return False

    return True

def blank_image(request, width, height):
    """Create a blank image.

    width: Width.
    height: Height.
    """

    return Image.new('RGBA', (width, height), color=(0, 255, 0, 0))

class Wms:
    """Gather layer hierarchies and the layer definitions."""

    def __init__(self):
        self._layer_providers = []
        self._layer_trees = []
        self._layers_by_name = {}
        self._styles = {}

        # Database name.
        #
        self.database: str = None

        # Database connection.
        #
        self.conn = None

    def layer_provider(self, func):
        """Decorator for layer provider functions.

        The layer provider function must return a tree of Layer instances."""

        self._layer_providers.append(func)
        self._layer_trees.append(func())

    def layer(self, name=None, *,
        abstract='Abstract',
        title='Title',
        minx=-180,
        miny=-90,
        maxx=180,
        maxy=90,
        attribution='WMS server',
        priority=None,
        style=None):
        """Decorator for layer functions.

        A client can ask for more than layer in a single request.
        The server will respond by stacking the layer images into a
        single image and returning the stacked image. The priority
        specifies the order in which the layers are stacked.
        Layers with higher priorities are stacked above layers with
        lower priorities. For example, a layer with priority 1
        will be stacked on top of a layer with priority 2.

        :param name: The visible name of the layer. If not provided,
            defaults to the wrapped function's __name__ property.
        :param priority: The priority of the layer.
        """

        def decorator(func):

            # Avoid changing the non-local names and breaking the closure.
            #
            n = name
            p = priority
            s = style

            if n is None:
                print('name is none', func.__name__)
                n = func.__name__

            if n in self._layers_by_name:
                raise ValueError(f'Layer "{n}" is already registered.')

            if p is None:
                p = 999 + len(self._layers_by_name)

            if s is not None:
                if not isinstance(s, list):
                    s = [s]
                for i in s:
                    if i not in self._styles:
                        raise ValueError(f'Style "{i}" is not registered')

            print('LAYER', n, func, p)
            layer = Layer(func,
            name=n,
            abstract=abstract,
            title=title,
            minx=minx,
            miny=miny,
            maxx=maxx,
            maxy=maxy,
            attribution=attribution,
            priority=p,
            style=s)
            self._layers_by_name[n] = layer

            return func

        return decorator

    def style(self, name=None):
        """Decorator for style functions.

        Style legends return an image to be used as a legend by the client.
        """

        def decorator(func):
            n = name
            if n is None:
                n = func.__name__

            if n in self._styles:
                raise ValueError(f'Style "{n}" is already registered.')

            print('STYLE', n, func)
            self._styles[n] = func

            return func

        return decorator

    def get_layer_providers(self):
        """Return a list of layer provider functions."""

        return self._layer_providers

    def get_layers(self):
        """Return a dictionary of layers indexed by name."""

        return self._layers_by_name

    def get_layer(self, name):
        """Return the layer specified by name.

        Raise WmsError('LayerNotDefined') if the layer name does not exist.
        """

        if name in self._layers_by_name:
            return self._layers_by_name[name]

        raise WmsError('LayerNotDefined', f'Layer "{name}" is not defined')

    def get_style(self, name):
        """Return the style specified by name.

        Raise WmsError('StyleNotDefined') if the layer name does not exist.
        """

        if name in self._styles:
            return self._styles[name]

        raise WmsError('StyleNotDefined', f'Style "{name}" is not defined')

    def multi_layer(self, request, width, height, bbox, path, layer_names, style_names):
        """Return the union of the listed layers."""

        def intersection(bbox, layer):
            if intersects(bbox, layer):
                west, south, east, north = bbox
                new_minx = max(west, layer.minx)
                new_miny = max(south, layer.miny)
                new_maxx = min(east, layer.maxx)
                new_maxy = min(north, layer.maxy)
                print('OVERLAP', layer.name, new_minx, new_miny, new_maxx, new_maxy)

                return new_minx, new_miny, new_maxx, new_maxy
            else:
                return None

        west, south, east, north = bbox

        # The standard says to draw in the order the layers are given.
        # We'll draw by priority instead.
        #
        names = list(zip(layer_names, style_names))
        names.sort(key=lambda t:self._layers_by_name[t[0]].priority, reverse=True)
        # layer_names.sort(key=lambda name:self._layers_by_name[name].priority, reverse=True)

        # Create a transparent image to draw on.
        #
        img_base = Image.new('RGBA', (width, height), color=(0, 0, 0, 0))
        for name,sname in names:
            layer = self._layers_by_name[name]
            bbox2 = intersection(bbox, layer)
            if bbox2:
                minx2, miny2, maxx2, maxy2 = bbox2
                width2 = int(width / (east-west) * (maxx2-minx2))
                height2 = int(height / (north-south) * (maxy2-miny2))
                img = layer.img_func(request, width2, height2, bbox2, path, name, sname).copy()
                print('SIZE', img.size)
                if 'A' not in img.getbands():
                    alpha = Image.new('L', img.size, color=255)
                    img = img.copy()
                    img.putalpha(alpha)

                x2 = int((minx2-west) / (east-west) * width)
                y2 = int((north-maxy2) / (north-south) * height)
                img_base.paste(img, (x2,y2), img)

        return img_base

    def register_missing_layers(self, hiers):
        """Create Layer instances in the hierarchy list for layer functions
        that were not registered by a provider.
        """

        def find_registered_layers(hiers, registered_names):
            """Find layer names that have been registered by a layer provider."""

            for node in hiers:
                if isinstance(node, LayerNode):
                    if node.name is not None:
                        print('LL', node)
                        if node.name in self._layers_by_name:
                            registered_names.add(node.name)
                        else:
                            raise ValueError(f'Layer "{node.name}" is not registered')
                        # layer = self._layers_by_name[node.name] # ??
                    if node.children:
                        find_registered_layers(node.children, registered_names)
                elif isinstance(node, list):
                    find_registered_layers(node, registered_names)

        registered_names = set()
        find_registered_layers(hiers, registered_names)
        print('REGISTERED', registered_names)

        layers = self.get_layers()
        for layer_name in layers:
            print('--', layer_name)
            if layer_name not in registered_names:
                print(f'Adding {layer_name} to layer hierarchy')
                layer_node = LayerNode(
                    name=layer_name,
                    abstract=layer_name,
                    title=layer_name
                )
                hiers.append(layer_node)

    def build_capabilities(self, request, text, path):#, hiers):
        """Build an XML WMS_Capabilities document to be returned on a GetCapabilities request.

        A template is used (the 'text' parameter) to save lots of hard-to-read code.
        Any existing <Layer> tag is removed and one or more new <Layer> tags are added.
        The hierarchy of tags is defined by the layer hierarchies returned by the layer providers.

        :param text: An XML template.
        :param hiers: A list of layer hierarchies from the layer providers.
        """

        def add_text(el, tag, text):
            tag_el = ET.SubElement(el, tag)
            tag_el.text = text

            return tag_el

        def add_layers(el, hiers):
            for layer in hiers:
                if isinstance(layer, LayerNode):
                    is_container = layer.name is None
                    layer_el = ET.SubElement(el, 'Layer')
                    if is_container:
                        add_text(layer_el, 'Title', layer.title)
                        add_text(layer_el, 'Abstract', layer.abstract)
                    else:
                        layer_data = self._layers_by_name[layer.name]
                        layer_el.set('queryable', '0')
                        layer_el.set('opaque', '0')
                        layer_el.set('cascaded', '0')
                        add_text(layer_el, 'Name', layer_data.name)
                        add_text(layer_el, 'Title', layer_data.title)
                        add_text(layer_el, 'Abstract', layer_data.abstract)
                        add_text(layer_el, 'CRS', 'EPSG:4326')
                        egbb_el = ET.SubElement(layer_el, 'EX_GeographicBoundingBox')
                        add_text(egbb_el, 'westBoundLongitude', str(layer_data.minx))
                        add_text(egbb_el, 'eastBoundLongitude', str(layer_data.maxx))
                        add_text(egbb_el, 'southBoundLatitude', str(layer_data.miny))
                        add_text(egbb_el, 'northBoundLatitude', str(layer_data.maxy))

                        # EPSG:4326 refers to WGS 84 geographic latitude, then longitude.
                        # That is, in this CRS the x axis corresponds to latitude, and the y axis to longitude.
                        # Therefore, reverse x and y.
                        #
                        bb_el = ET.SubElement(layer_el, 'BoundingBox')
                        bb_el.set('CRS', 'EPSG:4326')
                        bb_el.set('minx', str(layer_data.miny))
                        bb_el.set('maxx', str(layer_data.maxy))
                        bb_el.set('miny', str(layer_data.minx))
                        bb_el.set('maxy', str(layer_data.maxx))

                        if layer_data.style:
                            for sname in layer_data.style:
                                # lname = f'{layer_data.name}_legend'
                                # lname = layer_data.name
                                style_el = ET.SubElement(layer_el, 'Style')
                                add_text(style_el, 'Name', sname)
                                add_text(style_el, 'Title', f'{layer_data.title} (style {sname})')
                                img = self._styles[sname](path, sname)
                                legend_el = ET.SubElement(style_el, 'LegendURL')
                                legend_el.set('width', str(img.width))
                                legend_el.set('height', str(img.height))
                                add_text(legend_el, 'Format', 'image/png')
                                resource_el = ET.SubElement(legend_el, 'OnlineResource')
                                resource_el.set('xlink:type', 'simple')
                                p = f'/{path}' if path else ''
                                resource_el.set('xlink:href', f'http://localhost:5000/legend{p}/{sname}')

        #                 attrib_el = ET.SubElement(layer_el, 'Attribution')
        #                 add_text(attrib_el, 'Title', layer.attribution)
                    if layer.children:
                        add_layers(layer_el, layer.children)
                elif isinstance(layer, list):
                    layer_el = ET.SubElement(el, 'Layer')
                    add_text(layer_el, 'Title', 'Layer container')
                    add_layers(layer_el, layer)
                else:
                    raise ValueError(f'Unknown type in layer tree: {type(layer)}.')

        root = ET.fromstring(text)
        capability_el = root.find('wms:Capability', ns)
        layer_el = capability_el.find('wms:Layer', ns)
        if layer_el:
            capability_el.remove(layer_el)

        # Use the layer providers to get a list of layer hierarchies.
        #
        hiers = [lp() for lp in self.get_layer_providers()]
        self.register_missing_layers(hiers)

        add_layers(capability_el, hiers)

        return ET.tostring(root)

wms = Wms()

@dataclass(frozen=True)
class LayerNode:
    """Specify a WMS layer in a layer tree.

    The name specifies a layer. If name is None, this is a container layer.
    The abstract and title are used only for containers."""

    name: Optional[str] = None
    abstract: str = 'Abstract'
    title: str = 'Title'
    children: List['Layer'] = None

def build_exception(e):
    from xml.sax.saxutils import escape

    # Avoid faffing about with XML namespaces in ET by just using the correct template.
    #
    templ = 'exception_code.xml' if e.code else 'exception.xml'
    text = flask.render_template(templ, code=e.code, message=escape(e.message))

    return text

def byte_buffer(img):
    """Save an image into a byte buffer and return the buffer."""

    buf = BytesIO()
    img.save(buf, format='png')
    buf.seek(0)

    return buf

def linear_legend(pal, low='Low', high='High'):
    """Create a linear colorbar and low / high labels.

    The height is fixed at 128 pixels, so the palette should consist of 128 colors.
    """

    H = 128
    CW = 16
    PAD = 3
    if len(pal)!=H:
        raise ValueError(f'Palette length must be {H}')

    # Get the longest text width to determine the width of the legend image.
    #
    text_width = 0
    img = Image.new('RGB', (1,1))
    draw = ImageDraw.Draw(img)
    for t in [low, high]:
        # tw, _ = draw.textsize(t, font=FONT)
        tw = int(draw.textlength(t, font=FONT)+0.5) # TODO use multiline_textbbox for int pixels?
        text_width = max(text_width, tw)
    del draw

    img = Image.new('RGB', (CW+PAD+text_width+PAD,H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Reverse the palette so we can draw from high to low.
    #
    for i,color in enumerate(pal[::-1]):
        draw.line([0, i, CW, i], fill=ImageColor.getrgb(color))

    # s = draw.textsize(low, font=FONT)
    s = int(draw.textlength(low, font=FONT)+0.5)
    draw.text((CW+PAD,H-s-PAD), low, font=FONT, fill=(0,0,0))
    draw.text((CW+PAD, 0), high, font=FONT, fill=(0,0,0))
    del draw

    return img

def categorical_legend(cats, pal):
    """Create a categorical legend: colored squares with labels."""

    CW = 16
    img = Image.new('RGB', (1,1))
    draw = ImageDraw.Draw(img)
    # tw, th = draw.multiline_textsize('\n'.join(cats), font=FONT)
    _, _, tw, th = draw.multiline_textbbox((0,0), '\n'.join(cats), font=FONT)
    del draw

    img = Image.new('RGB', (CW+3+tw+3, th+3), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((CW+3,0), '\n'.join(cats), font=FONT, fill='black')

    h = th/len(pal)
    for i,col in enumerate(pal):
        h0 = i*h+1
        h1 = (i+1)*h+1
        draw.rectangle((0,h0,CW,h1), fill=col)
        draw.line([0, h0, CW,h0, CW,h1, 0,h1, 0, h0])
    del draw

    return img

def tuple_to_rgb(palette):
    """Convert a list of RGB 0..255 tuples into a list of '#rrggbb' strings.

    >>> tuple_to_rgb([(0, 0, 0), (255, 255, 255), (240, 200, 40)])
    ['#000000', '#ffffff', '#f0c828']
    """

    return [f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}' for rgb in palette]

##
# Database stuff.
##
def get_db():
    """Get a database connection. Not thread-safe."""

    # db = getattr(flask.g, '_database', None)
    # if db is None:
    #     db = flask.g._database = sqlite3.connect(wms.database)
    #     db.row_factory = sqlite3.Row

    # return db

    if wms.conn is None:
        wms.conn = sqlite3.connect(wms.database)
        wms.conn.row_factory = sqlite3.Row

    return wms.conn


def query_db(query, args=(), one=False):
    """Query the database.

    :param query: The SQL query (with '?' placeholders).
    :param args: The values to be substituted for the placeholders.
    :param one: If only one row is expected, set this to True to get the first row.
        If this is False, all rows are returned as a list.
    """

    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()

    return (rv[0] if rv else None) if one else rv
