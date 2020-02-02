from sentinelsat import SentinelAPI
import os
from cogeotiff.cog import create_cog
from glob import glob
import gdal, gdalconst

def get_name(path):
    name_file=os.path.basename(path)
    name=name_file.split('.')[0]
    return name

def get_subdataset(path):
    dataset=gdal.Open(path, gdal.GA_ReadOnly)
    sub_dataset=dataset.GetSubDatasets()[0]
    sub_dataset=sub_dataset[0]
    return sub_dataset

def make_dest_path(path, suffix):
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



class sentinel_api:
    """
    Download choosed images
    """
    user = 'tranvandung20121439'
    password = 'dung20121439'
    api_url = 'https://scihub.copernicus.eu/dhus'
    directory_path = os.environ['HOME'] + '/datacube/original_data/sentinel_1/'
    api = SentinelAPI(user, password, api_url)
    file_format = 'zip'
    
    def __init__(self, uuid):
        self.uuid = uuid
        self.product_odata = self.api.get_product_odata(uuid)
   
    def download(self):
        if not self.check_file():
            self.api.download(self.uuid, self.directory_path)
        return self.file_path()

    def file_path(self):
        file_path = self.directory_path + self.product_odata['title'] + '.' + self.file_format 
        return file_path

    def check_file(self):
        file_path = self.file_path()
        return os.path.exists(file_path)

    def platformname(self):
        prefix_name = self.product_odata['title'][:2]
        if prefix_name == 'S1':
            return 'SENTINEL-1'
        elif prefix_name == 'S1':
            return 'SENTINEL-2'
        else:
            return None


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
    dest_path = make_dest_path(path, '-4326.tif')
    if not os.path.exists(dest_path):
        cmd='gdalwarp -t_srs EPSG:4326 -dstnodata 0 {0} {1}'.format(path, dest_path)
        os.system(cmd)
    return dest_path

def toCOG(path):
    dest_path = make_dest_path(path, '_cog.tif')
    if not os.path.exists(dest_path):
        create_cog(path, dest_path, compress='LZW')
    return dest_path

def sentinel_1_process(zip_path, gpt, graph):
    path_COG = make_dest_path(zip_path, '-4326_cog.tif')
    if os.path.exists(path_COG):
        tif_path = process_by_snap(zip_path, gpt, graph)
        set_metadata(zip_path, tif_path)
        path_4326 = toEPSG4326(tif_path)
        path_COG = toCOG(path_4326)
        os.remove(tif_path)
        for path_4326__ in glob(path_4326+'*'):
            os.remove(path_4326__)
    return path_COG