from utils.data_cube_utilities import data_access_api
dc = data_access_api.DataAccessApi()
a = dc.get_datacube_metadata('sentinel_2_l2a', 'SENTINEL_2')
print(a)
