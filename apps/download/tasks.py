from celery.task import task
from celery import chain
from celery.utils.log import get_task_logger
from datetime import datetime

from .models import DownloadTask, SentinelResult
from apps.dc_algorithm.tasks import DCAlgorithmBase

''' USer of sentinelsat'''
from sentinelsat import SentinelAPI, geojson_to_wkt
from geojson import Polygon

user='tranvandung20121439'
password='dung20121439'
api_url='https://scihub.copernicus.eu/dhus'

logger = get_task_logger(__name__)


class BaseTask(DCAlgorithmBase):
    # TODO: replace the __app__name var with download - avoids the auto rename.
    __app__name = 'download'

@task(name="download.run", base=BaseTask)
def run(task_id=None):
    """Responsible for launching task processing using celery asynchronous processes
    Chains the parsing of parameters, validation, chunking, and the start to data processing.
    """
    chain(
        parse_parameters_from_task.s(task_id=task_id),
        sentinel_query_task.s(task_id=task_id),
        create_outputs.s(task_id=task_id)
    ).apply_async()
    return True

@task(name="download.parse_parameters_from_task", base=BaseTask)
def parse_parameters_from_task(task_id=None):
    """Parse out required DC parameters from the task model.
    See the DataAccessApi docstrings for more information.
    Parses out platforms, products, etc. to be used with DataAccessApi calls.
    If this is a multisensor app, platform and product should be pluralized and used
    with the get_stacked_datasets_by_extent call rather than the normal get.
    Returns:
        parameter dict with all keyword args required to load data.
    """
    task = DownloadTask.objects.get(pk=task_id)

    parameters = {
        # TODO: If this is not a multisensory app, uncomment 'platform' and remove 'platforms'
        # 'platform': task.satellite.datacube_platform,
        'platforms': task.satellite.get_platforms(),
        # TODO: If this is not a multisensory app, remove 'products' and uncomment the line below.
        # 'product': task.satellite.get_product(task.area_id),
        'products': task.satellite.get_products(task.area_id),
        'time': (task.time_start, task.time_end),
        'longitude': (task.longitude_min, task.longitude_max),
        'latitude': (task.latitude_min, task.latitude_max),
        'measurements': task.satellite.get_measurements()
    }
    logger.info('Parsed out parameters: \n'.format(parameters))
    task.execution_start = datetime.now()
    task.update_status("WAIT", "Parsed out parameters.")
    return parameters

@task(name="download.sentinel_query_task", base=BaseTask)
def sentinel_query_task(parameters, task_id=None):
    def validate_name(string: str):
        return string.replace('_', '-')

    def order_by(order_by='ingestiondate', ascending=False):
        prefix_order_by = '+' if ascending else '-'
        order_by = prefix_order_by + order_by
        return order_by

    task = DownloadTask.objects.get(pk=task_id)
    platformname = parameters['products']
    longitude_min, longitude_max = parameters['longitude']
    latitude_min, latitude_max = parameters['latitude']


    extent = Polygon([[(longitude_min, latitude_max),
                    (longitude_max, latitude_max),
                    (longitude_max, latitude_min),
                    (longitude_min, latitude_min),
                    (longitude_min, latitude_max)]])

    extent = geojson_to_wkt(extent)
    order_by = order_by('ingestiondate', ascending=False)
    api = SentinelAPI(user, password, api_url)
    products = api.query(extent,
                     date=(parameters['time']),
                     platformname='SENTINEL-1',
                     producttype='GRD',
                     orbitdirection='DESCENDING')

    products_df = api.to_dataframe(products)
    task.execution_start = datetime.now()
    task.update_status('WAIT', "Download Sentinel Query. ")
    return products_df

@task(name="download.create_outputs", base=BaseTask)
def create_outputs(product_df, task_id):
    task = DownloadTask.objects.get(pk=task_id)
    if product_df.empty:
        task.complete = True
        task.execution_end = datetime.now()
        task.update_status('OK', 'Create Outputs. Empty')
        return True
    uuid = product_df['uuid'].to_list()
    title = product_df['title'].to_list()
    link_icon = product_df['link_icon'].to_list()
    link = product_df['link'].to_list()
    size = product_df['size'].to_list()
    producttype = product_df['producttype'].to_list()
    endposition = product_df['endposition'].to_list()
 
    for i in range(len(uuid)):
        task.sentinelresult_set.create(
            uuid=uuid[i],
            title=title[i],
            link_icon=create_authentication_url(link_icon[i], user, password),
            link=create_authentication_url(link[i], user, password),
            size=size[i],
            producttype=producttype[i],
            endposition=endposition[i]       
        )
    task.complete = True
    task.execution_end = datetime.now()
    task.update_status('OK', 'Create Outputs.')
    return True


def create_authentication_url(url, user, password):
    index = url.find('://') + 3
    authentication_url = url[:index] + user + ':' + password + '@' + url[index:]
    return authentication_url