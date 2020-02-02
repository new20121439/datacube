import rasterio.warp
from osgeo import osr
import sys
import click
import yaml
from pathlib import Path

from datacube.index.hl import Doc2Dataset
import datacube

# Construct metadata dict
# import uuid
from xml.etree import ElementTree  # should use cElementTree..
from dateutil import parser
import os

# Global variable
bands = ['vh', 'vv']

def get_geometry(path):
    with rasterio.open(path) as img:
#         t0=parser.parse(img.get_tag_item('ACQUISITION_START_TIME'))
#         t1=parser.parse(img.get_tag_item('ACQUISITION_STOP_TIME'))
        t0=parser.parse(path.split('/')[-1].split('_')[4])
        t1=parser.parse(path.split('/')[-1].split('_')[5])
        left, bottom, right, top = img.bounds
        crs = str(str(getattr(img, 'crs_wkt', None) or img.crs.wkt))
        corners = {
            'ul': {
                'x': left,
                'y': top
            },
            'ur': {
                'x': right,
                'y': top
            },
            'll': {
                'x': left,
                'y': bottom
            },
            'lr': {
                'x': right,
                'y': bottom
            }
        }
        projection = {'spatial_reference': crs, 'geo_ref_points': corners}

        spatial_ref = osr.SpatialReference(crs)
        t = osr.CoordinateTransformation(spatial_ref, spatial_ref.CloneGeogCS())

        def transform(p):
            lon, lat, z = t.TransformPoint(p['x'], p['y'])
            return {'lon': lon, 'lat': lat}

        extent = {key: transform(p) for key, p in corners.items()}

        return projection, extent, (t0, t1)


def ingest_sentinel1_grd_50m_beta0(path, uuid):
    dc = datacube.Datacube()
    resolver = Doc2Dataset(dc.index)
    projection, extent, (t0, t1) = get_geometry(path)
    images = {v: {'path': path, 'layer': i+1} for i, v in enumerate(bands)}
    p = Path(path)
    scene_name = p.stem[:-11]
    
    result = {
        # 'id': str(uuid.uuid4()), # Generate random uuid
        'id': str(uuid),
        'processing_level': "Level-1",
        'product_type': "sentinel_1_grd_50m_beta0",
        'creation_dt': t0,
        'platform': {
            'code': 'SENTINEL_1A'
        },
        'instrument': {
            'name': 'SAR'
        },
        'extent': {
            'coord': extent,
            'from_dt': str(t0),
            'to_dt': str(t1),
            'center_dt': str(t0 + (t1 - t0) / 2)
        },
        'format': {
            'name': 'GeoTIFF'
        },  # ENVI or BEAM-DIMAP ?
        'grid_spatial': {
            'projection': projection
        },
        'image': {
            'bands': images
        },
        'lineage': {
            'source_datasets': {},
            'ga_label': scene_name
        } 
    }
    print(result)
    dataset, _  = resolver(result,'')
    dc.index.datasets.add(dataset)   
    return True