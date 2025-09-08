import numpy as np
import pandas as pd
import datashader as ds
from datashader import transfer_functions as tf
from datashader.colors import inferno, Hot, viridis
from colorcet import fire, bmw
import seaborn as sns

import util
from util import wms

# Drop-offs are reddish.
# Pickups are blueish-greenish.
#
PAL_DROPS = [tuple(int(c*255) for c in col)[:3] for col in sns.color_palette('hot_r')]
PAL_PICKS = [tuple(int(c*255) for c in col)[:3] for col in sns.color_palette('viridis_r')]
# PAL_DROPS = [tuple(int(c*255) for c in col)[:3] for col in sns.light_palette('Red')]
# PAL_PICKS = [tuple(int(c*255) for c in col)[:3] for col in sns.light_palette('Green')]

# PAL_DROPS = [tuple(int(c*255) for c in col)[:3] for col in sns.color_palette('PuRd')]

FNAM = '/data/nyctaxi/yellow_tripdata_2015-01.parquet'

class NycTaxiImages:
    def __init__(self, *, fnam=FNAM, logger=None, **kwargs):
        info = logger.info if logger else print

        info(f'Loading {FNAM} ...')
        self.df = pd.read_parquet(FNAM, columns=['passenger_count', 'pickup_x', 'pickup_y', 'dropoff_x', 'dropoff_y'])
        # self.df = self.df.dropna(axis='index')
        info(f'Rows: {len(self.df):,}')

        self.x0 = min(self.df.dropoff_x.min(), self.df.pickup_x.min())
        self.x1 = max(self.df.dropoff_x.max(), self.df.pickup_x.max())
        self.y0 = min(self.df.dropoff_y.min(), self.df.pickup_y.min())
        self.y1 = max(self.df.dropoff_y.max(), self.df.pickup_y.max())
        info(f'Bounding box: w={self.x0}, e={self.x1}, s={self.y0}, n={self.y1}')

        self.df_count = self.df[['pickup_x', 'pickup_y']].append(self.df[['dropoff_x', 'dropoff_y']].rename(columns={'pickup_y':'pickup_y'}), ignore_index=True, sort=False)
        self.df_count = self.df_count.rename(columns={'pickup_x':'x', 'pickup_y':'y'})

taxis = NycTaxiImages()

@wms.style('nyc_bmw')
def legend_bmy(path, legend):
    return util.linear_legend(bmw[::2])

@wms.style('nyc_fire')
def legend_fire(path, legend):
    return util.linear_legend(fire[::2])

@wms.layer('total_counts',
        abstract='Shows total pickup/dropoff counts from the NYC taxi data.',
        title='Total counts',
        minx = taxis.x0,
        maxx = taxis.x1,
        miny = taxis.y0,
        maxy = taxis.y1,
        priority=2,
        style=['nyc_bmw', 'nyc_fire'])
def _total_counts(request, w, h, bbox, path, layer_name, style_name):
    west, south, east, north = bbox
    x_range = west, east
    y_range = south, north
    df = taxis.df_count
    cvs = ds.Canvas(plot_width=w, plot_height=h, x_range=x_range, y_range=y_range)
    agg = cvs.points(df, 'x', 'y',  ds.count())
    cmap = bmw if style_name=='nyc_bmw' else fire
    img = tf.shade(agg, cmap=cmap, how='eq_hist')
    img = tf.dynspread(img, threshold=0.3, max_px=4)

    return img.to_pil()

def _create_image90(request, w, h, bbox, path, layer_name, style_name):
    """Virtual layer.

    This function implements two layers, depending on layer_name.
    Both layers do the same thing, but on different columns.
    """

    if layer_name=='pickup':
        xcol, ycol = 'pickup_x', 'pickup_y'
        cmap = viridis
    else:
        xcol, ycol = 'dropoff_x', 'dropoff_y'
        cmap = inferno

    west, south, east, north = bbox
    x_range = west, east
    y_range = south, north
    df = taxis.df
    cvs = ds.Canvas(plot_width=w, plot_height=h, x_range=x_range, y_range=y_range)
    agg = cvs.points(df, xcol, ycol, ds.count('passenger_count'))
    img = tf.shade(agg.where(agg>np.percentile(agg, 90)), cmap=cmap, how='eq_hist')
    img = tf.dynspread(img, threshold=0.3, max_px=4)

    return img.to_pil()

def _register_passenger_counts():
    """Register a function to implement two different layers.

    This demonstrates using a single function to implement two similar layers,
    in this case, the NYC taxi data with pickups in one layer and dropoffs in another.
    Each layer has its own bounding box and colormap.
    """

    lnames = []
    for lname,xcol,ycol in [['pickup', 'pickup_x', 'pickup_y'], ['dropoff', 'dropoff_x', 'dropoff_y']]:

        # Discover the bounding box for this xcol,ycol.
        #
        minx, miny = taxis.df[[xcol, ycol]].min()
        maxx, maxy = taxis.df[[xcol, ycol]].max()

        # Now we can manually pass the unique function to the layer decorator.
        #
        wms.layer(lname,
            abstract=f'{lname.capitalize()} abstract',
            title=f'{lname.capitalize()} layer',
            minx=minx,
            miny=miny,
            maxx=maxx,
            maxy=maxy,
            priority=10+len(lnames)
        )(_create_image90)
        lnames.append(lname)

    return lnames

_lnames = _register_passenger_counts()
print(f'LNAMES: {_lnames}')

@wms.layer('merged_layer',
        abstract='Shows pickups vs dropoffs.',
        title='Pickup / dropoff passenger counts',
        minx = taxis.x0,
        maxx = taxis.x1,
        miny = taxis.y0,
        maxy = taxis.y1,
        priority=5)
def _merged_images(request, w, h, bbox, path, layer_name, style_name):
    """Show the places with more dropoffs than pickups, and vice versa."""

    west, south, east, north = bbox
    x_range = west, east
    y_range = south, north
    df = taxis.df
    cvs = ds.Canvas(plot_width=w, plot_height=h, x_range=x_range, y_range=y_range)

    picks = cvs.points(df, 'pickup_x',  'pickup_y',  ds.count('passenger_count'))
    picks = picks.rename({'pickup_x': 'x', 'pickup_y': 'y'})

    drops = cvs.points(df, 'dropoff_x', 'dropoff_y', ds.count('passenger_count'))
    drops = drops.rename({'dropoff_x': 'x', 'dropoff_y': 'y'})

    more_picks = tf.shade(picks.where(picks > drops), cmap=PAL_PICKS, how='log')
    more_drops = tf.shade(drops.where(drops > picks), cmap=PAL_DROPS, how='log')

    img = tf.stack(more_picks, more_drops)
    img = tf.dynspread(img, threshold=0.3, max_px=4)

    return img.to_pil()

@wms.layer_provider
def nyc_taxi_layers():
    nyc_layer = util.LayerNode(name='merged_layer')
    totals_layer = util.LayerNode(name='total_counts')
    pcount_layer, dcount_layer = [util.LayerNode(name=n) for n in _lnames]

    layers = util.LayerNode(
        abstract='Different views of the NYC taxi data.',
        title='NYC taxi layers',
        children=[nyc_layer, totals_layer, pcount_layer, dcount_layer]
    )

    return layers
