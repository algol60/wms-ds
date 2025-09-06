import importlib
import tomllib
from pathlib import Path
from PIL import Image
import sys

from litestar import Litestar, Request, Response, get
from litestar.response import Template

import util
from util import wms

# WMS server.
#
# To run locally from a command prompt:
#
# python -m litestar run --debug --reload
#

WMS_VERSION = '1.3.0'
WMS_FORMAT = 'image/png'

# Config keys.
#
WMS_MODULES = 'WMS_MODULES'
WMS_DATABASE = 'WMS_DATABASE'

def startup(app: Litestar):
    with open('config.toml', 'rb') as f:
        config = tomllib.load(f)

    for fnam in config['modules'].values():
        print(f'import {fnam}')
        stem = Path(fnam).stem
        spec = importlib.util.spec_from_file_location(stem, fnam)
        module = importlib.util.module_from_spec(spec)
        sys.modules[stem] = module
        spec.loader.exec_module(module)

        if 'register' in dir(module):
            module.register(app)

def _get_mandatory(args, arg):
    """Get the argument of a mandatory parameter.

    Raises WmsError if the parameter is not present.
    """

    value = args.get(arg)
    if value is None:
        raise util.WmsError(None, f'Missing mandatory parameter "{arg}"')

    return value

@get('/')
async def get_root(request: Request) -> Response:
    """An easy place for a human to browse to.

    Provides a clickable link to the GetCapabilities endpoint."""

    if not request.query_params:
        # It's probably a browser, so return a human-readable response.
        #
        url = request.url_for('get_wms', SERVICE='WMS', REQUEST='GetCapabilities')

        return Response(f'Send me a WMS request, such as <a href="{url}">{url}</a>', status_code=200, media_type='text/html')

    # If there are parameters, pass the request to the WMS endpoint.
    #
    return _get_wms(request, '')

@get('/favicon.ico')
async def favicon() -> bytes:
    return b''

# @app.route('/WMS/')
# @app.route('/WMS/<path:path>')
@get(['/WMS/', '/WMS/{path:path}/'], name='get_wms')
async def get_wms(request: Request, path: str='') -> Response:
    """The endpoint for WMS requests."""

    return _get_wms(request, path)

def _get_wms(request, path):
    args = request.query_params

    try:
        req = _get_mandatory(args, 'REQUEST')
        if req=='GetMap':
            version = _get_mandatory(args, 'VERSION')
            if version!=WMS_VERSION:
                raise util.WmsError(None, f'Only version "{WMS_VERSION}" is supported')
            format = _get_mandatory(args, 'FORMAT')
            if format!=WMS_FORMAT:
                raise util.WmsError('InvalidFormat', f'Only format "{WMS_FORMAT}" is supported')

            width = int(_get_mandatory(args, 'WIDTH'))
            height = int(_get_mandatory(args, 'HEIGHT'))
            layer_names = _get_mandatory(args, 'LAYERS')
            style_names = _get_mandatory(args, 'STYLES')
            crs = _get_mandatory(args, 'CRS')
            bbox = [float(f) for f in _get_mandatory(args, 'BBOX').split(',')]

            if crs=='EPSG:4326':
                # EPSG:4326 refers to WGS 84 geographic latitude, then longitude.
                # That is, in this CRS the x axis corresponds to latitude, and the y axis to longitude.
                # Therefore, reverse x and y.
                # See 6.7.3.3 in the WMS v1.3.0 Specification.
                #
                w, s, e, n = bbox
                bbox = s, w, n, e
            else:
                raise util.WmsError('InvalidCRS', 'Only CRS=EPSG:4326 is valid')

            if ',' in layer_names:
                # The client has asked for multiple layers combined.
                #
                lns = layer_names.split(',')
                sns = style_names.split(',')
                img = wms.multi_layer(request, width, height, bbox, path, lns, sns)

                return Response(util.byte_buffer(img), mimetype=WMS_FORMAT)
            else:
                layer_def = wms.get_layer(layer_names)
                if util.intersects(bbox, layer_def):
                    img = layer_def.img_func(request, width, height, bbox, path, layer_names, style_names)
                else:
                    img = util.blank_image(request, width, height)

                return Response(content=util.byte_buffer(img).read(), media_type=WMS_FORMAT)
        elif req=='GetCapabilities':
            service = _get_mandatory(args, 'SERVICE')
            if service!='WMS':
                raise util.WmsError(None, 'Mandatory parameter "SERVICE=WMS" missing')

            # The base URL depends on the front end.
            # For the simple case of running Flask locally (as above),render
            # request.url_root works fine.
            # To change this, see the Flask "Configuration values" documentation.
            #
            # We want to pass the path along: if the client specifies the path "/WMS/any/thing/",
            # the capabilities document should use the same path. This allows the client to use
            # the path as a kind of global parameter. For example, "/WMS/day1" and "/WMS/day2"
            # could be used to specify different dates to generate layers from.
            #
            # This may work differently in Litestar.
            #
            # url = request.url_root[:-1] + url_for('get_wms', path=path)
            url = request.url_for('get_wms', path=path)

            # Use textual replacement to render the url root
            # (because we don't want to build the entire XML document manually),
            # then generate the <Layer> tree from the imported layers.
            #
            cap_xml = util.render('capabilities.xml', url=url, path=path)
            cap_xml = wms.build_capabilities(request, cap_xml, path)

            return Response(cap_xml, media_type='application/xml', headers={'Content-Disposition': 'inline'})
        else:
            raise util.WmsError('OperationNotSupported', f'Unrecognised REQUEST: "{req}"')

    except util.WmsError as e:
        print('EXCEPTION', e)
        xml = util.build_exception(e)

        return Response(xml, media_type='application/xml', headers={'Content-Disposition': 'inline'})

# @app.route('/legend/<string:legend>')
# @app.route('/legend/<path:path>/<string:legend>')
@get([
    '/legend/{legend:str}',
    '/legend/{path:path}/{legend:str}']
    #, sync_to_thread=True
)
async def get_legend(path: str='', legend: str|None=None) -> Response:
    """The legend endpoint."""

    # app.logger.info(f'Legend: {legend}')
    print(f'GET LEGEND {path=} {legend=}')
    legend = legend.lstrip('/')

    legend_func = wms.get_style(legend)
    return Response(util.byte_buffer(legend_func(path, legend)).read(), media_type=WMS_FORMAT)

##
# Database stuff.
##

# @app.teardown_appcontext
def shutdown():
    # print('TEARDOWN')
    # db = getattr(g, '_database', None)
    # if db is not None:
    #     db.close()

    if wms.conn is not None:
        wms.conn.close()

app = Litestar(
    on_startup=[startup],
    on_shutdown=[shutdown],
    route_handlers=[get_root, get_wms, get_legend, favicon]
)
