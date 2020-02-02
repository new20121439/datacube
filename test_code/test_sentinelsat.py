from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt
import datetime
from geojson import Polygon
from imageio import imread

class sentinel_query_task:
    user = 'tranvandung20121439'
    password = 'dung20121439'
    api_url = 'https://scihub.copernicus.eu/dhus'
    api = SentinelAPI(user, password, api_url)

    parameters = {
        'latitude': (11.5554, 11.7195),
        'longitude': (107.0446, 107.2362),
        'time': (datetime.date(2018, 4, 14), datetime.date(2019, 4, 15))
    }

    @property
    def query(self):
        def order_by(order_by='ingestiondate', ascending=False):
            prefix_order_by = '+' if ascending else '-'
            order_by = prefix_order_by + order_by
            return order_by

        longitude_min, longitude_max = self.parameters['longitude']
        latitude_min, latitude_max = self.parameters['latitude']
        # extent = Polygon([[(latitude_min, longitude_min),
        #                    (latitude_max, longitude_min),
        #                    (latitude_max, longitude_max),
        #                    (latitude_min, longitude_max),
        #                    (latitude_min, longitude_min)]])
        extent = Polygon([[(longitude_min, latitude_min),
                (longitude_max, latitude_min),
                (longitude_max, latitude_max),
                (longitude_min, latitude_max),
                (longitude_min, latitude_min)]])
        order_by = order_by('ingestiondate', ascending=False)
        extent = geojson_to_wkt(extent)
        products = self.api.query(extent,
                             date=(self.parameters['time']),
                             area_relation='Intersects',
                             cloudcoverpercentage=(0, 10),
                             platformname='Sentinel-2',
                            order_by=order_by
                                ) #producttype='S2MSI2A'
        self.products = products
        products_df = self.api.to_dataframe(products)
        if products_df.empty:
            raise Exception("No products were found")
        self.products_df = products_df
        return self.products_df

    def validate_name(self, string: str):
        return string.replace('_', '-')

    def download(self, idx=0, directory_folder=r'/home/dung/datacube/original_data/sentinel_2/'):
        id = self.products_df['uuid'].iloc[0:3]
        print(id)
        # self.api.download(id=id, directory_path=directory_folder)

    def show_thumnail(self, idx=0):
        link_icon = self.products_df['link_icon'].iloc[0:3]
        [imread(link_incon__) for link_incon__ in link_icon  ]


result_df =  sentinel_query_task()
products_df = result_df.query
# print(products_df['ingestiondate'])
print(result_df.products_df.columns)
# result_df.download()
# result_df.show_thumnail(idx=0)
