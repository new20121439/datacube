from django.db.models import F

from celery.task import task
from celery import chain, group, chord
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
import xarray as xr
import os
import imageio

from utils.data_cube_utilities.data_access_api import DataAccessApi
from utils.data_cube_utilities.dc_utilities import (create_cfmask_clean_mask, create_bit_mask, write_geotiff_from_xr,
                                                    write_png_from_xr, write_single_band_png_from_xr,
                                                    add_timestamp_data_to_xr, clear_attrs)
from utils.data_cube_utilities.dc_chunker import (create_geographic_chunks, create_time_chunks,
                                                  combine_geographic_chunks)
from apps.dc_algorithm.utils import create_2d_plot
from utils.data_cube_utilities.import_export import export_xarray_to_netcdf

from .models import CloudCoverageTask
from apps.dc_algorithm.tasks import DCAlgorithmBase, check_cancel_task, task_clean_up

logger = get_task_logger(__name__)


class BaseTask(DCAlgorithmBase):
    app_name = 'cloud_coverage'


@task(name="cloud_coverage.run", base=BaseTask)
def run(task_id=None):
    """Responsible for launching task processing using celery asynchronous processes

    Chains the parsing of parameters, validation, chunking, and the start to data processing.
    """
    return chain(parse_parameters_from_task.s(task_id=task_id),
                 validate_parameters.s(task_id=task_id),
                 perform_task_chunking.s(task_id=task_id),
                 start_chunk_processing.s(task_id=task_id))()


@task(name="cloud_coverage.parse_parameters_from_task", base=BaseTask, bind=True)
def parse_parameters_from_task(self, task_id=None):
    """Parse out required DC parameters from the task model.

    See the DataAccessApi docstrings for more information.
    Parses out platforms, products, etc. to be used with DataAccessApi calls.

    If this is a multisensor app, platform and product should be pluralized and used
    with the get_stacked_datasets_by_extent call rather than the normal get.

    Returns:
        parameter dict with all keyword args required to load data.
    """
    task = CloudCoverageTask.objects.get(pk=task_id)

    parameters = {
        'platform': task.satellite.datacube_platform,
        'product': task.satellite.get_product(task.area_id),
        'time': (task.time_start, task.time_end),
        'longitude': (task.longitude_min, task.longitude_max),
        'latitude': (task.latitude_min, task.latitude_max),
        'measurements': task.satellite.get_measurements()
    }

    task.execution_start = datetime.now()
    if check_cancel_task(self, task): return
    task.update_status("WAIT", "Parsed out parameters.")

    return parameters


@task(name="cloud_coverage.validate_parameters", base=BaseTask, bind=True)
def validate_parameters(self, parameters, task_id=None):
    """Validate parameters generated by the parameter parsing task

    All validation should be done here - are there data restrictions?
    Combinations that aren't allowed? etc.

    Returns:
        parameter dict with all keyword args required to load data.
        -or-
        updates the task with ERROR and a message, returning None

    """
    task = CloudCoverageTask.objects.get(pk=task_id)
    if check_cancel_task(self, task): return

    dc = DataAccessApi(config=task.config_path)

    #validate for any number of criteria here - num acquisitions, etc.
    acquisitions = dc.list_acquisition_dates(**parameters)

    if len(acquisitions) < 1:
        task.complete = True
        task.update_status("ERROR", "There are no acquistions for this parameter set.")
        return None

    if check_cancel_task(self, task): return
    task.update_status("WAIT", "Validated parameters.")

    if not dc.validate_measurements(parameters['product'], parameters['measurements']):
        task.complete = True
        task.update_status(
            "ERROR",
            "The provided Satellite model measurements aren't valid for the product. Please check the measurements listed in the {} model.".
            format(task.satellite.name))
        return None

    dc.close()
    return parameters


@task(name="cloud_coverage.perform_task_chunking", base=BaseTask, bind=True)
def perform_task_chunking(self, parameters, task_id=None):
    """Chunk parameter sets into more manageable sizes

    Uses functions provided by the task model to create a group of
    parameter sets that make up the arg.

    Args:
        parameters: parameter stream containing all kwargs to load data

    Returns:
        parameters with a list of geographic and time ranges
    """
    if parameters is None:
        return None

    task = CloudCoverageTask.objects.get(pk=task_id)
    if check_cancel_task(self, task): return

    dc = DataAccessApi(config=task.config_path)
    dates = dc.list_acquisition_dates(**parameters)
    task_chunk_sizing = task.get_chunk_size()

    geographic_chunks = create_geographic_chunks(
        longitude=parameters['longitude'],
        latitude=parameters['latitude'],
        geographic_chunk_size=task_chunk_sizing['geographic'])

    time_chunks = create_time_chunks(
        dates, _reversed=task.get_reverse_time(), time_chunk_size=task_chunk_sizing['time'])

    dc.close()
    if check_cancel_task(self, task): return
    task.update_status("WAIT", "Chunked parameter set.")
    return {'parameters': parameters, 'geographic_chunks': geographic_chunks, 'time_chunks': time_chunks}


