import contextlib
import os
import posixpath
import re
import logging
import bpy
import json
from time import time, sleep, strftime, gmtime
import sys

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

models_filepath = sys.argv[4]
scale = float(sys.argv[5])
game_decompiled_folder = sys.argv[6]

models_filepath = os.path.normpath(models_filepath)
game_decompiled_folder = os.path.normpath(game_decompiled_folder)

map_name = os.path.basename(models_filepath).replace('_models.json', '.fbx')
map_dirpath = os.path.dirname(models_filepath) + '\\fbx'

txt_path = f'{os.path.dirname(models_filepath)}\\blender_time.txt'
if os.path.isfile(txt_path):
    os.remove(txt_path)

def clean_scene():
    for data_objects in bpy.data.objects:
        bpy.data.objects.remove(data_objects)
    for data_actions in bpy.data.actions:
        bpy.data.actions.remove(data_actions)
    for data_armatures in bpy.data.armatures:
        bpy.data.armatures.remove(data_armatures)
    for data_meshes in bpy.data.meshes:
        bpy.data.meshes.remove(data_meshes)
    for data_materials in bpy.data.materials:
        bpy.data.materials.remove(data_materials)
    for data_collections in bpy.data.collections:
        bpy.data.collections.remove(data_collections)


with open(models_filepath) as json_file:
    models_files = json.loads(json_file.read())

total = len((models_files['map_models'] + models_files['skybox_models'] + models_files['map_props_models'] + models_files['skybox_props_models']))
logger.info(f'Total VMDL files: {total}')
sleep(2)

clean_scene()


def generate_new_name(vmdl_name, random_hex):
    main_regex = re.compile(r'^.*lr\d*_(.+)')
    agg_regex = re.compile(r'agg\d*_\d*')
    c_regex = re.compile(r'^[a-z]*\d*[a-z]*_')

    main_match = main_regex.search(vmdl_name)
    if main_match:
        rough_name = main_match.group(1)

        # Check for 'agg' or 'c' matches
        agg_match = agg_regex.search(rough_name)
        c_match = c_regex.search(rough_name)

        if agg_match:
            start_name = agg_match.group(0)
        elif c_match:
            start_name = c_match.group(0)
        else:
            start_name = vmdl_name

        lp_match = re.search(r'_lp\d*', vmdl_name)
        overlay_match = re.search(r'_overlay\d*', vmdl_name)
        if lp_match:
            final_name = start_name + lp_match.group(0)
        elif overlay_match:
            final_name = start_name + overlay_match.group(0)
        else:
            final_name = start_name

        for f in ['_nz', '_nz_nsh', '_nsh']:
            if vmdl_name.endswith(f):
                final_name = f'{final_name}{f}'
                break

        final_name = f'{final_name}_{random_hex}'
        final_name = re.sub(r'_+', '_', final_name)
        return final_name

    else:
        final_name = f'{vmdl_name}_{random_hex}'
        return final_name


def get_materials(objcts, material_list):
    if objcts.type != 'MESH':
        return []

    materials = objcts.data.materials

    mesh_material_list = [material.name for material in materials if material is not None]
    found_materials = [
        next((material for material in material_list if mesh == posixpath.basename(material)), None)
        for mesh in mesh_material_list
    ]
    if all(material is None for material in found_materials):
        found_materials = [
            next((material for material in material_list if posixpath.basename(material).startswith(mesh)), None)
            for mesh in mesh_material_list
        ]
    if all(material is None for material in found_materials):
        found_materials = []

    return found_materials


