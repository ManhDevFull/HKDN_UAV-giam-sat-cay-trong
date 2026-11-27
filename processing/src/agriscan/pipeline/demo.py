"""Small reproducible scene: healthy/stressed vegetation, soil and shadows."""

from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin


def create_demo_mosaic(path: Path) -> None:
    rng = np.random.default_rng(42)
    noise = rng.uniform(-0.006, 0.006, (80, 100)).astype('float32')
    red, green, nir = 0.12 + noise, 0.20 + noise, 0.55 + noise
    red[20:40, 20:40], nir[20:40, 20:40] = .24 + noise[20:40, 20:40], .40 + noise[20:40, 20:40]
    red[:10], nir[:10] = .26 + noise[:10], .28 + noise[:10]
    red[60:70], green[60:70], nir[60:70] = .004, .005, .008
    values = np.stack([red, green, nir]).astype('float32')
    values[:, -3:, -3:] = -9999.0
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, 'w', driver='GTiff', height=80, width=100, count=3, dtype='float32',
                       crs='EPSG:32648', transform=from_origin(684000, 1198000, .1, .1),
                       nodata=-9999.0, compress='deflate') as image:
        image.write(values)
        for index, name in enumerate(('red', 'green', 'nir'), 1):
            image.set_band_description(index, name)
        image.update_tags(units='relative_signal', band_order='red,green,nir', synthetic='true')
