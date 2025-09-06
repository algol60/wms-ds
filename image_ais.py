import pandas as pd
from util import wms, categorical_legend, linear_legend, LayerNode

import datashader as ds
from datashader import transfer_functions as tf
from datashader.colors import inferno, Hot, viridis
from colorcet import fire, bmw, glasbey

LON = 'LON'
LAT = 'LAT'
TYPE = 'TYPE'

class AIS:
    def __init__(self):
        self.df = pd.read_parquet('D:/data/AIS/March2024.parquet', columns=[LON, LAT, TYPE])
        print(f'@shape {self.df.shape=}')

        df_counts = self.df.groupby(TYPE, as_index=False).size().sort_values(by='size', ascending=False).reset_index().head(10)
        self.top10_df = self.df[self.df[TYPE].isin(df_counts[TYPE])].copy()
        self.top10_df[TYPE] = self.top10_df[TYPE].astype('category')
        self.top10_cats = list(self.top10_df[TYPE].cat.categories)
        self.pal = glasbey[:len(self.top10_cats)]
        self.ckey = {k:v for k,v in zip(self.top10_cats, self.pal)}

        print(f'@shape {self.top10_df.shape=}')
        print(f'@cats {self.top10_cats=}')

        self.minx, self.miny = self.df[['LON', 'LAT']].min()
        self.maxx, self.maxy = self.df[['LON', 'LAT']].max()

ais = AIS()
print(f'@AIS XY {ais.minx=} {ais.miny=} {ais.maxx=} {ais.maxy=}')

@wms.style('nyc_bmw')
def legend_bmy(path, legend):
    return linear_legend(bmw[::2])

@wms.style('nyc_fire')
def legend_fire(path, legend):
    return linear_legend(fire[::2])

@wms.layer(
    'total_ais',
    title='AIS Counts',
    minx=ais.minx,
    maxx=ais.maxx,
    miny=ais.miny,
    maxy=ais.maxy,
    priority=2,
    style='nyc_fire'
)
def _total_ais(request, w, h, bbox, path, layer_name, style_name):
    west, south, east, north = bbox
    x_range = west, east
    y_range = south, north
    cvs = ds.Canvas(plot_width=w, plot_height=h, x_range=x_range, y_range=y_range)
    agg = cvs.points(ais.df, LON, LAT, ds.count())
    # cmap = bmw if style_name=='nyc_bmw' else fire
    cmap = fire
    img = tf.shade(agg, cmap=cmap, how='eq_hist')
    img = tf.dynspread(img, shape='circle', threshold=0.3, max_px=4)

    return img.to_pil()

@wms.style('cat_ais')
def cat_legend(path, legend):
    return categorical_legend(ais.top10_cats, ais.pal)

@wms.layer(
    'category_ais',
    title='AIS Categories',
    minx=ais.minx,
    maxx=ais.maxx,
    miny=ais.miny,
    maxy=ais.maxy,
    priority=3,
    style='cat_ais'
)
def _category_ais(request, w, h, bbox, path, layer_name, style_name):
    west, south, east, north = bbox
    x_range = west, east
    y_range = south, north
    cvs = ds.Canvas(plot_width=w, plot_height=h, x_range=x_range, y_range=y_range)
    agg = cvs.points(ais.top10_df, LON, LAT,  ds.count_cat(TYPE))
    # cmap = bmw if style_name=='nyc_bmw' else fire
    cmap = ais.pal # bmw
    img = tf.shade(agg, color_key=ais.ckey, how='eq_hist')
    img = tf.dynspread(img, shape='circle', threshold=0.3, max_px=4)

    return img.to_pil()

@wms.layer_provider
def _layers():
    total_ais_layer = LayerNode(name='total_ais')
    category_ais_layer = LayerNode(name='category_ais')
    layers = LayerNode(
        abstract='AIS points',
        title='AIS layers',
        children=[total_ais_layer, category_ais_layer]
    )

    return layers