def convert_vertex():
    logger.info('Converting UVs to vertex colors')
    for ob in bpy.data.objects:

        TEXCOORD_4_uv_values = []
        TEXCOORD_4_2_uv_values = []

        for uv in ob.data.uv_layers:
            if uv.name == 'TEXCOORD_4':
                TEXCOORD_4_uv_values = list(uv.uv)
            elif uv.name == 'TEXCOORD_4_2':
                TEXCOORD_4_2_uv_values = list(uv.uv)

        if not TEXCOORD_4_uv_values or not TEXCOORD_4_2_uv_values:
            while ob.data.color_attributes and ob.data.color_attributes[0].name != 'COLOR':
                ob.data.color_attributes.remove(ob.data.color_attributes[0])
            continue

        color_values = []
        for indx in range(len(TEXCOORD_4_uv_values)):
            r = list(TEXCOORD_4_uv_values[indx].vector)[0]
            g = [1 - f for f in TEXCOORD_4_uv_values[indx].vector][1]
            b = [1 - f for f in TEXCOORD_4_2_uv_values[indx].vector][1]
            a = list(TEXCOORD_4_2_uv_values[indx].vector)[0]
            color_values.append([r, g, b, a])

        colattr = ob.data.color_attributes.new(
            name='VERTEXPAINT',
            type='BYTE_COLOR',
            domain='CORNER',
        )

        for v_index in range(len(color_values)):
            colattr.data[v_index].color = color_values[v_index]

        # remove color attributes
        while ob.data.color_attributes and ob.data.color_attributes[0].name != 'VERTEXPAINT':
            ob.data.color_attributes.remove(ob.data.color_attributes[0])


def export_fbx(filepath, use_selection=False):
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=use_selection,
        bake_anim=False,
        mesh_smooth_type='FACE',
        bake_space_transform=True,
        add_leaf_bones=False,
        global_scale=scale / 100)


def export_fbx_animation(filepath):
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=True,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False,
        bake_space_transform=True,
        bake_anim_simplify_factor=0,
        object_types={'ARMATURE'},
        add_leaf_bones=False,
        global_scale=scale / 100)


def fix_bones_length(armature):
    if armature and armature.type == 'ARMATURE':
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode='EDIT')
        for bone in armature.data.edit_bones:
            current_length = bone.length
            new_length = current_length / 50
            bone.length = new_length
            logger.info(f"Bone: {bone.name}, Old Length: {current_length}, New Length: {new_length}")
        bpy.ops.object.mode_set(mode='OBJECT')


def natural_sort_key(s):
    # Split the string into a list of numbers and non-numeric parts
    return [int(text) if text.isdigit() else text for text in re.split('([0-9]+)', s)]


def join_objects(object_list):
    valid_meshes = [obj for obj in object_list if obj is not None and obj.name in bpy.data.objects]
    valid_meshes.sort(key=lambda obj: natural_sort_key(obj.name))
    if valid_meshes:  # Ensure there are valid meshes to work with
        bpy.context.view_layer.objects.active = valid_meshes[0]  # Set the first valid mesh as active
        for obj in valid_meshes:
            obj.select_set(True)  # Select each valid mesh
        bpy.ops.object.join()
        return valid_meshes[0]


def create_mesh_dict(drawcall_index: int, name: str, entity_tint_color: list, vwnod_tint_color: list, mesh_dictionary: dict, obj: bpy.types.Object):
    def add_data(key):
        data = mesh_dictionary['parsed_data'][drawcall_index].get(key, None)
        if data:
            mesh_data[key] = data

    mesh_data = {
        'drawcall_index': drawcall_index, 'name': name,
        'material': get_materials(obj, mesh_dictionary.get('model_materials', []))
    }

    if entity_tint_color:
        mesh_data['entity_tint_color'] = entity_tint_color
    if vwnod_tint_color:
        mesh_data['vwnod_tint_color'] = vwnod_tint_color

    if drawcall_index >= len(mesh_dictionary['parsed_data']):
        return mesh_data

    add_data('vwnod_transform')
    add_data('entity_transform')
    add_data('entity_data')
    add_data('vwnod_skin')
    add_data('entity_skin')
    add_data('object_type_flags')
    add_data('overlay_render_order')

    return mesh_data


