from collections import defaultdict
from pprint import pprint
import shutil
import subprocess
import json
import os
from beet import Context, Function, FunctionTag, TextFile, JsonFile
from requests import get
import time

VERSION_SPECIFIC = True
VERSION_TARGET = '1.19'
PACK_FORMAT = 10
MCGEN = f"python -m mcgen --version {VERSION_TARGET} --log FATAL --processors mcgen.processors.split_registries"
PISTON_VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


GENERATED_HEADER = "# THIS FILE IS GENERATED. DO NOT EDIT UNLESS YOU KNOW WHAT YOU ARE DOING! :)\n\n"


def setup_pack(ctx: Context):
    ctx.data.pack_format = PACK_FORMAT


def generate(_):
    print('\n>> Building data')
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
    version = VERSION_TARGET if VERSION_SPECIFIC else data['latest']['release']
    print('> Checking version cache data', flush=True)
    if 'version' in extracted.keys():
        if extracted['version'] == version:
            print('> Data is up to date', flush=True)
            with open(cache_file_loc, 'w') as f:
                extracted['time'] = time.time()
                json.dump(extracted, f)
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
    out_registries = os.path.join('temp', 'out', version, 'reports', 'registries')
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
        json.dump({'version': version, 'time': time.time()}, f)
    print('>> Finished generating regdump', flush=True)


mappings = {}
def generate_unified_mappings(ctx: Context):
    all_blocks = os.path.join('temp', 'registries', 'block', 'data.json')
    all_items = os.path.join('temp', 'registries', 'item', 'data.json')
    break_fmt = 'minecraft.mined:{}'
    place_fmt = 'minecraft.used:{}'
    with open(all_blocks) as f:
        blocks = json.load(f)['values']
    with open(all_items) as f:
        items = json.load(f)['values']
    both = [k for k in blocks if k in items]
    additional = [k for k in blocks if k not in items]

    index = {}

    i = 0
    for k in both:
        mappings[i] = {
            'break': break_fmt.format(k.replace(':', '.')),
            'place': place_fmt.format(k.replace(':', '.'))
        }
        index[i] = {"id": k, "used_with": ['break', 'place']}
        i += 1
    for k in additional:
        mappings[i] = {
            'break': break_fmt.format(k.replace(':', '.'))
        }
        index[i] = {"id": k, "used_with": ['break']}
        i += 1
    print('> Mappings:', flush=True)
    print('generated {} total'.format(len(mappings)), flush=True)
    hist = defaultdict(int)
    for d in mappings.values():
        hist[len(d)] += 1
    for k, v in hist.items():
        print('          {} with {} item(s)'.format(v, k), flush=True)
    print('> writing', flush=True)
    ctx.data.extra['mappings/unified.json'] = JsonFile(index)

merged_tags = defaultdict(list)


