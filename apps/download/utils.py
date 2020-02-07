from sentinelsat import SentinelAPI
import os
from cogeotiff.cog import create_cog
from glob import glob
import gdal, gdalconst
from . import models

import requests
import shutil
from requests.auth import HTTPBasicAuth


def get_name(path):
    """
    path/to/abc.tif ---> return: abc
    """
    name_file=os.path.basename(path)
    name=name_file.split('.')[0]
    return name

def get_subdataset(path):
    dataset=gdal.Open(path, gdal.GA_ReadOnly)
    sub_dataset=dataset.GetSubDatasets()[0]
    sub_dataset=sub_dataset[0]
    return sub_dataset

def make_dest_path(path, suffix):
    """
    'path/abc.tif' + suffix '-any.tif' ---> return: 'path/abc-any.tif'
    """
    dir_name = os.path.dirname(path)
    file_name = get_name(path)
    dest_path = dir_name + '/' + file_name + suffix
    return dest_path

def zip2COG(path):
    """
    Convert zip or tif file to Cloud Optimized Geotif
    """
    if not os.path.exists(path):
        return False
        
    in_folder = os.path.dirname(path)
    out_folder = os.path.join(in_folder, 'COG')
    if not os.path.isdir(out_folder): 
        os.makedirs(out_folder)
    sub_dataset = get_subdataset(path)
    name_output = get_name(path)+'.tif'
    print('Creating {}....'.format(name_output))
    dest_path = out_folder + '/' + name_output
    if not os.path.exists(dest_path): 
        create_cog(sub_dataset, dest_path, compress='LZW')
    return dest_path

def download_image(url, path, user, pass_word):
    """
    Download image from url
    """
    r = requests.get(url, auth=HTTPBasicAuth(user, pass_word), stream=True)
    if r.status_code == 200:
        with open(path, 'wb') as f:
            r.raw.decode_content = True
            shutil.copyfileobj(r.raw, f)
    return True


class sentinel_api:
    """
    Download choosed images
    """
    user = 'tranvandung20121439' 
    password = 'dung20121439'
    api_url = 'https://scihub.copernicus.eu/dhus'
    directory_path = os.environ['HOME'] + '/Datacube/datacube/ingested_data/'
    api = SentinelAPI(user, password, api_url)
    file_format = 'zip'
    thumbnail_format = 'jpg'

    def __init__(self, uuid):
        self.uuid = uuid
        self.product_odata = self.api.get_product_odata(uuid)
   
    def download(self):
        if not os.path.exists(self.file_path):
            self.api.download(self.uuid, self.directory_path)
        return self.file_path

    @property
    def file_path(self):
        file_path = self.directory_path + self.product_odata['title'] + '.' + self.file_format 
        return file_path

    def platformname(self):
        prefix_name = self.product_odata['title'][:2]
        if prefix_name == 'S1':
            return 'SENTINEL-1'
        elif prefix_name == 'S1':
            return 'SENTINEL-2'
        else:
            return None

    @property
    def thumbnail_path(self):
        return self.directory_path + self.product_odata['title'] + '-4326_cog.' + self.thumbnail_format 

    def download_thumbnail(self, task_id):
        task = models.DownloadTask.objects.filter(id=task_id).first()
        link_icon = task.sentinelresult_set.filter(uuid=self.uuid).values_list('link_icon', flat=True)[0]
        download_image(link_icon, self.thumbnail_path, self.user, self.password)
        return self.thumbnail_path


def process_by_snap(path, gpt='~/app/snap/bin/gpt', graph='graph_mlc_50m.xml'):
    dest_path = make_dest_path(path, '.tif')
    if not os.path.exists(dest_path):
        cmd = gpt + '  {} -Pinputfile={} -Poutputfile={}'.format(graph, path, dest_path)
        os.system(cmd)
    return dest_path

def set_metadata(source_path, dest_path):
    # Open the file:
    file_name = get_name(source_path)
    source_path = '/vsizip/{0}/{1}.SAFE'.format(source_path, file_name)
    source_ds = gdal.Open(source_path , gdalconst.GA_ReadOnly)
    metadata=source_ds.GetMetadata()
    gcp = source_ds.GetGCPs()
    gcpproj = source_ds.GetGCPProjection()
    
    ds = gdal.Open(dest_path, gdalconst.GA_Update)

    # resolution from 10m to 50m
    newgcp=[gdal.GCP(tmp.GCPX, tmp.GCPY, tmp.GCPZ, tmp.GCPPixel//5, tmp.GCPLine//5) for tmp in gcp]

    # set metadata
    ds.SetGCPs( newgcp, gcpproj )
    ds.SetMetadata(metadata)
    return True

def toEPSG4326(path):
    """
    Change GEOTIFF image path='folder/abc.tif' to 4326 GEOTIFF 'folder/abc-4326.tif'
    """
    dest_path = make_dest_path(path, '-4326.tif')
    if not os.path.exists(dest_path):
        cmd='gdalwarp -t_srs EPSG:4326 -dstnodata 0 {0} {1}'.format(path, dest_path)
        os.system(cmd)
    return dest_path

def toCOG(path):
    """
    GEOTIFF path='folder/abc.tif' to CLOUD OPTIMIZED GEOTIFF 'folder/abc_cog.tif'
    """
    dest_path = make_dest_path(path, '_cog.tif')
    if not os.path.exists(dest_path):
        create_cog(path, dest_path, compress='LZW')
    return dest_path

def sentinel_1_process(zip_path, gpt, graph):
    path_COG = make_dest_path(zip_path, '-4326_cog.tif')
    if not os.path.exists(path_COG):
        tif_path = process_by_snap(zip_path, gpt, graph)
        set_metadata(zip_path, tif_path)
        path_4326 = toEPSG4326(tif_path)
        path_COG = toCOG(path_4326)
        os.remove(tif_path)
        for path_4326__ in glob(path_4326+'*'):
            os.remove(path_4326__)
    return path_COG
