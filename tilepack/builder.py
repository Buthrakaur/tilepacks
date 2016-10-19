from tilepack.util import point_to_tile
import tilepack.outputter
import requests
import zipfile
import argparse
import os
import multiprocessing
import time
import random

def cover_bbox(min_lon, min_lat, max_lon, max_lat, zoom):
    min_x, max_y, _ = point_to_tile(min_lon, min_lat, zoom)
    max_x, min_y, _ = point_to_tile(max_lon, max_lat, zoom)

    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            yield (x, y, zoom)

# def fetch_tile(x, y, z, layer, format, api_key):
def fetch_tile(format_args):
    sleep_time = 0.5
    while True:
        url = 'https://tile.mapzen.com/mapzen/vector/v1/{layer}/{zoom}/{x}/{y}.{fmt}?api_key={api_key}'.format(**format_args)
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            return (format_args, resp.content)
        except requests.exceptions.RequestException as e:
            if isinstance(e, requests.exceptions.HTTPError):
                print("HTTP error {} -- {} while retrieving {}, retrying after {} sec".format(e.response.status_code, e.response.text, url, sleep_time))
            else:
                print("{} while retrieving {}, retrying after {} sec".format(type(e), url, sleep_time))
            time.sleep(sleep_time)
            sleep_time = min(sleep_time * 2.0, 30.0) * random.uniform(1.0, 1.7)

output_type_mapping = {
    'mbtiles': tilepack.outputter.MbtilesOutput,
    'zipfile': tilepack.outputter.ZipfileOutput,
}

def build_tile_packages(min_lon, min_lat, max_lon, max_lat, min_zoom, max_zoom,
        layer, tile_format, output, output_formats, api_key):

    fetches = []
    for zoom in range(min_zoom, max_zoom + 1):
        for x, y, z in cover_bbox(min_lon, min_lat, max_lon, max_lat, zoom=zoom):
            fetches.append(dict(x=x, y=y, zoom=z, layer=layer, fmt=tile_format, api_key=api_key))

    tiles_to_get = len(fetches)

    tile_ouputters = []
    for t in set(output_formats):
        builder_class = output_type_mapping.get(t)

        if not builder_class:
            raise KeyError("Unknown output format {}".format(t))

        tile_ouputters.append(builder_class.build_from_basename(output))

    try:
        p = multiprocessing.Pool(multiprocessing.cpu_count() * 10)

        for t in tile_ouputters:
            t.open()
            t.add_metadata('name', output)
            # FIXME: Need to include the `json` key
            t.add_metadata('format', 'application/vnd.mapbox-vector-tile')
            t.add_metadata('bounds', ','.join(map(str, [min_lon, min_lat, max_lon, max_lat])))
            t.add_metadata('minzoom', min_zoom)
            t.add_metadata('maxzoom', max_zoom)

        for i, (format_args, data) in enumerate(p.imap_unordered(fetch_tile, fetches)):
            for t in tile_ouputters:
                t.add_tile(format_args, data)
    finally:
        p.close()
        p.join()
        for t in tile_ouputters:
            t.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('min_lon',
        type=float,
        help='Bounding box minimum longitude/left')
    parser.add_argument('min_lat',
        type=float,
        help='Bounding box minimum latitude/bottom')
    parser.add_argument('max_lon',
        type=float,
        help='Bounding box maximum longitude/right')
    parser.add_argument('max_lat',
        type=float,
        help='Bounding box maximum latitude/top')
    parser.add_argument('min_zoom',
        type=int,
        help='The minimum zoom level to include')
    parser.add_argument('max_zoom',
        type=int,
        help='The maximum zoom level to include')
    parser.add_argument('output',
        help='The filename for the output tile package')
    parser.add_argument('--layer',
        default='all',
        help='The Mapzen Vector Tile layer to request')
    parser.add_argument('--tile-format',
        default='mvt',
        help='The Mapzen Vector Tile format to request')
    parser.add_argument('--output-formats',
        default='mbtiles,zipfile',
        help='A comma-separated list of output formats to write to')
    args = parser.parse_args()

    api_key = os.environ.get('MAPZEN_API_KEY')

    output_formats = args.output_formats.split(',')
    build_tile_packages(
        args.min_lon,
        args.min_lat,
        args.max_lon,
        args.max_lat,
        args.min_zoom,
        args.max_zoom,
        args.layer,
        args.tile_format,
        args.output,
        output_formats,
        api_key,
    )

if __name__ == '__main__':
    main()
