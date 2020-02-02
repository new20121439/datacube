﻿# Open Data Cube Core Install

This document will guide users through the process of installing and configuring Open Data Cube. 
The ODC must be installed prior to installing additional components such as the web-based UI.

Contents
=================

  * [System Requirements](#system_requirements)
  * [Updates](#updates)
  * [Directory Creation](#directory_creation)
  * [Virtual Environment Setup](#venv_setup)
  * [GDAL Libraries](#gdal_libs)
  * [Python Dependencies](#python_deps)
  * [Core](#core)
  * [PostgreSQL Database](#postgres)
  * [Confirm Installation](#confirm_install)
  * [Next Steps](#next_steps)
  * [Common problems/FAQs](#faqs)

<a name="system_requirements"></a> System Requirements
=================
This document assumes that a local user, not an admin user, will be used to run all of the processes.  We use `localuser` as the user name, but it can be anything you want.  We recommend the use of `localuser`, however, as a considerable number of our configuration files assume the use of this name.  To use a different name may require the modification of several additional configuration files that otherwise would not need modification. Do not use special characters such as <b>è</b>, <b>Ä</b>, or <b>î</b> in this username as it can potentially cause issues in the future. We recommend an all-lowercase underscore-separated string.

This document is targeted at an Ubuntu development environment. The base requirements can be found below:

* **OS**: Ubuntu 18.04 LTS - [Download here](https://www.ubuntu.com/download/server)
* **Memory**: 8GiB
* **Local Storage**: 50GiB
* **Python Version**: Python 3

Before we begin, note that multiple commands should not be copied and pasted to be run simultaneously unless you know 
it is acceptable in a given command block. Run each line individually.

<!--* **Create your base directory structure to hold all of the relevant codebases**: We create everything in a directory 'Datacube' in the local user's directory. We also create a base directory structure for raw data and the ingested data in the root directory '/datacube/\*'-->
<!--* **Create a virtual environment named 'datacube_env' in the ~/Datacube directory**: We use a single virtual environment for all of our Data Cube related packages/modules. To set this up, you must install virtualenv for Python3 and initialize the environment.-->

<a name="updates"></a> Updates
=================
Before starting the installation of packages, it is a good idea to update the software that will be retrieving those packages as well as the locations from which they will be retrieved.  The lines below will upgrade `apt-get` then install `Python3`, `npm`, `pip3`, and `git`. The other packages, `tmux` and `htop`, are useful tools for performance monitoring but are not required.  Then finally we attempt to upgrade `pip3`, just in case the version is not as new as it could be.

```
sudo apt-get update
sudo apt-get install tmux htop python3-dev python3-pip git
sudo pip3 install --upgrade pip
```

<a name="directory_creation"></a> Directory Creation
=================
The following commands will create the directories the Data Cube will require and set their permissions so that all users can read and write data to and from them.

```
sudo mkdir -p /datacube/{original_data,ingested_data}
sudo chmod -R 777 /datacube/

mkdir -p ~/Datacube
```

<a name="venv_setup"></a> Virtual Environment Setup
=================
Next, we need to install the virtual environment and source it before we start pip installing packages.  This is a way to compartmentalize the python packages and keep your operating environment unaffected by changes to Python made from within the virtual environment.

```
sudo pip3 install virtualenv 
virtualenv ~/Datacube/datacube_env
source ~/Datacube/datacube_env/bin/activate
```

<a name="gdal_libs"></a> GDAL Libraries
=================
Install GDAL's header libraries and other important libraries that the Data Cube will rely on. 

The first two commands account for the GDAL version used by datacube-core being 2.4.0, 
which, at the time of writing, is not available on the default repositories used by `apt-get`.
Note that you will need to press the Enter key after initiating the first command
to actually add the required repository.

```
sudo add-apt-repository ppa:ubuntugis/ubuntugis-unstable
```
```
sudo apt-get update
sudo apt-get install gdal-bin libgdal-dev libnetcdf-dev netcdf-bin libhdf5-serial-dev hdf5-tools
```

The version of the GDAL libraries can be determined with the command `gdalinfo --version`.  
Make sure it matches your GDAL Python bindings package or you will receive 
an error related to `x86_64-linux-gnu-gcc`. 
The next step will require a compatible installation of gdal.

```
gdalinfo --version
```

Run the following command where the version (e.g. `2.4.2`) is the version 
from the previous step, or as close to it as possible.
For instance, if 2.4.2 was shown by `gdalinfo --version`, but unable to install
in this command, try 2.4.1, and so on:

```
pip install --global-option=build_ext --global-option="-I/usr/include/gdal" gdal==2.4.2
```

<a name="python_deps"></a> Python Dependencies
=================
Use the following commands to install the requisite Python dependencies. 
These packages are required for using the Data Cube, S3 indexing, and the Data Cube notebooks.
Version `1.2.18` of SQLAlchemy is used to avoid an error in `datacube -v system init` when using
the default, more recent versions of SQLAlchemy (at least version `1.3.0b3`).
```
pip install rasterio==1.0.24
pip install numpy xarray
pip install shapely scipy cloudpickle Cython netcdf4==1.3.1 boto3 folium hdmedians scikit-image ruamel.yaml
pip install sqlalchemy==1.3.1
pip install psycopg2-binary
```

<a name="core"></a> Core
=================
Install the latest version of the Open Data Cube core from the [Open Data Cube Core github](https://github.com/opendatacube/datacube-core/releases).  It is critical that you select a version of `1.6.1` or later if you intend to use S3 indexing.  Afterwards, run the python setup development wheel.
```
cd ~/Datacube
git clone https://github.com/opendatacube/datacube-core.git --branch datacube-1.7
cd ~/Datacube/datacube-core
python setup.py develop
```

<a name="postgres"></a> PostgreSQL Database
=================
Install <b>PostgreSQL</b> database that will store the metadata that will point to the data location.  Also install prerequisite libraries that will be leveraged by the Data Cube.  

```
sudo apt-get install postgresql-10 postgresql-client-10 postgresql-contrib-10 libhdf5-serial-dev postgresql-doc-10
```

In the configuration file `/etc/postgresql/10/main/postgresql.conf`, change the `timezone` parameter to `UTC`. This parameter should be in a section titled `Locale and Formatting`. 

In the configuration file `/etc/postgresql/10/main/pg_hba.conf`, 
change the `local` line to match the example below. 
It is one of the last lines in the configuration file.  
The spacing matters as well so take care to preserve it.  
Below is a more detailed example of both configuration files.

**pg_hba.conf**
```
local   all             postgres                                peer
# TYPE  DATABASE        USER            ADDRESS                 METHOD
# "local" is for Unix domain socket connections only
local   all             all                                     md5
# IPv4 local connections:
host    all             all             127.0.0.1/32            md5
# IPv6 local connections:
host    all             all             ::1/128                 md5
```

Now that the <b>PostgreSQL</b> settings have been modified, restart the service:

```
sudo service postgresql restart
```

Create a <b>PostgreSQL</b> superuser to access the database. 
We usually use a password of `localuser1234`, but you can use 
whatever password you like, as long as you record and remember it. 
```
sudo -u postgres createuser --superuser dc_user
sudo -u postgres psql -c "ALTER USER dc_user WITH PASSWORD 'localuser1234';"
createdb -U dc_user datacube
```

Next, create the Data Cube configuration file to be read when initializing the Data Cube.  
Create a file at `~/.datacube.conf`.  The hostname should be set to either `localhost` or `127.0.0.1`.  
If you are attempting to access a Data Cube installed on a server, you will use the IP address 
of that server followed by the port number in order to connect.  
Example: `192.168.1.5:8080` where `192.168.1.5` is the server IP and `8080` is the port number. 
It is critical that the password matches the password specified when 
the <b>PostgreSQL</b> database superuser was created. 
If it does not, the Data Cube will have an authorization failure. 
An example configuration file is shown below.
```
[datacube]
db_hostname: 127.0.0.1
db_database: datacube
db_username: dc_user
db_password: localuser1234
```

Finally, initialize the database.  If this step fails, you must go over 
the previous steps and ensure that you have correctly set up all configuration 
files, the <b>PostgreSQL</b> database, as well as the <b>PostgreSQL</b> 
database superuser and password.
```
datacube -v system init
```

<a name="confirm_install"></a> Confirm Installation
=================
Run `datacube system check` to validate the installation.
The output should look something like this:
```
Version:       1.7
Config files:  /home/localuser/.datacube.conf
Host:          127.0.0.1:5432
Database:      datacube
User:          dc_user
Environment:   None
Index Driver:  default

Valid connection:       YES
```
If you receive an error on this step then please ensure you have followed the previous steps and that there were no errors received during their execution.

<a name="next_steps"></a> Next Steps
========  
Now that we have ODC core setup, you may install our web-based UI or a Jupyter Notebook server with some example ODC notebooks.
The Jupyter Notebook server installation documentation can be found [here](./notebook_install.md).
The web-based UI installation documentation can be found [here](./ui_install.md).

<a name="faqs"></a> Common problems/FAQs
========  
----  

Q: 	
 >I’m getting a “Permission denied error.”  How do I fix this?  

A:  
>	More often than not the issue is caused by a lack of permissions on the folder where the application is located.  Grant full access to the folder and its sub folders and files (this can be done by using the command `chmod -R 777 FOLDER_NAME`).  

---  

Q: 	
 >I'm getting a database error that resembles "fe_sendauth: no password supplied". How do I fix this?

A:  
>	This occurs when the Data Cube system cannot locate a `.datacube.conf` file and one is not provided as a command line parameter. Ensure that a `.datacube.conf` file is found in your local user's home directory - `~/.datacube.conf`

---  

Q: 	
 >I'm getting an error that resembles "FATAL: Peer authentication failed for user". How do I fix this?

A:  
>	This occurrs when <b>PostgreSQL</b> is incorrectly configured. Open your `pg_hba.conf` file and check that the local connection authenticates using the `md5` method. If you are trying to connect to a remote database (e.g. using PGAdmin3 from a host machine when the Data Cube is on a guest VM) then a new entry will be required to allow non local connections. More details can be found on the [PostgreSQL documentation](https://www.postgresql.org/docs/9.5/static/auth-pg-hba-conf.html).

---  

Q: 	
 >Can the Data Cube be accessed from R/C++/IDL/etc.?

A:  
>This is not currently directly supported, the Data Cube is a Python based API. The base technology managing data access <b>PostgreSQL</b>, so theoretically the functionality can be ported to any language that can interact with the database. An additional option is just shelling out from those languages, accessing data using the Python API, then passing the result back to the other program/language.

---  

Q: 	
 >Does the Data Cube support *xyz* projection?

A:  
>Yes, the Data Cube either does support or can support with minimal changes any projection that `rasterio` can read or write to.

---  

Q: 	
 >I want to store more metadata that isn't mentioned in the documentation. Is this possible?

A:  
>This entire process is able to be completely customized. Users can configure exactly what metadata they want to capture for each dataset - we use the default for simplicity's sake.

---  

Q: 	
>Does ingestion handle pre-processing or does data need to be processed before ingestion?

A:  
>The ingestion process is simply a reprojection and resampling process for existing data. Data should be pre-processed before ingestion.

---

Q: 	
>I'm receiving an error stating: `ERROR 4: Unable to open EPSG support file gcs.csv. Try setting the GDAL_DATA environment variable to point to the directory containing EPSG csv files.` what do I do to fix this?


A:  
>You must set the `GDAL_DATA` environment variable to the absolute path of the directory containing the file called `gcs.csv`.  If you are unable to locate it, a simple find command like: `find / -name "gcs.csv"` can find it for you.  However, if you followed the steps above, it should be located in: `~/Datacube/datacube_env/lib/python3.5/site-packages/rasterio/gdal_data/gcs.csv`.  
>
>You can set the environment variable for the current session using:
>`export GDAL_DATA="path/to/directory"` 
>
>To set it permanently for all future sessions add the line above to your `.bashrc` file in your `$HOME` directory.
>

---

