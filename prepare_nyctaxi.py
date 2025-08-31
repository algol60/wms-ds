import pandas as pd

FNAM = 'D:/data/nyctaxi/yellow_tripdata_2015-01'

df = pd.read_parquet(f'{FNAM}.parquet')
print(df.shape)
print(df.columns)

df = df[[c for c in df.columns if c.endswith(('tude', 'count', 'datetime'))]]
print(df.shape)
print(df.columns)
print(df.head())

df = df.rename(columns={
    'pickup_longitude': 'pickup_x',
    'pickup_latitude': 'pickup_y',
    'tpep_pickup_datetime': 'pickup_dtg',
    'dropoff_longitude': 'dropoff_x',
    'dropoff_latitude': 'dropoff_y',
    'tpep_dropoff_datetime': 'dropoff_dtg'
})
df.pickup_dtg = pd.to_datetime(df.pickup_dtg)
df.dropoff_dtg = pd.to_datetime(df.dropoff_dtg)

print(df.shape)
print(df.columns)
print(df.head())

x0, x1 = -75, -73
y0, y1 = 40, 41.6
df = df[(x0 < df.pickup_x) & (df.pickup_x < x1) & (y0 < df.pickup_y) & (df.pickup_y < y1)]
print(df.shape)
print(df.columns)

df = df[(x0 < df.dropoff_x) & (df.dropoff_x < x1) & (y0 < df.dropoff_y) & (df.dropoff_y < y1)]
print(df.shape)
print(df.columns)

df = df.dropna()
print(df.shape)
print(df.columns)

print(df.describe())

# df.to_parquet(f'{FNAM}_clean.parquet')
