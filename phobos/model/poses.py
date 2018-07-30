#!/usr/bin/python
# coding=utf-8

"""
.. module:: phobos.exporter
    :platform: Unix, Windows, Mac
    :synopsis: TODO: INSERT TEXT HERE

.. moduleauthor:: Kai von Szadowski

Copyright 2014, University of Bremen & DFKI GmbH Robotics Innovation Center

This file is part of Phobos, a Blender Add-On to edit robot models.

Phobos is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version.

Phobos is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with Phobos.  If not, see <http://www.gnu.org/licenses/>.

File meshes.py

Created on 13 Feb 2014
"""

import os
import yaml
import bpy
import phobos.utils.selection as sUtils
import phobos.utils.editing as eUtils
import phobos.utils.naming as nUtils
import phobos.utils.blender as bUtils
import phobos.utils.general as gUtils
import phobos.utils.io as ioUtils
from phobos.utils.validation import validate
from phobos.phoboslog import log
from phobos.utils.io import securepath


@validate('object_pose')
def deriveObjectPose(obj, logging=False):
    """Derives a pose of link, visual or collision object.

    The transformations of the object are calculated according to
    phobos.utils.edititing.getCombinedTransform.

    The returned dictionary contains this information:
        *rawmatrix*: mathutils.Matrix
        *matrix*: list representation (list of lists) of mathutils.Matrix
        *translation*: list (according to mathutils.Matrix.to_translation)
        *rotation_euler*: list (according to mathutils.Matrix.to_euler)
        *rotation_quaternion*: list (according to mathutils.Matrix.to_quaternion)

    :param obj: blender object to derive the pose from
    :type obj: bpy.types.Object

    :return: pose information of the object
    :rtype: dict

    .. seealso phobos.utils.editing.getCombinedTransform
    """
    effectiveparent = sUtils.getEffectiveParent(obj)
    matrix = eUtils.getCombinedTransform(obj, effectiveparent)

    pose = {'rawmatrix': matrix,
            'matrix': [list(vector) for vector in list(matrix)],
            'translation': list(matrix.to_translation()),
            'rotation_euler': list(matrix.to_euler()),
            'rotation_quaternion': list(matrix.to_quaternion())}

    if logging:
        log("Location: " + str(pose['translation']) + " Rotation: " + str(pose['rotation_euler']),
            'DEBUG')
    return pose


def bakeModel(objlist, modelname, posename="", decimate_type='COLLAPSE', decimate_parameter=0.1):
    """This function gets a list of objects and creates a single, simplified mesh from it and exports it to .stl.

    Args:
      objlist(list: list): The list of blender objects to join and export as simplified stl file.
      modelname(str): The new models name and filename.
      posename:  (Default value = "")
      decimate_type:  (Default value = 'COLLAPSE')
      decimate_parameter:  (Default value = 0.1)

    Returns:

    """
    if bpy.context.scene.phobosexportsettings.relativePath:
        # CHECK careful with path consistency (Windows)
        outpath = securepath(os.path.expanduser(os.path.join(bpy.path.abspath("//"), bpy.context.scene.phobosexportsettings.path)))
    else:
        # CHECK careful with path consistency (Windows)
        outpath = securepath(os.path.expanduser(bpy.context.scene.phobosexportsettings.path))

    # TODO delete me?
    #bake_outpath = securepath(os.path.join(outpath, modelname) if savetosubfolder else outpath)
    bake_outpath = outpath

    if bpy.context.scene.phobosexportsettings.structureExport:
        securepath(os.path.join(bake_outpath, 'bakes'))
        bake_outpath = os.path.join(bake_outpath, 'bakes/')

    export_name = modelname + '_' + posename

    visuals = [o for o in objlist if ("phobostype" in o and o.phobostype == "visual")]
    if len(visuals) > 0:

        log("Baking model to " + bake_outpath, "INFO")
        sUtils.selectObjects(visuals, active=0)
        log("Copying objects for joining...", "INFO")
        bpy.ops.object.duplicate(linked=False, mode='TRANSLATION')
        log("Joining...", "INFO")
        bpy.ops.object.join()
        obj = bpy.context.active_object
        log("Deleting vertices...", "INFO")
        bpy.ops.object.editmode_toggle()
        bpy.ops.mesh.select_all(action='TOGGLE')
        bpy.ops.mesh.select_all(action='TOGGLE')
        bpy.ops.mesh.remove_doubles()
        bpy.ops.object.editmode_toggle()
        log("Adding modifier...", "INFO")

        bpy.ops.object.modifier_add(type='DECIMATE')
        bpy.context.object.modifiers["Decimate"].decimate_type = decimate_type
        if decimate_type == 'COLLAPSE':
            bpy.context.object.modifiers["Decimate"].ratio = decimate_parameter
        elif decimate_type == 'UNSUBDIV':
            bpy.context.object.modifiers["Decimate"].iterations = decimate_parameter
        elif decimate_type == 'DISSOLVE':
            bpy.context.object.modifiers["Decimate"].angle_limit = decimate_parameter

        log("Applying modifier...", "INFO")
        bpy.ops.object.modifier_apply(apply_as='DATA', modifier="Decimate")
        obj.name = export_name + ".obj"

        # TODO use_selection might cause bugs, depending on Blender version
        bpy.ops.export_scene.obj(filepath=os.path.join(bake_outpath, obj.name), use_selection=True)

        obj.hide_render = True
        previewfile = export_name
        bUtils.createPreview(visuals, export_path=bake_outpath, modelname=modelname, previewfile=previewfile)

        obj.select = True

        bpy.ops.object.delete()
        log("Done baking...", "INFO")

    else:
        log("No visuals to bake!", "WARNING")


