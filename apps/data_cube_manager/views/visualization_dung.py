# Copyright 2016 United States Government as represented by the Administrator
# of the National Aeronautics and Space Administration. All Rights Reserved.
#
# Portion of this code is Copyright Geoscience Australia, Licensed under the
# Apache License, Version 2.0 (the "License"); you may not use this file
# except in compliance with the License. You may obtain a copy of the License
# at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# The CEOS 2 platform is licensed under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.forms.models import model_to_dict
from django.conf import settings
from django.views import View
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required

from urllib import parse
from collections import OrderedDict
import json
import yaml
import uuid
import shutil

from apps.data_cube_manager import models
from apps.data_cube_manager import forms
from apps.data_cube_manager import utils
from apps.data_cube_manager import tasks


class DataCubeVisualization(View):
    """Visualize ingested and indexed Data Cube regions using leaflet"""

    def get(self, request):
        """Main end point for viewing datasets and their extents on a leaflet map"""

        context = {'form': forms.VisualizationForm()}
        context['dataset_types'] = models.DatasetType.objects.using('agdc').filter(
            definition__has_keys=['measurements'])
        # print('DataCubeVisualization: ', context) # Dung
        return render(request, 'data_cube_manager/visualization_dung.html', context)

class GetIngestedAreas(View):
    """Get a dict containing details on the ingested areas, grouped by Platform"""

    platform_filter = 'metadata__platform__code'
    def get(self, request):
        """Call a synchronous task to produce a dict containing ingestion details
        Work performed in a synchrounous task so the execution is done on a worker rather than on
        the webserver. Gets a dict like:
            {Landsat_5: [{}, {}, {}],
            Landsat_7: [{}, {}, {}]}
        """
        platforms = get_platforms(models, field='metadata')
        # print('GetIngestedAreas platform: ', platforms) # dung
        ingested_area_details = {
            platform: get_dataset_by_platform(models, self.platform_filter, platform)
            for platform in platforms
        }
        print('GetIngestedAreas: ', ingested_area_details)
        return JsonResponse(ingested_area_details)


def get_platforms(models, field='metadata'):
    """
    Get all platforms in DatasetType model
    return:
         List
         list of all unique platforms
    """
    metadata_result = models.DatasetType.objects.using('agdc')
    platforms = set()
    for i in range(len(metadata_result)):
        platforms.add(metadata_result[i].get_platform())
    return list(platforms)


def get_dataset_by_platform(models, platform_filter, platform):
    dataset_follow_by_platform = models.Dataset.objects.using('agdc').filter(**{platform_filter: platform})
    dataset_result = []
    for i in range(len(dataset_follow_by_platform)):
        filtered_platform_result = dataset_follow_by_platform[i].get_dataset_table_columns()
        serial_data = get_serialized_data(filtered_platform_result)
        serial_data['dataset_type_ref'] = dataset_follow_by_platform[i].dataset_type_ref.pk 
        dataset_result.append(serial_data)
    return dataset_result

def get_serialized_data(data):
    left, top = data[4].split(', ')
    right, bot = data[5].split(', ')
    return {
        'dataset_type_ref': 'dataset_type_ref_dung',
        'product': data[0],
        'start_date': data[6],
        'end_date': data[6],
        'latitude_min': float(bot),
        'latitude_max': float(top),
        'longitude_min': float(left),
        'longitude_max': float(right),
        'pixel_count': 1,
        'scene_count': 1
    }