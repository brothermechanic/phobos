import os
from typing import List
from copy import deepcopy

import numpy as np

from . import representation, xml_factory, sensor_representations
from .base import Representation
from ..utils.transform import create_transformation, get_adjoint, inv
from ..utils.tree import get_joints_depth_first


class XMLRobot(Representation):
    SUPPORTED_VERSIONS = ["1.0"]

    def __init__(self, name=None, version=None, links: List[representation.Link] = None,
                 joints: List[representation.Joint] = None,
                 materials: List[representation.Material] = None,
                 transmissions: List[representation.Transmission] = None,
                 sensors=None, xmlfile=None):
        super().__init__()
        self.joints = []
        self.links = []
        self.parent_map = {}
        self.child_map = {}
        self.materials = []
        self.transmissions = []
        self.sensors = []
        self.xmlfile = xmlfile

        if name is None or len(name) == 0:
            if self.xmlfile is not None:
                self.name, _ = os.path.splitext(xmlfile)
            else:
                self.name = None
        else:
            self.name = name
        if version is None:
            version = "1.0"
        elif type(version) is not str:
            version = str(version)
        if version not in self.SUPPORTED_VERSIONS:
            raise ValueError("Invalid version; only %s is supported" % (','.join(self.SUPPORTED_VERSIONS)))

        self.version = version

        if joints is not None:
            for joint in joints:
                self.add_aggregate("joint", joint)
        if links is not None:
            for link in links:
                self.add_aggregate("link", link)

        self.materials = materials if materials is not None else []
        self.transmissions = transmissions if transmissions is not None else []
        self.sensors = sensors if sensors is not None else []

        self.link_entities()

    def __str__(self):
        return self.name

    @property
    def collisions(self):
        return self.get_all_collisions()

    @property
    def visuals(self):
        return self.get_all_visuals()

    def link_entities(self):
        for entity in self.links + self.joints + self.sensors:
            entity.link_with_robot(self)

    def unlink_entities(self):
        for entity in self.links + self.joints + self.sensors:
            entity.unlink_from_robot()

    def relink_entities(self):
        self.unlink_entities()
        self.link_entities()

    def duplicate(self):
        self.unlink_entities()
        out = deepcopy(self)
        self.link_entities()
        out.link_entities()
        return out

    def _get_children_lists(self, parentlist, childrenlist, targettype='link'):
        """
        Used recursively. Returns a list of all links that can be considered parents/children for the given parent list
        :param parentlist:
        :param childrenlist:
        :param targettype:
        :return:
        """
        childs = []
        for parent in parentlist:
            childs += self.get_children(parent, targettype=targettype)

        if len(childs) > 0:
            newparents, newchildren = self._get_children_lists(childs, [])
            return parentlist + newparents, childrenlist + childs + newchildren
        else:
            return [], []

    def _rename(self, targettype, target, new_name, further_targettypes=None):
        if target == new_name:
            return {}
        # new_name exists? otherwise we'd have to fix the name
        assert (self.get_aggregate(targettype, new_name) is None,
                f"Can't rename {targettype} {target} to {new_name} as the new name already exists")

        other_targettypes = ['collision', 'visual', 'material']
        if further_targettypes is not None:
            other_targettypes += further_targettypes
        other_targettypes = set([o[:-1] if o.endswith("s") else o for o in other_targettypes])
        other_targettypes = list(other_targettypes) + [o+"s" if not o.endswith("s") else o for o in other_targettypes]
        index = None  # gives the index of joint or link for parent/child maps
        renamed = False
        if targettype in ['link', "links"]:
            index = 1
            obj = self.get_link(target)
            if obj is not None:
                obj.set_unique_name(new_name)
                renamed = True
        elif targettype in ['joint', "joints"]:
            index = 0
            obj = self.get_joint(target)
            if obj is not None:
                obj.set_unique_name(new_name)
                renamed = True
        if targettype in ["link", "links", "joint", "joints"]:
            # Iterate over the values of parent child map and rename the values
            new_child_map = {}
            for k, v in self.child_map.items():
                for i, vi in enumerate(v):
                    if target == vi[index]:
                        v[i] = tuple([new_name if i == index else n for i, n in enumerate(vi)])
                if k == target:
                    new_child_map[new_name] = v
                else:
                    new_child_map[k] = v
            self.child_map = new_child_map

            new_parent_map = {}
            for k, v in self.parent_map.items():
                if target == v[index]:
                    v = tuple([new_name if i == index else n for i, n in enumerate(v)])
                if k == target:
                    new_parent_map[new_name] = v
                else:
                    new_parent_map[k] = v
            self.parent_map = new_parent_map
        elif targettype in other_targettypes:
            obj = self.get_aggregate(targettype, target)
            if obj is not None:
                obj.set_unique_name(new_name)
                renamed = True
        if renamed:
            return {target: new_name}
        return {}

    def regenerate_tree_maps(self):
        """
        Regenerates the child and parent maps
        """
        self.child_map = {}
        self.parent_map = {}
        # the link entries
        for j in self.joints:
            self.parent_map[j.child] = (j.name, j.parent)
            if j.parent in self.child_map:
                self.child_map[j.parent].append((j.name, j.child))
            else:
                self.child_map[j.parent] = [(j.name, j.child)]
        # the joint entries
        for j in self.joints:
            self.parent_map[j.name] = (self.parent_map[j.parent][0] if j.parent in self.parent_map else None, j.parent)
            if j.name in self.child_map:
                self.child_map[j.name].append((self.child_map[j.child][0] if j.child in self.child_map else None, j.child))
            else:
                self.child_map[j.name] = [(self.child_map[j.child][0] if j.child in self.child_map else None, j.child)]

    def add_aggregate(self, typeName, elem, silent=False):
        if type(elem) == list:
            return [self.add_aggregate(typeName, e) for e in elem]
        if typeName in 'joints':
            self.parent_map[str(elem.child)] = (elem.name, elem.parent)
            self.parent_map[str(elem.name)] = (elem.name, elem.parent)
            if elem.parent in self.child_map:
                self.child_map[elem.parent].append((elem.name, elem.child))
            else:
                self.child_map[elem.parent] = [(elem.name, elem.child)]
            if elem not in self.joints:
                self.joints += [elem]
        elif typeName in 'links':
            if elem not in self.links:
                self.links += [elem]
        else:
            if not typeName.endswith("s"):
                typeName += "s"
            # Collect all instances which have the same name
            instances = []
            # Original list
            objects = getattr(self, typeName)
            object_names = [str(obj) for obj in objects]
            counter = 1
            if str(elem) in object_names:
                while str(elem) + f"_{counter}" in object_names:
                    counter += 1
                if not silent:
                    print(f"Renamed {typeName} {str(elem)} to {str(elem)}_{counter}")
                elem.set_unique_name(str(elem) + f"_{counter}")
            objects += [elem]
            setattr(self, typeName, objects)

    def remove_aggregate(self, typeName, elem):
        """
        Removes the given aggregate
        ATTENTION: This simply removes the aggregate, removing links and joints using only this may corrupt
        the robot structure
        """
        if type(elem) == str:
            elem = self.get_aggregate(typeName, elem)
        if elem is None:
            return
        if type(elem) == list:
            return [self.remove_aggregate(typeName, e) for e in elem]
        if typeName in 'joints' or typeName in "links":
            # find the corresponding link/joint we have to delete as well
            if typeName in "joints":
                joint = elem
                child = self.get_aggregate("link", elem.child)
            else:
                child = elem
                joint = self.get_parent(child)
                if joint is not None:
                    joint = self.get_joint(joint)
                else:  # in case we want to delete the root link
                    raise NotImplementedError("Deleting the root link, when is not yet possible!")

            parent = self.get_link(joint.parent)
            if child.name in self.child_map.keys():
                next_joints = [names[0] for names in self.child_map[child.name]]
            else:
                next_joints = []

            # Get the transformation
            C_T_P = self.get_transformation(start=parent.name, end=child.name)
            # merging the link when removing the joint
            if typeName in "joints":
                # Correct inertial if child inertial is found
                if child.inertial:
                    IC_T_P = C_T_P.dot(child.inertial.origin.to_matrix())
                    M_c = child.inertial.to_mass_matrix()
                    if parent.inertial:
                        COM_C = np.identity(4)
                        COM_C[0:3, 3] = np.array(child.inertial.origin.xyz)
                        COM_Cp = C_T_P.dot(COM_C)
                        new_origin = (
                                             np.array(parent.inertial.origin.xyz) * parent.inertial.mass +
                                             COM_Cp[0:3, 3] * child.inertial.mass) / (
                                                 parent.inertial.mass + child.inertial.mass)
                        new_origin = representation.Pose(xyz=new_origin, rpy=[0, 0, 0])
                        IC_T_IP = inv(parent.inertial.origin.to_matrix()).dot(IC_T_P)
                        M_p = parent.inertial.to_mass_matrix()
                        A = get_adjoint(new_origin.to_matrix())
                        M_p = np.dot(np.transpose(A), np.dot(M_p, A))
                    else:
                        IC_T_IP = IC_T_P
                        M_p = np.zeros((6, 6))
                        new_origin = representation.Pose.from_matrix(inv(IC_T_P))

                    A = get_adjoint(IC_T_IP.dot(new_origin.to_matrix()))
                    M = np.dot(np.transpose(A), np.dot(M_c, A)) + M_p
                    parent.inertial = representation.Inertial.from_mass_matrix(M, new_origin)

                for vis in child.visuals:
                    VC_T_P = C_T_P.dot(vis.origin.to_matrix())
                    vis.origin = representation.Pose.from_matrix(VC_T_P)
                    parent.add_aggregate('visual', vis)

                for col in child.collisions:
                    CC_T_P = C_T_P.dot(col.origin.to_matrix())
                    col.origin = representation.Pose.from_matrix(CC_T_P)
                    parent.add_aggregate('collision', col)
            # reparent the following joints
            new_joints = []
            for j in self.joints:
                if j is not joint:
                    if j.name in next_joints:
                        j.origin = representation.Pose.from_matrix(C_T_P.dot(j.origin.to_matrix()))
                        j.parent = parent.name
                    new_joints += [j]
            # remove the joint and links
            self.joints = new_joints
            self.links = [l for l in self.links if l is not child]
            self.regenerate_tree_maps()
            # check the consequences
            new_sensors = []
            for sensor in self.sensors:
                if isinstance(sensor, sensor_representations.MultiSensor):
                    sensor.remove_target([str(child), str(joint)])
                    if not sensor.is_empty():
                        new_sensors += [sensor]
                else:
                    if not hasattr(sensor, "joint") or sensor.joint != joint.name:
                        new_sensors += [sensor]
                    elif hasattr(sensor, "link") and sensor.link == joint.child:
                        sensor.transform(joint.origin.to_matrix())
                        sensor.link = str(parent)
                        new_sensors += [sensor]
            self.sensors = new_sensors

            new_transmissions = []
            for tm in self.transmissions:
                tm.joints = [j for j in tm.joints if str(j.name) != str(joint)]
                if len(tm.joints) > 0:
                    new_transmissions.append(tm)
            self.transmissions = new_transmissions
            return joint, child
        else:  # basically handle any other aggregates
            if not typeName.endswith("s"):
                typeName += "s"
            # Original list
            objects = getattr(self, typeName)
            setattr(self, typeName, [o for o in objects if o is not elem])

    def add_link(self, link):
        if not isinstance(link, representation.Link):
            raise AssertionError("Please provide an instance of Link to attach.")
        self.add_aggregate('link', link)

    def add_joint(self, joint):
        if not isinstance(joint, representation.Joint):
            raise AssertionError("Please provide an instance of Joint to attach.")
        self.add_aggregate('joint', joint)

    def add_sensor(self, sensor):
        if not isinstance(sensor, sensor_representations.Sensor):
            raise Exception(f"Please provide an instance of Sensor to attach. Received: {repr(type(sensor))}")
        self.add_aggregate('sensors', sensor)
        return

    def get_chain(self, root, tip, joints=True, links=True, fixed=True):
        chain = []
        if links:
            chain.append(str(tip))
        link = str(tip)
        assert self.get_link(root) is not None
        assert self.get_link(link) is not None
        while str(link) != str(root):
            (joint, parent) = self.parent_map[link]
            if joints:
                if fixed or self.get_joint(joint).joint_type != 'fixed':
                    chain.append(joint)
            if links:
                chain.append(parent)
            link = parent
        chain.reverse()
        return chain

    def get_root(self):
        root = None
        for link in self.links:
            if link.name not in self.parent_map:
                assert root is None, f"Multiple roots detected, invalid URDF. Already found: {root.name, link.name}"
                root = link
        assert root is not None, "No roots detected, invalid URDF."
        return root

    def get_aggregate(self, targettype, target, verbose=False):
        """
        Returns the id of the given instance
        :param targettype: the tye of the searched instance
        :param target: the name of the searched instance
        :return: the id or None if not found
        """
        if type(target) == list:
            return [self.get_aggregate(targettype, str(t)) for t in target]
        names = []
        if not targettype.endswith("s"):
            targettype += "s"
        for obj in getattr(self, targettype):
            names.append(str(obj))
            if str(obj) == str(target):
                return obj
        if verbose:
            print(f"Robot {self.name} has no {targettype} with name {target}, only these: {repr(names)}")
        return None

    def get_link(self, link_name, verbose=True) -> [representation.Link, list]:
        """
        Returns the link(s) corresponding to the link name(s).
        :param link_name: the name of the joint to get
        :return: the link instance, None if not found
        """
        if isinstance(link_name, representation.Link):
            return link_name
        if isinstance(link_name, list):
            return [self.get_link(lname) for lname in link_name]

        return self.get_aggregate("link", link_name, verbose=verbose)

    def get_joint(self, joint_name, verbose=False) -> [representation.Joint, list]:
        """
        Returns the joint(s) corresponding to the joint name(s).
        :param joint_name: the name of the joint to get
        :return: the joint instance, None if not found
        """
        if isinstance(joint_name, representation.Joint):
            return joint_name
        if isinstance(joint_name, list):
            return [self.get_joint(jname) for jname in joint_name]

        return self.get_aggregate("joint", joint_name, verbose=verbose)

    def get_sensor(self, sensor_name) -> [sensor_representations.Sensor, list]:
        """Returns the ID (index in the sensor list) of the sensor(s).
        """
        if isinstance(sensor_name, list):
            return [self.get_sensor(sensor) for sensor in sensor_name]

        return self.get_aggregate('sensors', sensor_name)

    def get_inertial(self, link_name):
        """
        Returns the inertial of the given link.
        :param link_name: the name of the respective link
        :return: the inertial of the given link
        """
        link_id = self.get_link_id(link_name)

        if link_id is None:
            return None

        return self.links[link_id].inertial

    def get_visual(self, link_name):
        """
        Return all visuals of the given link if it exists.
        :param link_name: the name of the respective link
        :return: list of visuals of the given link, if there are else none
        """
        link_id = self.get_link_id(link_name)

        if link_id is None:
            return None

        if self.links[link_id].visuals:
            return self.links[link_id].visuals
        else:
            return None

    def get_all_visuals(self):
        visuals = []
        for link in self.links:
            visuals += link.visuals
        return visuals

    def get_visual_by_name(self, visual_name):
        """
        Returns the visual with the given name if it exists
        :param visual_name: name of the searched visual
        :return: the found visual or none
        """
        if isinstance(visual_name, representation.Visual):
            return visual_name
        for link in self.links:
            for vis in link.visuals:
                if vis.name == visual_name:
                    return vis

        return None

    def get_collision(self, link_name):
        """
        Return all collisions of the given link if it exists.
        :param link_name: the name of the respective link
        :return: list of collisions of the given link, if there are else none
        """
        link_id = self.get_link_id(link_name)

        if link_id is None:
            return None

        if self.links[link_id].collisions:
            return self.links[link_id].collisions
        else:
            return None

    def get_all_collisions(self):
        collisions = []
        for link in self.links:
            collisions += link.collisions
        return collisions

    def get_collision_by_name(self, collision_name):
        """
        Returns the collision with the given name if it exists
        :param collision_name: name of the searched collision
        :return: the found collision or none
        """
        if isinstance(collision_name, representation.Collision):
            return collision_name
        for link in self.links:
            for coll in link.collisions:
                if coll.name == collision_name:
                    return coll

        return None

    def get_id(self, targettype, target):
        """
        Returns the id of the given instance
        :param targettype: the tye of the searched instance
        :param target: the name of the searched instance
        :return: the id or None if not found
        """
        for i, obj in enumerate(getattr(self, targettype)):
            if obj.name == target:
                return i
        return None

    def get_joint_id(self, joint_name):
        """
        Returns the ID (index in the joint list) of the joint.
        :param joint_name: the name of the joint to search
        :return: the Id if found else None
        """
        if isinstance(joint_name, list):
            return [self.get_id('joints', name) for name in joint_name]

        return self.get_id('joints', joint_name)

    def get_link_id(self, link_name):
        """
        Returns the ID (index in the link list) of the link.
        :param link_name: the name of the link to search
        :return: the Id if found else None
        """
        if isinstance(link_name, list):
            return [self.get_id('links', name) for name in link_name]

        return self.get_id('links', link_name)

    def get_joint_level(self, jointname):
        """
        Returns the depth of the given joint in the robots kinematic tree
        """
        joint = self.get_joint(jointname)
        return self.get_link_level(joint.parent)

    def get_link_level(self, linkname):
        """
        Returns the depth of the given link in the robots kinematic tree
        """
        parent = self.get_parent(linkname)
        level = 0
        while parent is not None:
            joint = self.get_joint(parent[0])
            parent = self.get_parent(joint.parent)
            level += 1
        return level

    def get_joints_ordered_df(self):
        """Returns the joints in depth first order"""
        return get_joints_depth_first(self, self.get_root())

    def get_links_ordered_df(self):
        """Returns the joints in depth first order"""
        joints = self.get_joints_ordered_df()
        out = [self.get_root()] + [jn.child for jn in joints]
        return [self.get_link(ln) for ln in out]

    def get_material(self, material_name):
        """
        Returns the collision with the given name if it exists
        :param material_name: name of the searched collision
        :return: the found collision or none
        """
        if isinstance(material_name, representation.Material):
            return material_name
        for mat in self.materials:
            if mat.name == material_name:
                return mat

        return None

    def get_parent(self, name, targettype='joint'):
        """
        Get the parent of targettype for the given link name.
        :param name: the name of the link to get the parent for
        :param targettype: the next parent joint or the next parent link (default: 'joint')
        :return: List with one element (todo)
        """
        # Check if the name is present
        if name in self.parent_map.keys():
            parents = self.parent_map[name]
        elif name in self.child_map.keys():
            return None
        else:
            print("Parent map keys: ", self.parent_map.keys())
            raise AssertionError("Nothing with name " + name + " in this robot")

        # Parentmap contains links.
        # If we want joints, then collect the children of these
        assert parents is not None
        if targettype == "link":
            return [parents[1]]
        if targettype == 'joint':
            return [parents[0]]

        return parents

    def get_children(self, name, targettype='joint'):
        """
        Get the children of type targettype for the given link name.
        :param name: the name of the parent link
        :param targettype: whether we want the next joint children or link childrne
        :return: list of children of the given link
        """
        if isinstance(name, list):
            children = []
            for n in name:
                new_children = self.get_children(n, targettype=targettype)
                children += new_children if new_children else []
            return children

        children = []

        if name in self.child_map.keys():
            children = self.child_map[name]

        if children:
            if targettype == 'joint':
                children = [i[0] for i in children]
            elif targettype == 'link':
                children = [i[1] for i in children]

        return children

    def get_leaves(self, start=None):
        """
        Get all leaves of the given start link.
        If start is provided, returns leaves of the sub tree
        :param start: the root link for which to get the leaves
        :return:
        """
        all_leaves = [link for link in self.links if str(link) not in self.child_map.keys()]
        if start is None:
            return all_leaves

        chains_to_leave = {str(leave): [str(link) for link in self.get_chain(self.get_root(), leave, joints=False)] for leave in all_leaves}

        return [leave for leave, chain in chains_to_leave.items() if str(start) in chain]

    def get_transformation(self, end, start=None):
        """
        Returns the transformation from start to end
        :param end: the end link of the transformation
        :param start: the start link of the transformation (default is root)
        :return: the transformation matrix
        """
        if start is None:
            start = self.get_root()
        transformation = create_transformation((0, 0, 0), (0, 0, 0))

        link = str(end)
        while link != str(start):
            parent = self.get_parent(link)
            if parent is not None and len(parent) > 1:
                print("Multiple parents:", parent, flush=True)
            elif parent is None:
                raise Exception(link, "has no parent, but is different from start", start)
            pjoint = self.get_joint(parent[0])
            transformation = create_transformation(pjoint.origin.xyz, pjoint.origin.rpy).dot(transformation)
            link = str(pjoint.parent)

        return transformation

    def global_origin(self, stop):
        """ Get the global pose of the link.
        """
        return representation.Pose.from_matrix(self.get_transformation(stop))

    def post_read_xml(self):
        """Version and validity check"""
        if self.version is None:
            self.version = "1.0"

        split = self.version.split(".")
        if len(split) != 2:
            raise ValueError("The version attribute should be in the form 'x.y'")

        if split[0] == '' or split[1] == '':
            raise ValueError("Empty major or minor number is not allowed")

        if int(split[0]) < 0 or int(split[1]) < 0:
            raise ValueError("Version number must be positive")

        if self.version not in self.SUPPORTED_VERSIONS:
            raise ValueError("Invalid version; only %s is supported" % (','.join(self.SUPPORTED_VERSIONS)))


xml_factory.class_factory(XMLRobot)