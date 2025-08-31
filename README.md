# WMS-DS: a WMS server for Datashader tiles

WMS-DS is a Web Map Service (WMS) implementation. It is written in [Python](https://www.python.org/), and is implemented as a [Flask](http://flask.pocoo.org/) application. It implements version 1.3.0 of the WMS specification, specified by the [OpenGIS Web Map Service (WMS) Implementation Specification](http://portal.opengeospatial.org/files/?artifact_id=14416).

## Introduction

(This section reproduces the introduction from the WMS Specification v1.3.0.)

A Web Map Service (WMS) produces maps of spatially referenced data dynamically from geographic information. This International Standard defines a “map” to be a portrayal of geographic information as a digital image file suitable for display on a computer screen. A map is not the data itself. WMS-produced maps are generally rendered in a pictorial format such as PNG, GIF or JPEG, or occasionally as vector-based graphical elements in Scalable Vector Graphics (SVG) or Web Computer Graphics Metafile (WebCGM) formats.

This International Standard defines three operations: one returns service-level metadata; another returns a map whose geographic and dimensional parameters are well-defined; and an optional third operation returns information about particular features shown on a map. Web Map Service operations can be invoked using a standard web browser by submitting requests in the form of Uniform Resource Locators (URLs). The content of such URLs depends on which operation is requested. In particular, when requesting a map the URL indicates what information is to be shown on the map, what portion of the Earth is to be mapped, the desired coordinate reference system, and the output image width and height. When two or more maps are produced with the same geographic parameters and output size, the results can be accurately overlaid to produce a composite map. The use of image formats that support transparent backgrounds (e.g. GIF or PNG) allows underlying maps to be visible. Furthermore, individual maps can be requested from different servers. The Web Map Service thus enables the creation of a network of distributed map servers from which clients can build customized maps.

This International Standard applies to a Web Map Service instance that publishes its ability to produce maps rather than its ability to access specific data holdings. A basic WMS classifies its geographic information holdings into “Layers” and offers a finite number of predefined “Styles” in which to display those layers. The International Standard supports only named Layers and Styles, and does not include a mechanism for user-defined symbolization of feature data.

## Description

WMS-DS accepts HTTP `GetMap` requests that include a geographic bounding box (expressed as a south-west corner and north-east corner in EPSG:4326 coordinates) and an image size (expressed as a width and height in pixels) and returns a PNG format image with the specified size of the area in the bounding box. An HTTP `GetCapabilities` request returns an XML document that tells the client what images are supported. The HTTP `GetFeatureInfo` reqest is not currently implemented.

The WMS server can return any image. For example:
- an artificial image that draws markers at particular locations;
- an artificial image that draws an image wherever the user is looking;
- a georeferenced image;
- an image produced by the Datashader library.

Datashader images were the impetus for creating WMS-DS, to be able to visualise millions of data points in ArcGIS Pro.

## Implementation

WMS-DS provides a framework to implement a WMS server. The layers and styles that are provided by the server are implemented in Python modules, in such a way that layers and styles can be independent of each other, or can reuse the same code. For example, one module can provide layers showing different views of the [NYC taxi data](https://www1.nyc.gov/site/tlc/about/tlc-trip-record-data.page), reusing code to produce similar layers, or layers with different style, while a different module can produce a georeferenced image. Each module can be developed independently of the others. Howwever, care must be taken with layer names: since layer names are global, it is possible for two modules to provide layers with the same name. The WMS server will check for this and raise an exception if a layer name is registered more than once.

Python functions that return map images are marked with decorators that register the functions to the WMS server. The registrations are used to build and provide the XML document returned by the WMS `GetCapabilities` request. Further decorators provide style definitions for layers, and the ability to define the layers in a hierarchy.

Each module can use a Flask blueprint to provide further functionality in the form of REST endpoints or web pages. For example, one of the Datashader examples shows OpenSky data. A Flask blueprint route can provide an endpoint to select the airlines to be shown in the image, and a web page can allow airlines to be selected by a user, then call the REST endpoint to update the session state. See the [Flask blueprints documentation](http://flask.pocoo.org/docs/1.0/blueprints/) for more information.

### The state database

The WMS server provides an sqlite3 database for storing state or other data. The implementation is as described at [Using SQLite 3 with Flask](http://flask.pocoo.org/docs/1.0/patterns/sqlite3/). The `util` module provides `get_db()` (using the `sqlite3.Row` row factory) and `query_db` functions.

The sqlite3 database file must be specified in Flask's `config.json` config file, using the "`WMS_DATABASE`" key. Any schemas used by a module must be created in the database before use.

For a "few" users (for some definition of "few") just using the database for storing state (such as variables defining how an image is created), it is expected that an sqlite3 database is sufficient.

### Dependencies

WMS-DS requires Anaconda3 Python (for Flask and PIL). Individual modules nay have further requirements (for example, [Datashader](http://datashader.org/)).

## Running WMS-DS

Since WMS-DS is a Flask application, it is started according to the Flask applications.

On Windows:

```cmd
set FLASK_APP=wms_server
set FLASK_ENV=development
python -m flask run
```

On Linux:

```bash
FLASK_APP=wms_server FLASK_ENV=development python -m flask run
```

After starting, the WMS is available at `http://localhost:5000/?`.

## Layer functions

(See the image_*.py modules provided with WMS-DS for examples.)

Layer functions provide images in PIL format in response to WMS "GetMap" requests. Layer functions are defined as follows. (The name of the function is irrelevant.)

```python
def layer_function(request, w, h, bbox, path, layer_name, style_name):
    ...
```

- request: the Flask request object. THis is provided for session control, authorisation, etc.
    The reminaing parameters can be extracted from the request, but are provided for convenience.
- w: the width of the image to be returned
- h: the height of the image to be returned
- bbox: the bounding box of the requested image. This is a 4-tuple consisting of (minx, miny, maxx, maxy), ie the lower-left and upper-right corners of the bounding box. The values are specified as EPSG:4326 longitudes and latitudes.
- path: the URL path used in the HTTP request.
- layer_name: the requested layer.
- style_name: the requested style.

The path is specified by the client. It can be used for any desired purposes; for example, different path names could specify different dates for data. If there is only one set of data, the path can be ignored.

The layer_name is the layer requested by the client. If the function only implements one layer, then layer_name can be ignored.

The style_name is the style requested by the client. For example, if a layer has styles 'light' and 'dark', appropriate colors can be used to generate the resulting image.

The function must return a PIL image of shape (w,h) representing the rectangle specified by the bounding box.

### Registering layer functions

Layer functions are registered using the `wms.layer()` decorator. This is defined as:

```python
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
```

The `name` must be specified; this is the name of the layer that is requested by the client and passed to the layer function as `layer_name`. The `abstract`, `title`, and `attribution` parameters provide human-readable information. The `minx`, `miny`, `maxx`, and `maxy` parameters are the bounding box of the layer. The `priority` is an integer that specifies the drawing order if multiple layers are requested by the client. (The standard specifies that layers are draw in the order that they are requested, but the priority overrides this.) The `style` parameter specifies a list of style names (see below).

A layer function is defined and registered as follows.

```python
@wms.layer('the_layer', ...)
def my_layer_function(...):
    ...
```

Using the decorator specifies a one-to-one mapping between a layer name and a function. Calling the decorator function directly allows one function to be registered for multiple layers. For example:

```python
def layers_function(...):
    ...

for i in range(N):
    wms.layer(f'layer{i}', ...)(layers_function)
```

## Styles

Styles are defined by registering style functions with the `wms.style()` decorator. A style function must return an image (in PIL format) which can be used as a legend by the WMS client. The utility functions `categorical_legend` and `linear_legend` can be used to create suitable legend images.

When a layer is requested by a WMS client, a style can be optionally provided. The style is passed to a layer function in the `style_name` parameter. (If no style is requested, the style is the empty string.) There is no connection between the legend image returned by the style function and the style_name passed to the layer function, although the layer function should return a map image that reflects the style of the legend.

## Layer providers

A module can optionally define a layer provider using the `wms.layer_provider()` decorator. A layer provider function uses the `LayerNode` class to provide a hierarchical organisation of registered layers.

If no layer provider is registered, or a layer provider is registered but not all layers are specified, the remaining layers are organised in a list.

## Blueprints

Blueprints are created in a module as per the Flask blueprint documentation. A blueprint is registered to Flask by providing a `get_blueprint()` function in the module. If present, the WMS server calls this function when the module is loaded to get the blueprint, and registers the blueprint with Flask. See the `image_sample.py` module for an example.

## Initialisation

Python modules to be included in the WMS server are specified in the `config.json` file as members of a list under the key "WMS_MODULES". Modules are specified as filenames.

Modules can be commented out by inserting a '#' at the beginning of a filename string.

Modules are loaded using Flask's `app.before_first_request()` functionality. This means that module code is not run when the Flask app is run, but when the first client request is received. This is done because Flask is multi-threaded; loading modules at start time means that they couldbe loaded more than once.

Depending on what modules do when they run (for example, loading data), the first request can wait some time to get a response. To avoid this, immediately after starting Flask, use a web browser to manually browse to the root URL (on a standalone server running on the local system:) `http://localhost:5000/?`).
