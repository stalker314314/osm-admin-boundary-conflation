# OSM administrative boundary conflation

This repo contains set of predefined pipelines, data formats and tools that aid conflation of
administrative boundaries in OpenStreetMap (OSM). If you get your hands on authoritative dataset ("external truth")
which contains geometries of admin boundaries, this repo can help you to import this data in an easy and semi-automated
way.

Conflation is hard and labor-intensive process if you want to do it properly. When conflating boundaries, you need to
take great care not to accidentally move national boundary, or move other glued ways like highways, or move tagged nodes,
like traffic lights. And you can have other relations glued together with administrative boundaries. It can get messy
and error-prone very fast. This repo helps with all of that and on high-level it will enable you to:

* measure quality of your boundaries (authoritative data vs OSM data)
* keep quality of OSM boundaries in daily, continuous fashion
* prepare data so you can do manual conflation using tools like JOSM
* check conflation potential (what can be semi-automatically conflated, what not and most importantly - why not)
* do ungluing and conflate boundary ways in semi-automatic ways (present to user each way to be conflated and result of
conflation and ask user to proceed)

## Install

This repo is tested exclusively in Linux and is recommended way to use it. On Windows, your best bet is Conda.
Here are brief instructions for Debian:
```
sudo apt install proj-bin libproj-dev curl gdal-bin git
python -m pip install -r requirements.txt 
```

Also, you will need to install Docker if you plan to use local Overpass instance (which is highly encouraged). If you do
use Docker, do note that all scripts here assume that Docker could be ran without root, so try to set up Docker to be
rootless.

During running of some tools, scripts will try to clone ogr2osm repo (it is dependency, but there are no automated way
to pull this, so I added `git clone` directly in script to make your life easier).

## Pipeline

```
      Input data
          |
          v
+--------------------+
|                    |
|     Your script    |
|    to convert to   |
|     input .csv     |
|                    |
+----------+---------+
           | .csv
           |
           +-------------------------+
           |                         |
           v                         v
+--------------------+    +--------------------+
|                    |    |                    |
|                    |    |                    |
|  inputcsv2shp.py   |    | measure_quality.py |
|                    |    |                    |
|                    |    |                    |
+---------+----------+    +--------------------+
          |  .shp
          v
+--------------------+
|                    |
|                    |
|     shp2osm.py     |
|                    |
|                    |
+---------+----------+
          | .osm
          v
+--------------------+
|                    |
|                    |  conflate-progress.pickle
|    conflate.py     +---------------+
|                    |               |
|                    |               v
+---------+----------+    +-------------------+
          |               |                   |
          |Changesets     |                   |
          v               | conflate-stats.py |
       +-----+            |                   |
       |     |            |                   |
       | OSM |            +---------+---------+
       |     |                      |
       +-----+                      |.html
                                    v
```

## Usage

### Adjust config

Root directory of this repo contains file `config.yml`. It contains most important configuration that you need to closely
go over and adopt to your use case. All fields should be self-explanatory, but if you are not sure about some, or need
more extensibility than what is there, let me know!

### Convert input data to .CSV
This repo contains several tools to make sense of admin boundary conflation. First thing is to convert your input dataset
to something that pipeline down the road can understand. This is simple CSV file which contains following columns:
* `level9_id`: string
* `wkt`: WKT geometry of your level 9 entity (in WSG84)

Everything else is optional:

* `level9_name`: string
* `level8_id`: string
* `level8_name`: string
* `level7_id`: string
* `level7_name`: string
* `level6_id`: string
* `level6_name`: string

As you can see, format is as simple as it can be. How to create it from your dataset is out of scope of this document,
but you can use Python (look at implementation for Serbia located at `serbia/serbia2input.py`) or even QGIS. If you need
help, feel free to ping me with your dataset or open issue on Github!

If you don't have level9 entities (settlements, neightbours), but something else (level 8, level 10...), script should
work in theory, but it needs adjustments here and there. Let me know if this is blocker for you, so we can implement
your use case too.

### Measure quality

Once you have data in expected .csv format, you can run: `python ./measure_quality.py <input_csv_file> <output_csv_file>`
and it will go over all entities and, for each admin entity, it will output IoU (intersection over union) as a standard
measurement of how good authoritative dataset fit OSM data. It works by matching `ref` from your dataset to OSM or
`name` tag, so if you don't have matching `ref` or `name` tags in OSM, it cannot match them. If you want easy way to add
`ref` tags to OSM, check section "Extra scripts".

This script can measure around 1000-2000 entities per day if you use public Overpass instances. If you use local
Overpass instance, it will work in parallel and can process 100000 entities per day (roughly 100x faster)!

If you don't plan to do conflation of your data, this measurement script is all you need. Check section "Daily
measurement" to understand how you can do continuous checks for quality of your administrative boundaries.

### Produce .osm file for conflation

Conflation is slow and semi-manual process. Before you can proceed, you need to convert input .csv format to .osm format
with which tooling works. This is needed only once and it is automatic process using two scripts:
```
python inputcsv2shp.py <input_csv_file> <intermediate_shp_file>
./shp2osm.sh <intermediate_shp_file> <output_osm_file>
```