def process_meshes(mesh_dictionary: dict, object_list: list, object_name: str, instanced: bool = False, prop: bool = False, vmesh: bool = False):
    mesh_dictionary['mesh_data'] = []

    if not prop:
        object_list.sort(key=lambda ob: natural_sort_key(ob.name))

    if instanced:
        for n, obj in enumerate(object_list):
            drawcall_index = str(n) if prop else str(obj.name)
            if '.' in drawcall_index:
                drawcall_index = drawcall_index.split('.')[0]
            logger.info(f'Current drawcall: {drawcall_index}')
            new_name = f'{object_name}_{drawcall_index}'
            obj.name = new_name
            obj.data.name = new_name

            try:
                mesh_dictionary['parsed_data'][int(drawcall_index)]
            except IndexError:
                if vmesh:
                    mesh_dictionary['mesh_data'].append(create_mesh_dict(int(drawcall_index), new_name,
                                                                         [], [[1.0, 1.0, 1.0, 1.0]],
                                                                         mesh_dictionary, obj))
                else:
                    return None
            else:
                mesh_dictionary['mesh_data'].append(create_mesh_dict(int(drawcall_index), new_name,
                                                                     mesh_dictionary['parsed_data'][int(drawcall_index)].get('entity_tint_color', []),
                                                                     mesh_dictionary['parsed_data'][int(drawcall_index)].get('vwnod_tint_color', []),
                                                                     mesh_dictionary, obj))

    else:
        # join all meshes with the same tint color
        existing_drawcalls = [obj.name for obj in object_list]

        tint_colors = []
        for mesh in mesh_dictionary['parsed_data']:
            if str(mesh.get('drawcall_index', 0)) in existing_drawcalls:
                tint_colors.extend(mesh.get("vwnod_tint_color", [1.0, 1.0, 1.0, 1.0]))

        all_colors_are_the_same = all(x == tint_colors[0] for x in tint_colors)

        logger.info(f'Colors are the same: {all_colors_are_the_same}')

        if all_colors_are_the_same:
            bpy.ops.object.select_all(action='DESELECT')

            if len(object_list) > 1:
                logger.warning(f'Joined {len(object_list)} meshes')
                object_list = join_objects(object_list)

            else:
                object_list = object_list[0]

            drawcall_index = str(object_list.name)
            new_name = f'{object_name}_{drawcall_index}'
            object_list.name = new_name
            object_list.data.name = new_name

            mesh_dictionary['mesh_data'].append(create_mesh_dict(int(drawcall_index), new_name,
                                                                 [], tint_colors[0],
                                                                 mesh_dictionary, object_list))

        else:
            # remove duplicated colors
            used_colors = [list(x) for x in dict.fromkeys(tuple(x) for x in tint_colors)]
            logger.warning(f'Using {len(used_colors)} colors')

            for n, color in enumerate(used_colors):
                bpy.ops.object.select_all(action='DESELECT')
                logger.info(f'Current color: {color}')
                same_tinted_meshes = [object_list[i] for i, c in enumerate(tint_colors) if c == color]
                logger.info(f'Drawcalls indexes for same tinted meshes: {[f.name for f in same_tinted_meshes]}')

                if len(same_tinted_meshes) > 1:
                    logger.warning(f'Joined {len(same_tinted_meshes)} meshes')
                    same_tinted_meshes = join_objects(same_tinted_meshes)
                else:
                    same_tinted_meshes = same_tinted_meshes[0]

                new_name = f'{object_name}_{n}'
                same_tinted_meshes.name = new_name
                same_tinted_meshes.data.name = new_name

                mesh_dictionary['mesh_data'].append(create_mesh_dict(n, new_name,
                                                                     [], color, mesh_dictionary,
                                                                     same_tinted_meshes))


def remove_LODs(mesh_dictionary: dict, object_list: list):
    grouped_meshes = {}
    drawcall_indexes_to_remove = []

    for aggregate_mesh in mesh_dictionary.get('parsed_data', []):
        lod_setup_index = aggregate_mesh["lod_setup_index"]
        if lod_setup_index == -1:
            continue
        if lod_setup_index not in grouped_meshes:
            grouped_meshes[lod_setup_index] = []
        grouped_meshes[lod_setup_index].append(aggregate_mesh)

    drawcall_indexes_to_keep = []

    for lod_setup_index, meshes in grouped_meshes.items():
        # Find the mesh with the minimum lod_group_mask
        min_mesh = min(meshes, key=lambda mesh: mesh["lod_group_mask"])
        drawcall_indexes_to_keep.append(min_mesh["drawcall_index"])

        drawcall_indexes_to_remove.extend(
            mesh["drawcall_index"] for mesh in meshes if mesh["drawcall_index"] != min_mesh["drawcall_index"]
        )

    objects_to_remove = [obj for dc in drawcall_indexes_to_remove for obj in object_list if obj.name == str(dc)]
    meshes_to_remove = [obj.data for obj in objects_to_remove]

    logger.info(f'Found {len(objects_to_remove)} LODs to remove\n')

    for i, obj in enumerate(objects_to_remove):
        logger.warning(f'[{i + 1}/{len(objects_to_remove)}] Removing LOD for drawcall index "{obj.name}"')
        bpy.data.objects.remove(obj, do_unlink=True)

    for mesh in meshes_to_remove:
        if mesh:  # Check if the mesh still exists
            bpy.data.meshes.remove(mesh)

    print('')
    return list(bpy.data.objects)


