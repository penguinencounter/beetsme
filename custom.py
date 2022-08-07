import shutil
import subprocess
import json
import os
from beet import Context
from pprint import pprint
from requests import get
import time


MCGEN = "python -m mcgen --version release --log FATAL --processors mcgen.processors.split_registries"
PISTON_VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def generate(_):
    print('>> Building data')
    print('> Checking ratelimit data', flush=True)
    cache_file_loc = os.path.join('temp', 'caching.json')
    if os.path.exists(cache_file_loc):
        with open(cache_file_loc) as f:
            extracted = json.load(f)
    else:
        extracted = {}
    if 'time' in extracted.keys():
        if time.time() - extracted['time'] < 3600:
            print('> Caching data is fresh (1hr), done')
            return
    print('> Downloading version information', flush=True)
    r = get(PISTON_VERSION_MANIFEST)
    # extract JSON
    data = r.json()
    print('> Checking version cache data', flush=True)
    if 'version' in extracted.keys():
        if extracted['version'] == data['latest']['release']:
            print('> Data is up to date', flush=True)
            print('>> Finished', flush=True)
            return
    print('> Data is out of date, running mcgen', flush=True)
    clean1 = os.path.join('temp', 'out')
    clean2 = os.path.join('temp', 'raw')
    clean3 = os.path.join('temp', 'registries')
    print('* Cleaning 1/3', flush=True)
    if os.path.exists(clean1):
        shutil.rmtree(clean1)
    print('* Cleaning 2/3', flush=True)
    if os.path.exists(clean2):
        shutil.rmtree(clean2)
    print('* Cleaning 3/3', flush=True)
    if os.path.exists(clean3):
        shutil.rmtree(clean3)
    print('* Running...', flush=True)
    subprocess.call(MCGEN)

    print('>> Exporting data to discoverable folder', flush=True)

    # copy temp/out/(version)/reports/registries to temp/registries
    out_registries = os.path.join('temp', 'out', data['latest']['release'], 'reports', 'registries')
    if os.path.exists(out_registries):
        shutil.copytree(out_registries, os.path.join('temp', 'registries'))
    else:
        print('> No registries found or program is borked', flush=True)

    print('>> Cleanup', flush=True)

    # cleanup temp
    targets = map(lambda x: os.path.join('temp', x), ['jars', 'out', 'raw'])
    for target in targets:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)

    print('> Writing cache', flush=True)
    with open(cache_file_loc, 'w') as f:
        json.dump({'version': data['latest']['release'], 'time': time.time()}, f)
    print('>> Finished generating regdump', flush=True)


def gen_use(ctx: Context):
    ns = ctx.data['territories_generated']
    print('>> Generating use data')
    print('> Accessing generator data', flush=True)
    all_blocks = os.path.join('temp', 'registries', 'block', 'data.json')
    all_items = os.path.join('temp', 'registries', 'item', 'data.json')
    with open(all_blocks) as f:
        blocks = json.load(f)['values']
    with open(all_items) as f:
        items = json.load(f)['values']
    print('> Generating use data', flush=True)
    # Generate a list of all ids that are in both blocks and items
    shared = []
    for block in blocks:
        if block in items:
            shared.append(block)
    pprint(shared)

