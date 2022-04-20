from scipy.spatial.transform import Rotation as Rot
import numpy as np

from ..defs import EULER_CONVENTION, RPY_CONVENTION
from ..io import representation


def matrix_to_quaternion(rotation):
    return Rot.from_matrix(rotation).as_quat()


def quaternion_to_matrix(quat):
    return Rot.from_quat(quat).as_matrix()


def rpy_to_quaternion(rotation):
    return Rot.from_euler(EULER_CONVENTION, rotation).as_quat()


def quaternion_to_rpy(quaternion):
    angles = Rot.from_quat(quaternion).as_euler(EULER_CONVENTION)
    return order_angles(angles, EULER_CONVENTION, RPY_CONVENTION)


def rpy_to_matrix(rpy):
    euler = order_angles(rpy, RPY_CONVENTION, EULER_CONVENTION)
    return Rot.from_euler(EULER_CONVENTION, euler).as_matrix()


def matrix_to_rpy(R):
    angles = Rot.from_matrix(R).as_euler(EULER_CONVENTION)
    return order_angles(angles, EULER_CONVENTION, RPY_CONVENTION)


def skew_symmetric(x):
    return np.array([[0, -x[2], -x[1]], [x[2], 0, -x[0]], [-x[1], x[0], 0]])


def origin_to_homogeneous(origin):
    R = rpy_to_matrix(origin.rpy if hasattr(origin, "rpy") else [0.0, 0.0, 0.0])
    p = np.array(origin.xyz if hasattr(origin, "xyz") else [0.0, 0.0, 0.0])
    T = np.identity(4)
    T[0:3, 3] = p
    T[0:3, 0:3] = R
    T[3, 3] = 1.0
    return T


def order_angles(angles, in_order, out_order):
    axes = {"x": angles[in_order.lower().index("x")], "y": angles[in_order.lower().index("y")],
            "z": angles[in_order.lower().index("z")]}
    return [axes[k] for k in out_order.lower()]


def to_origin(T, dec=6):
    xyz = T[0:3, 3]
    rpy = matrix_to_rpy(T[0:3, 0:3])
    return representation.Pose(xyz=round_array(xyz, dec=dec), rpy=round_array(rpy, dec=dec))


def round_array(array, dec):
    out = []
    for x in array:
        if 1*10**-(dec+1) > x > -1*10**-(dec+1):
            out.append(0.0)
        else:
            out.append(x)
    return np.around(out, decimals=dec)


def Homogeneous(xyz=None, rpy=None):
    assert xyz is not None or rpy is not None
    if rpy is None:
        rpy = [0, 0, 0]
    if xyz is None:
        xyz = [0, 0, 0]
    R = rpy_to_matrix(rpy)
    p = np.array(xyz)
    T = np.zeros((4, 4))
    T[0:3, 3] = p
    T[0:3, 0:3] = R
    T[3, 3] = 1.0
    return T


def inv(T):
    return np.linalg.inv(T)


def Adjoint(T):
    assert isinstance(T, representation.Pose) or isinstance(T, np.ndarray)
    if isinstance(T, representation.Pose):
        R = rpy_to_matrix(T.rpy)
        P = skew_symmetric(np.array(T.xyz))
    else:  # isinstance(T, np.ndarray):
        R = T[0:3, 0:3]
        P = skew_symmetric(T[0:3, 3])
    Ad = np.zeros((6, 6))
    Ad[0:3, 0:3] = R
    Ad[3::, 0:3] = np.dot(P, R)
    Ad[3::, 3::] = R
    return Ad