def remove_LODs_for_props(objcts):
    lod_exists = any('_LOD0' in o.name for o in objcts)
    if lod_exists:
        objects_to_remove = [o for o in objcts if '_LOD0' not in o.name]

        for o in objects_to_remove:
            logger.warning(f'Removing LOD mesh {o.name}')
            ob_data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(ob_data)

        return list(bpy.data.objects)
    else:
        return objcts


error_meshes_to_skip = []


def import_export_world_models(dictionary, part_name, sky=False):
    clean_scene()
    for i, model_dict in enumerate(dictionary):
        print('\n')
        vmdl_c_path = model_dict.get('vmdl_c_path')
        if vmdl_c_path is None:
            continue

        model_material_list = model_dict.get('model_materials')
        if model_material_list is None:
            logger.warning(f'Cant find material for model "{vmdl_c_path}", skipping')
            continue

        if model_dict.get('name') is not None:
            logger.warning(f'Model "{vmdl_c_path}" already converted, skipping')
            continue

        vmdl_c_path = os.path.normpath(os.path.join(game_decompiled_folder, vmdl_c_path))

        logger.info(f'Working with model "{vmdl_c_path}"')
        folder_path = os.path.dirname(vmdl_c_path)

        is_vmesh = 'is_vmesh' in model_dict

        try:
            bpy.ops.sourceio.vmdl(discover_resources=False, scale=1, files=[{'name': vmdl_c_path}], custom_directory=folder_path)
        except Exception:
            error_meshes_to_skip.append((part_name, i))
        # Remove existing armatures
        for data_armatures in bpy.data.armatures:
            bpy.data.armatures.remove(data_armatures)

        new_imported_objects = list(bpy.data.objects)
        logger.info(f'Number of imported objects: {len(new_imported_objects)}')

        if not new_imported_objects:
            clean_scene()
            continue

        if is_vmesh:
            new_imported_objects = remove_LODs_for_props(new_imported_objects)
            new_imported_objects.sort(key=lambda ob: natural_sort_key(ob.name))
            for s in range(len(new_imported_objects)):
                new_imported_objects[s].name = str(s)
            new_imported_objects = list(bpy.data.objects)

        else:
            lod_pattern = re.compile(r'(_LOD\d+)$')
            for obj in bpy.data.objects:
                if obj.type != 'MESH':
                    continue
                # Remove LOD suffixes from the object's name
                new_name = lod_pattern.sub('', obj.name)
                if new_name != obj.name:
                    obj.name = new_name
                if obj.data:
                    new_data_name = lod_pattern.sub('', obj.data.name)
                    if new_data_name != obj.data.name:
                        obj.data.name = new_data_name

        mesh_name = os.path.basename(vmdl_c_path).replace('.vmdl_c', '')
        mesh_name = generate_new_name(mesh_name, model_dict.get('hex'))
        mesh_name = f'sky__{mesh_name}' if sky is True else mesh_name

        logger.info(f'Mesh name: {mesh_name}')

        aggregate_object = model_dict.get('num_aggregate_meshes') is not None

        if is_vmesh:
            process_meshes(model_dict, new_imported_objects, mesh_name, instanced=True, vmesh=True)

        else:
            if aggregate_object:
                have_lods = model_dict.get('num_lods', 0) > 0
                logger.info(f'Have LODs: {have_lods}')

                if have_lods:
                    new_imported_objects = remove_LODs(model_dict, new_imported_objects)

                instanced_mesh = model_dict.get('entity_instances', 0) > 0 or model_dict.get('vwnod_instances', 0) > 0
                if instanced_mesh:
                    process_meshes(model_dict, new_imported_objects, mesh_name, instanced=True)

                else:
                    process_meshes(model_dict, new_imported_objects, mesh_name, instanced=False)

            else:
                process_meshes(model_dict, new_imported_objects, mesh_name, instanced=False)

        convert_vertex()

        # export
        for ob in bpy.data.objects:
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = ob
            ob.select_set(True)
            fbx_name = ob.name
            export_fbx(f'{os.path.join(map_dirpath, fbx_name)}.fbx', use_selection=True)

        clean_scene()