def generate_scoreboard_hooks(ctx: Context):
    """
    Generates hooks.
    """
    sbns = 'terr.'
    ns = ctx.data['territories_generated']

    print('>> Generating scoreboard hooks', flush=True)
    print('> Generating tasks', flush=True)
    todo = defaultdict(list)
    for k, v in mappings.items():
        for k2, v2 in v.items():
            todo[k2].append(k)
            print('\r', end='', flush=True)
            print(f'{k2} -> ({k}) {v2}'.ljust(100), end='', flush=True)
    print('\n> Running tasks', flush=True)

    for taskName, todoItems in todo.items():
        outputs = {
            "init": GENERATED_HEADER,
            "test": GENERATED_HEADER,
            "uninstall": GENERATED_HEADER
        }
        print(f'> generating: {taskName} ({len(todoItems)} items)', flush=True)
        for item in todoItems:
            retrievedData = mappings[item][taskName]
            objName = f'{sbns}{taskName}.{item}'
            outputs['init'] += f'scoreboard objectives add {objName} {retrievedData}\n'
            outputs['test'] += 'execute as @a[scores={'+objName+'=1..}] run function #territories:on_'+taskName+'\n'
            outputs['test'] += 'execute as @a[scores={'+objName+'=1..}] run scoreboard players set @s '+objName+' 0\n'
            outputs['uninstall'] += f'scoreboard objectives remove {objName}\n'
            print(f'\r', end='', flush=True)
            print(f'generate: {taskName} > {retrievedData}'.ljust(100), end='', flush=True)
        print()
        print(f'> writing: {taskName} ({len(todoItems)} items)', flush=True)
        for k, v in outputs.items():
            print(f'out: {k} | {len(v)} bytes', flush=True)
            ns[f'{taskName}_hook/{k}'] = Function(v)
    return
    initOutput = GENERATED_HEADER
    checkOutput = GENERATED_HEADER
    uninstallOutput = GENERATED_HEADER
    mappingOut = "Block placing mapping:\n\n"
    for sbn, name in shared.items():
        initOutput += f'scoreboard objectives add {sbns}{name} {sbn}\n'
        checkOutput += 'execute as @a[scores={'+sbns+name+'=1..}] run function #territories:on_place\n'
        checkOutput += 'execute as @a[scores={'+sbns+name+'=1..}] run scoreboard players set @s '+sbns+name+' 0\n'
        uninstallOutput += f'scoreboard objectives remove {sbns}{name}\n'
        mappingOut += f'{sbns}{name} -> {sbn}\n'


    ctx.data.extra['mappings/on_place.txt'] = TextFile(mappingOut)
    
    print('== STATISTICS ==')
    print(f'Total blocks registered: {len(shared)}')
    print(f'Init  : {len(initOutput)} char, {len(initOutput.splitlines())} lines')
    print(f'Hook  : {len(checkOutput)} char, {len(checkOutput.splitlines())} lines')
    print(f'Uninst: {len(uninstallOutput)} char, {len(uninstallOutput.splitlines())} lines')
    print('================')

    # add to datapack
    ns["block_place_hook/init"] = Function(initOutput)
    ns["block_place_hook/check"] = Function(checkOutput)
    ns["block_place_hook/uninstall"] = Function(uninstallOutput)

    # tag
    merged_tags["minecraft:load"].append('territories_generated:block_place_hook/init')
    merged_tags["territories:update_expensive"].append('territories_generated:block_place_hook/check')


def gen_break_block(ctx: Context):
    """
    Generates block breaking hooks.
    """
    sbns = 'terr.'
    ns = ctx.data['territories_generated']

    print('\n>> Generating break data')
    print('> Accessing generator data', flush=True)
    all_blocks = os.path.join('temp', 'registries', 'block', 'data.json')
    with open(all_blocks) as f:
        blocks = json.load(f)['values']
    print('> Generating break data', flush=True)
    # Generate a list of all ids that are in both blocks and items
    shared = {}
    fmt = 'minecraft.mined:{}'
    i = 0
    for block in blocks:
        name = f'mine.{i}'
        shared[fmt.format(block.replace(':', '.'))] = name
        i += 1
    initOutput = GENERATED_HEADER
    checkOutput = GENERATED_HEADER
    uninstallOutput = GENERATED_HEADER
    mappingOut = "Block breaking mapping:\n\n"
    for sbn, name in shared.items():
        initOutput += f'scoreboard objectives add {sbns}{name} {sbn}\n'
        checkOutput += 'execute as @a[scores={'+sbns+name+'=1..}] run function #territories:on_break\n'
        checkOutput += 'execute as @a[scores={'+sbns+name+'=1..}] run scoreboard players set @s '+sbns+name+' 0\n'
        uninstallOutput += f'scoreboard objectives remove {sbns}{name}\n'
        mappingOut += f'{sbns}{name} -> {sbn}\n'

    ctx.data.extra['mappings/on_break.txt'] = TextFile(mappingOut)

    print('== STATISTICS ==')
    print(f'Total blocks registered: {len(shared)}')
    print(f'Init  : {len(initOutput)} char, {len(initOutput.splitlines())} lines')
    print(f'Hook  : {len(checkOutput)} char, {len(checkOutput.splitlines())} lines')
    print(f'Uninst: {len(uninstallOutput)} char, {len(uninstallOutput.splitlines())} lines')
    print('================')

    # add to datapack
    ns["block_break_hook/init"] = Function(initOutput)
    ns["block_break_hook/check"] = Function(checkOutput)
    ns["block_break_hook/uninstall"] = Function(uninstallOutput)

    # tag
    merged_tags["minecraft:load"].append('territories_generated:block_break_hook/init')
    merged_tags["territories:update_expensive"].append('territories_generated:block_break_hook/check')


def build_tags(ctx: Context):
    for k, v in merged_tags.items():
        print("finish: Generating merged tags", k, flush=True)
        ctx.data[k] = FunctionTag({"values": v})
