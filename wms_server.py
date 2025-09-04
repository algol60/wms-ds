import importlib
import json
from pathlib import Path
from PIL import Image

from flask import Flask, Response, request, render_template, send_file, url_for, g

import util
from util import wms

# WMS server.
#
# To run locally from a command prompt:
#
# Windows:
# >set FLASK_APP=wms_server
# >set FLASK_ENV=development
# >flask run
#
# Unix:
# $ FLASK_APP=wms_server FLASK_ENV=development flask run
#

WMS_VERSION = '1.3.0'
WMS_FORMAT = 'image/png'

# Config keys.
#
WMS_MODULES = 'WMS_MODULES'
WMS_DATABASE = 'WMS_DATABASE'

app = Flask(__name__)
# app.config.from_json('config.json', silent=False)
app.config.from_file('config.json', json.load)

wms.database = app.config[WMS_DATABASE]

# http://localhost:5000/?
# http://localhost:5000/?SERVICE=WMS&REQUEST=GetCapabilities

# @app.before_first_request
# def before_first_request():
with app.app_context():
    app.logger.info('before_first_request')

    # Import each module declared in WMS_MODULES.
    # Use the filename stem as the module name (just like Python).
    #
    for fnam in app.config[WMS_MODULES]:
        if not fnam.startswith('#'):
            app.logger.info(f'import {fnam}')
            stem = Path(fnam).stem
            spec = importlib.util.spec_from_file_location(stem, fnam)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, 'get_blueprint'):
                print('BLUEPRINT', module)
                app.register_blueprint(module.get_blueprint())

    print(app.url_map)

def _get_mandatory(args, arg):
    """Get the argument of a mandatory parameter.

    Raises WmsError if the parameter is not present.
    """

    value = args.get(arg)
    if value is None:
        raise util.WmsError(None, f'Missing mandatory parameter "{arg}"')

    return value

@app.route('/')
def get_root():
    """An easy place for a human to browse to.

    Provides a clickable link to the GetCapabilities endpoint."""

    args = request.args
    if not args:
        # It's probably a browser, so return a human-readable response.
        #
        url = request.url_root[:-1] + url_for('get_wms', path='', SERVICE='WMS', REQUEST='GetCapabilities')

        return Response(f'Send me a WMS request, such as <a href="{url}">{url}</a>', 404)

    # If there are parameters, pass the request to the WMS endpoint.
    #
    return get_wms()

@app.route('/WMS/')
@app.route('/WMS/<path:path>')
def get_wms(path=''):
    """The endpoint for WMS requests."""

    args = request.args

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

                return Response(util.byte_buffer(img), mimetype=WMS_FORMAT)
        elif req=='GetCapabilities':
            service = _get_mandatory(args, 'SERVICE')
            if service!='WMS':
                raise util.WmsError(None, 'Mandatory parameter "SERVICE=WMS" missing')

            # The base URL depends on the front end.
            # For the simple case of running flask locally (as above),
            # request.url_root works fine.
            # To change this, see the Flask "Configuration values" documentation.
            #
            # We want to pass the path along: if the client specifies the path "/WMS/any/thing/",
            # the capabilities document should use the same path. This allows the client to use
            # the path as a kind of global parameter. For example, "/WMS/day1" and "/WMS/day2"
            # could be used to specify different dates to generate layers from.
            #
            url = request.url_root[:-1] + url_for('get_wms', path=path)

            # Use textual replacement to render the url root
            # (because we don't want to build the entire XML document manually),
            # then generate the <Layer> tree from the imported layers.
            #
            cap_xml = render_template('capabilities.xml', url=url, path=path)
            cap_xml = wms.build_capabilities(request, cap_xml, path)

            return Response(cap_xml, mimetype='application/xml', headers={'Content-Disposition': 'inline'})
        else:
            raise util.WmsError('OperationNotSupported', f'Unrecognised REQUEST: "{req}"')

    except util.WmsError as e:
        print('EXCEPTION', e)
        xml = util.build_exception(e)

        return Response(xml, mimetype='application/xml', headers={'Content-Disposition': 'inline'})

@app.route('/legend/<string:legend>')
@app.route('/legend/<path:path>/<string:legend>')
def get_legend(path='', legend=None):
    """The legend endpoint."""

    app.logger.info(f'Legend: {legend}')
    print('GET LEGEND', legend)

    legend_func = wms.get_style(legend)
    return Response(util.byte_buffer(legend_func(path, legend)), mimetype=WMS_FORMAT)

##
# Database stuff.
##

@app.teardown_appcontext
def _close_connection(exception):
    # print('TEARDOWN')
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