def storePose(root, posename):
    """Stores the current pose of all of a model's selected joints.

    Existing poses of the same name will be overwritten.

    Args:
      root(bpy_types.Object): root of the model the pose belongs to
      posename(str): name the pose will be stored under

    Returns:
      Nothing.

    """
    if root:
        filename = nUtils.getModelName(root) + '::poses'
        posedict = yaml.load(bUtils.readTextFile(filename))
        if not posedict:
            posedict = {posename: {'name': posename, 'joints': {}}}
        else:
            posedict[posename] = {'name': posename, 'joints': {}}
        links = sUtils.getChildren(root, ('link',), True, False)
        sUtils.selectObjects([root]+links, clear=True, active=0)
        bpy.ops.object.mode_set(mode='POSE')
        for link in (link for link in links if 'joint/type' in link and
                     link['joint/type'] not in ['fixed', 'floating']):
            link.pose.bones['Bone'].rotation_mode = 'XYZ'
            posedict[posename]['joints'][nUtils.getObjectName(link, 'joint')] = link.pose.bones[
                'Bone'].rotation_euler.y
        bpy.ops.object.mode_set(mode='OBJECT')
        posedict = gUtils.roundFloatsInDict(posedict, ioUtils.getExpSettings().decimalPlaces)
        bUtils.updateTextFile(filename, yaml.dump(posedict, default_flow_style=False))
    else:
        log("No model root provided to store the pose for", "ERROR")


def loadPose(modelname, posename):
    """Load and apply a robot's stored pose.

    :param modelname: the model's name
    :type modelname: str
    :param posename: the name the pose is stored under
    :type posename: str
    """

    load_file = bUtils.readTextFile(modelname + '::poses')
    if load_file == '':
        log('No poses stored.', 'ERROR')
        return

    loadedposes = yaml.load(load_file)
    if posename not in loadedposes:
        log('No pose with name ' + posename + ' stored for model ' + modelname, 'ERROR')
        return
    prev_mode = bpy.context.mode
    pose = loadedposes[posename]

    # apply rotations to all joints defined by the pose
    try:
        bpy.ops.object.mode_set(mode='POSE')
        for obj in sUtils.getObjectsByPhobostypes(['link']):
            if nUtils.getObjectName(obj, 'joint') in pose['joints']:
                obj.pose.bones['Bone'].rotation_mode = 'XYZ'
                obj.pose.bones['Bone'].rotation_euler.y = float(
                    pose['joints'][nUtils.getObjectName(obj, 'joint')])
    except KeyError as error:
        log("Could not apply the pose: " + str(error), 'ERROR')
    finally:
        # restore previous mode
        bpy.ops.object.mode_set(mode=prev_mode)


def getPoses(modelname):
    """Get the names of the poses that have been stored for a robot.

    Args:
      modelname: The model's name.

    Returns:
      A list containing the poses' names.

    """
    load_file = bUtils.readTextFile(modelname + '::poses')
    if load_file == '':
        return []
    poses = yaml.load(load_file)
    return poses.keys()