You can open and inspect obtained .osm file in JOSM editor and check it. It should have separate ways for each segment
of administrative boundary. Goal of conflation is now to find and conflate each of these segments to OSM. If you don't
want to use conflate script, you can still use obtained .osm file to do it manually (see section "Manual conflation
with .osm file").

### Manual conflation with .osm file

**BIG FAT DISCLAIMER**: Please don't import data or change boundaries without fully conforming with
[OSM import guidelines](https://wiki.openstreetmap.org/wiki/Import/Guidelines) *and* also consulting with both local
community and neighboring countries' communities (if you plan to change national boundaries!).

* Install JOSM, and install plugin [UtilsPlugin2](https://josm.openstreetmap.de/wiki/Help/Plugin/UtilsPlugin2) which we
will need during process of conflation
* If .osm files are big, increase memory provided to JOSM. It boils down to add parameters `-J-d64 -J-Xmx2048m`, but
check [here](https://josm.openstreetmap.de/wiki/Download#VMselectiononWindowsx64) for more details.
* Open obtained .osm file in JOSM as new layer.
* Go to "File"->"Download data" (Ctr+Shift+Down) and go to tab "Download from Overpass API" and input this[1] as a
query. It is not important what you select in the map below. Click "Download as new layer". It is wise to uncheck "Zoom
to downloaded data", so you don't zoom back to whole country. After download, you should get new layer "Data Layer 1".

Now that you set it all up, here is cyclic workflow:
* Select "Data layer 1" layer and zoom to level9 entities that you want to fix. Focus on a particular way you want to
fix.
* Copy authoritative way to OSM layer. To do this, first select .osm layer, then select one or more ways. Copy it
(Ctrl+C). Go back to "Data layer 1" and paste it at same position using  "Edit"->"Paste at source position" (Ctrl+Alt+V).
Never do Ctrl+V!
* Now select both old and new way, holding Ctrl. With both ways selected, choose "More Tools" -> "Replace Geometry"
(Ctrl+Shift+G)
* New dialog for solving conflicts will show up. You should "Keep" most tags, but you should "delete" "level9_id" tag.
Sometimes, if you change boundary with lower "admin_level" (for example "admin_level=7"), you can have conflict for that
tag too, but always choose lower number. Click "Apply".
* You just conflated way from old (OSM) geometry to new (authoritative) geometry and all points are added/modified. From
two ways, we got one. What is not fixed are end nodes. They are now detached from OSM boundaries and need to be
reattached. To do that, move them to existing OSM way holding Ctrl to glue them. All boundaries always should form
closed shape.
* Congratulation, you just conflated your first way:)

[1]
```
[out:xml];
area["name"="<your_country>"]["admin_level"=2]->.a;
(
	relation(area.a)["boundary"]["admin_level"];
);
(._;>;);
out;
```

### Assess and report conflating potential

If you just want to see what is possible to be automatically, set `config.yml` like this:
```
dry_run: True
auto_proceed: True
```

and run it like `python <input_osm_file> <progress_file>`. This will check each way and save intermediate results to
`progress_file`. If you provide same progress file again, it will continue where it left of. If you want to start from
scratch, provide new file or delete existing one.

This file can be used later to generate report of possible conflation, and if it is not possible - it will explain why
it is not possible (there are lot of various reasons, all explained in report). To generate report, execute:
```
python conflate-report.py <progress_file> <output_html_file>
```

When you open <output_html_file> in your browser, you can check individual problems and solve them independently.

### Semi-automatic conflation

Once you assessed conflating potential, you might want to conflate those ways which are possible to be conflated. For
that, set `config.yml` to:
```
dry_run: False
auto_proceed: False
```

You will need to create file named `osm-password` in root folder and fill it with one line that has
`<osm_username>:<osm_password>` in it. This is needed to authenticate with OSM. Once you run conflation with
`python <input_osm_file> <progress_file>`, you will be asked for those ways that can be conflated, new dialog will be
shown with what geometry will be changed and you need to click "Y" for each way. It is wise to check what actual changes
in OSM has been done, to be sure this script is not going crazy!

### Extra scripts

There are couple of useful scripts in `extras/` folder which might come handy to you. They all require to create file
named `osm-password` in root folder and fill it with one line that has `<osm_username>:<osm_password>` in it. They are:

* `add_level9_id_to_osm.py`: use it to mass add "ref" tag to OSM to all your level 9 entities, based on their name
* `add_level8_id_to_osm.py`: use it to mass add "ref" tag to OSM to all your level 8 entities, based on their name
* `add_subare_settlements.py`: use it to mass add level 9 relations to level 8 relations as a "subarea" members

### Continuous quality checks

If you can measure quality of your level 9 entities, it should be easy to run that scripts in two consecutive days and
do the difference on their outputs. This is what we did for Serbia and you can check `serbia/daily-measurement.sh` for
details. Basically, we refresh cadastre data and OSM data for day before, then update data for today and do difference
of their results and report if any level 9 entity is worse than it was day before. This way, we get continuous checks.

If you need something similar, but you are not sure how to do it, let me know and I will try to help you!