@task(name="cloud_coverage.start_chunk_processing", base=BaseTask, bind=True)
def start_chunk_processing(self, chunk_details, task_id=None):
    """Create a fully asyncrhonous processing pipeline from paramters and a list of chunks.

    The most efficient way to do this is to create a group of time chunks for each geographic chunk,
    recombine over the time index, then combine geographic last.
    If we create an animation, this needs to be reversed - e.g. group of geographic for each time,
    recombine over geographic, then recombine time last.

    The full processing pipeline is completed, then the create_output_products task is triggered, completing the task.
    """
    if chunk_details is None:
        return None

    parameters = chunk_details.get('parameters')
    geographic_chunks = chunk_details.get('geographic_chunks')
    time_chunks = chunk_details.get('time_chunks')

    task = CloudCoverageTask.objects.get(pk=task_id)

    task.total_scenes = len(geographic_chunks) * len(time_chunks) * (task.get_chunk_size()['time']
                                                                     if task.get_chunk_size()['time'] is not None else
                                                                     len(time_chunks[0]))
    task.scenes_processed = 0
    task.save()

    if check_cancel_task(self, task): return
    task.update_status("WAIT", "Starting processing.")

    logger.info("START_CHUNK_PROCESSING")

    processing_pipeline = (group([
        group([
            processing_task.s(
                task_id=task_id,
                geo_chunk_id=geo_index,
                time_chunk_id=time_index,
                geographic_chunk=geographic_chunk,
                time_chunk=time_chunk,
                **parameters) for time_index, time_chunk in enumerate(time_chunks)
        ]) for geo_index, geographic_chunk in enumerate(geographic_chunks)
    ]) | recombine_geographic_chunks.s(task_id=task_id) | create_output_products.s(task_id=task_id)\
       | task_clean_up.si(task_id=task_id, task_model='CloudCoverageTask')).apply_async()

    return True


@task(name="cloud_coverage.processing_task", acks_late=True, base=BaseTask, bind=True)
def processing_task(self,
                    task_id=None,
                    geo_chunk_id=None,
                    time_chunk_id=None,
                    geographic_chunk=None,
                    time_chunk=None,
                    **parameters):
    """Process a parameter set and save the results to disk.

    Uses the geographic and time chunk id to identify output products.
    **params is updated with time and geographic ranges then used to load data.
    the task model holds the iterative property that signifies whether the algorithm
    is iterative or if all data needs to be loaded at once.

    Args:
        task_id, geo_chunk_id, time_chunk_id: identification for the main task and what chunk this is processing
        geographic_chunk: range of latitude and longitude to load - dict with keys latitude, longitude
        time_chunk: list of acquisition dates
        parameters: all required kwargs to load data.

    Returns:
        path to the output product, metadata dict, and a dict containing the geo/time ids
    """

    chunk_id = "_".join([str(geo_chunk_id), str(time_chunk_id)])
    task = CloudCoverageTask.objects.get(pk=task_id)
    if check_cancel_task(self, task): return

    logger.info("Starting chunk: " + chunk_id)
    if not os.path.exists(task.get_temp_path()):
        return None

    iteration_data = None
    cloud_cover = None
    metadata = {}

    def _get_datetime_range_containing(*time_ranges):
        return (min(time_ranges) - timedelta(microseconds=1), max(time_ranges) + timedelta(microseconds=1))

    times = list(
        map(_get_datetime_range_containing, time_chunk)
        if task.get_iterative() else [_get_datetime_range_containing(time_chunk[0], time_chunk[-1])])
    dc = DataAccessApi(config=task.config_path)
    updated_params = parameters
    updated_params.update(geographic_chunk)
    base_index = (task.get_chunk_size()['time'] if task.get_chunk_size()['time'] is not None else 1) * time_chunk_id
    for time_index, time in enumerate(times):
        updated_params.update({'time': time})
        data = dc.get_dataset_by_extent(**updated_params)

        if check_cancel_task(self, task): return

        if data is None or 'time' not in data:
            logger.info("Invalid chunk.")
            continue

        clear_mask = task.satellite.get_clean_mask_func()(data)
        metadata = task.metadata_from_dataset(metadata, data, clear_mask, updated_params)

        if check_cancel_task(self, task): return

        mosaic, cloud_coverage = task.get_processing_method()
        iteration_data = mosaic(
            data,
            clean_mask=clear_mask,
            intermediate_product=iteration_data,
            no_data=task.satellite.no_data_value,
            reverse_time=task.get_reverse_time())
        cloud_cover = cloud_coverage(
            data, clean_mask=clear_mask, intermediate_product=cloud_cover, no_data=task.satellite.no_data_value)

        if check_cancel_task(self, task): return

        task.scenes_processed = F('scenes_processed') + 1
        task.save(update_fields=['scenes_processed'])

    if iteration_data is None:
        return None

    full_product = xr.merge([iteration_data, cloud_cover])

    path = os.path.join(task.get_temp_path(), chunk_id + ".nc")
    export_xarray_to_netcdf(full_product, path)
    dc.close()
    logger.info("Done with chunk: " + chunk_id)
    return path, metadata, {'geo_chunk_id': geo_chunk_id, 'time_chunk_id': time_chunk_id}