def import_export_props(dictionary):
    clean_scene()
    for p in dictionary:
        for prop_model_dict in p:
            print('\n')
            m_name = prop_model_dict.get("vmdl_c_path")
            m_name = os.path.normpath(os.path.join(game_decompiled_folder, m_name))

            prop_name = os.path.basename(m_name.replace('.vmdl_c', ''))
            prop_path = m_name.replace('.vmdl_c', '.fbx')
            folder_path = os.path.dirname(prop_path)

            if 'mesh_data' not in prop_model_dict:
                prop_model_dict['mesh_data'] = []

            if 'parsed_data' not in prop_model_dict:
                continue

            logger.info(f'Current prop: {prop_path}')
            logger.info(f'Current hex: {prop_model_dict.get("hex")}')

            gltf_path = prop_model_dict.get('gltf_path')
            is_gltf = True if gltf_path is not None and os.path.exists(gltf_path) else False

            if is_gltf:
                bpy.ops.import_scene.gltf(filepath=gltf_path, import_shading='SMOOTH')

                icosphere_object = next((o for o in bpy.data.objects if 'Icosphere' in o.name), None)
                if icosphere_object is not None:
                    meshes_to_remove = icosphere_object.data
                    bpy.data.objects.remove(icosphere_object, do_unlink=True)
                    if meshes_to_remove:
                        bpy.data.meshes.remove(meshes_to_remove)
                for obj in bpy.data.objects:
                    fix_bones_length(obj)

            else:
                bpy.ops.sourceio.vmdl(discover_resources=False, scale=1, files=({'name': m_name},), custom_directory=folder_path)
                for data_armatures in bpy.data.armatures:
                    bpy.data.armatures.remove(data_armatures)

            new_imported_objects = remove_LODs_for_props(list(bpy.data.objects))
            prop_objects = [o for o in new_imported_objects if o.type == 'MESH']

            if len(prop_objects) > 1:
                vertex_groups_meshes = [o for o in prop_objects if o.vertex_groups]
                non_vertex_groups_meshes = [o for o in prop_objects if not o.vertex_groups]

                if vertex_groups_meshes and non_vertex_groups_meshes:
                    for obj in non_vertex_groups_meshes:
                        logger.info(f'Removing not linked to an armature mesh {obj.name}')
                        bpy.data.objects.remove(obj, do_unlink=True)

                    new_imported_objects = list(bpy.data.objects)

                if vertex_groups_meshes:
                    new_imported_objects = join_objects(vertex_groups_meshes)
                    new_imported_objects.name = prop_name
                    new_imported_objects.data.name = prop_name
                    new_imported_objects = [new_imported_objects]

            if is_gltf:
                armature = None
                anim_fbx_folder = f'{folder_path}\\{prop_name}_animations'
                if not os.path.exists(anim_fbx_folder):
                    os.makedirs(anim_fbx_folder)

                anims = [p.get('animname') for p in prop_model_dict['parsed_data'][0]['entity_data']]

                logger.info('Exporting animations')
                for obj in bpy.context.scene.objects:
                    if 'Icosphere' in obj.name:
                        continue

                    if obj.type == 'ARMATURE':
                        armature = obj
                        obj.name = 'root'
                        obj.scale = (1.0, 1.0, 1.0)
                        obj.rotation_mode = 'QUATERNION'
                        obj.rotation_quaternion = (0.5, -0.5, 0.0, 0.0)

                        if obj.animation_data and obj.animation_data.nla_tracks:
                            bpy.ops.object.select_all(action='DESELECT')
                            obj.select_set(True)
                            bpy.context.view_layer.objects.active = obj

                            for track in obj.animation_data.nla_tracks:
                                if track.name not in anims:
                                    continue
                                print(f"Track Name: {track.name}")
                                action = bpy.data.actions.new(name=track.name)
                                bpy.context.scene.frame_start = int(track.strips[0].frame_start)
                                frame_end = 5 if int(track.strips[0].frame_end) <= 2 else int(track.strips[0].frame_end)
                                bpy.context.scene.frame_end = frame_end

                                # Copy the strips to the new action
                                for strip in track.strips:
                                    print(f"  Strip Name: {strip.name}, Start: {strip.frame_start}, End: {strip.frame_end}")

                                    # Check if the strip has an action
                                    if strip.action:
                                        print(f"    Found action: {strip.action.name}")

                                        # Iterate through each fcurve in the action
                                        for fcurve in strip.action.fcurves:
                                            # Create a new fcurve in the action for the same data path
                                            new_fcurve = action.fcurves.new(data_path=fcurve.data_path, index=fcurve.array_index)

                                            # Copy keyframes from the actions fcurve to the new fcurve
                                            for point in fcurve.keyframe_points:
                                                # Insert keyframe points into the new fcurve
                                                new_keyframe = new_fcurve.keyframe_points.insert(frame=point.co[0], value=point.co[1])
                                                new_keyframe.interpolation = point.interpolation  # Copy interpolation type
                                                new_keyframe.handle_left_type = point.handle_left_type  # Copy handle types
                                                new_keyframe.handle_right_type = point.handle_right_type

                                # Set the action to the object
                                obj.animation_data.action = action

                                print(f'Exporting {track.name}.fbx')

                                if len(action.name.split('\\')) > 1:
                                    anim_name = f'{prop_name}_' + track.name.split('\\')[0]
                                else:
                                    anim_name = track.name

                                anim_path = os.path.join(anim_fbx_folder, f'{anim_name}.fbx')

                                if 'fbx_anim_list' not in prop_model_dict:
                                    prop_model_dict['fbx_anim_list'] = []

                                if anim_path not in prop_model_dict['fbx_anim_list']:
                                    prop_model_dict['fbx_anim_list'].append(anim_path)

                                export_fbx_animation(anim_path)
                                bpy.data.actions.remove(action)

                if armature is not None:
                    for obj in bpy.context.scene.objects:
                        if 'Icosphere' in obj.name:
                            continue

                        if obj.type == 'MESH':
                            bpy.ops.object.select_all(action='DESELECT')
                            armature.select_set(True)
                            obj.select_set(True)
                            export_fbx(prop_path)

            else:
                for ob in bpy.data.objects:
                    bpy.ops.object.select_all(action='DESELECT')
                    bpy.context.view_layer.objects.active = ob
                    ob.select_set(True)
                    export_fbx(prop_path, use_selection=False)

            if len(new_imported_objects) > 1 and not is_gltf:
                new_imported_objects = join_objects(new_imported_objects)
                new_imported_objects.name = prop_name
                new_imported_objects.data.name = prop_name
                new_imported_objects = [new_imported_objects]

            prop_objects = [o for o in new_imported_objects if o.type == 'MESH']
            process_meshes(prop_model_dict, prop_objects, prop_name, instanced=True, prop=True)
            prop_model_dict['fbx_path'] = prop_path
            clean_scene()


start_time = time()

import_export_world_models(models_files['map_models'], 'map_models')
import_export_world_models(models_files['skybox_models'], 'skybox_models', sky=True)
import_export_props([models_files['map_props_models'] + models_files['skybox_props_models']])

for error in error_meshes_to_skip:
    print(error)
    part_name, dict_indx = error
    if part_name in models_files:
        if 0 <= dict_indx < len(models_files[part_name]):
            models_files[part_name].pop(dict_indx)

with open(models_filepath, 'w') as props_outmodel:
    json.dump(models_files, props_outmodel, indent=4)

end_time = strftime("%Hh %Mm %Ss", gmtime(time() - start_time))
logger.info(f'\nMap total time: {end_time}')
print('\nF I N I S H E D')

with open(txt_path, 'w') as f:
    f.write(end_time)

sleep(2)
print('\n')