@task(name="cloud_coverage.recombine_geographic_chunks", base=BaseTask, bind=True)
def recombine_geographic_chunks(self, chunks, task_id=None):
    """Recombine processed data over the geographic indices

    For each geographic chunk process spawned by the main task, open the resulting dataset
    and combine it into a single dataset. Combine metadata as well, writing to disk.

    Args:
        chunks: list of the return from the processing_task function - path, metadata, and {chunk ids}

    Returns:
        path to the output product, metadata dict, and a dict containing the geo/time ids
    """
    logger.info("recombine_geographic_chunks() begin!")

    task = CloudCoverageTask.objects.get(pk=task_id)
    if check_cancel_task(self, task): return

    total_chunks = [chunks] if not isinstance(chunks, list) else chunks
    total_chunks = [chunk for chunk in total_chunks if chunk is not None]
    if len(total_chunks) == 0:
        return None
    geo_chunk_id = total_chunks[0][2]['geo_chunk_id']
    time_chunk_id = total_chunks[0][2]['time_chunk_id']

    metadata = {}
    chunk_data = []
    for index, chunk in enumerate(total_chunks):
        metadata = task.combine_metadata(metadata, chunk[1])
        chunk_data.append(xr.open_dataset(chunk[0]))
    combined_data = combine_geographic_chunks(chunk_data)

    path = os.path.join(task.get_temp_path(), "recombined_geo_{}.nc".format(time_chunk_id))
    export_xarray_to_netcdf(combined_data, path)
    logger.info("Done combining geographic chunks for time: " + str(time_chunk_id))
    return path, metadata, {'geo_chunk_id': geo_chunk_id, 'time_chunk_id': time_chunk_id}


@task(name="cloud_coverage.create_output_products", base=BaseTask, bind=True)
def create_output_products(self, data, task_id=None):
    """Create the final output products for this algorithm.

    Open the final dataset and metadata and generate all remaining metadata.
    Convert and write the dataset to variuos formats and register all values in the task model
    Update status and exit.

    Args:
        data: tuple in the format of processing_task function - path, metadata, and {chunk ids}

    """
    logger.info("create_output_products() begin!")

    task = CloudCoverageTask.objects.get(pk=task_id)
    if check_cancel_task(self, task): return

    full_metadata = data[1]
    dataset = xr.open_dataset(data[0])

    task.result_path = os.path.join(task.get_result_path(), "cloud_coverage.png")
    task.mosaic_path = os.path.join(task.get_result_path(), "mosaic.png")
    task.data_path = os.path.join(task.get_result_path(), "data_tif.tif")
    task.data_netcdf_path = os.path.join(task.get_result_path(), "data_netcdf.nc")
    task.final_metadata_from_dataset(dataset)
    task.metadata_from_dict(full_metadata)

    bands = task.satellite.get_measurements() + ['total_pixels', 'total_clear', 'clear_percentage']

    png_bands = ['red', 'green', 'blue']

    export_xarray_to_netcdf(dataset, task.data_netcdf_path)
    write_geotiff_from_xr(task.data_path, dataset.astype('float64'), bands=bands, no_data=task.satellite.no_data_value)
    write_png_from_xr(
        task.mosaic_path,
        dataset,
        bands=png_bands,
        scale=task.satellite.get_scale(),
        no_data=task.satellite.no_data_value)
    write_single_band_png_from_xr(
        task.result_path,
        dataset,
        band='clear_percentage',
        color_scale=task.color_scale_path,
        no_data=task.satellite.no_data_value)

    dates = list(map(lambda x: datetime.strptime(x, "%m/%d/%Y"), task._get_field_as_list('acquisition_list')))
    if len(dates) > 1:
        task.plot_path = os.path.join(task.get_result_path(), "plot_path.png")
        create_2d_plot(
            task.plot_path,
            dates=dates,
            datasets=task._get_field_as_list('clean_pixel_percentages_per_acquisition'),
            data_labels="Clean Pixel Percentage (%)",
            titles="Clean Pixel Percentage Per Acquisition")

    logger.info("All products created.")
    # task.update_bounds_from_dataset(dataset)
    task.complete = True
    task.execution_end = datetime.now()
    task.update_status("OK", "All products have been generated. Your result will be loaded on the map.")
    return True