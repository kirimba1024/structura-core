"""Euclidean morphology for voxel masks."""
from scipy import ndimage


def dilation(mask, radius):
    return mask.copy() if radius <= 0 else ndimage.distance_transform_edt(~mask) <= radius


def erosion(mask, radius):
    return mask.copy() if radius <= 0 else ndimage.distance_transform_edt(mask) > radius


def closing(mask, radius):
    return erosion(dilation(mask, radius), radius)


def signed_distance(mask):
    return ndimage.distance_transform_edt(~mask) - ndimage.distance_transform_edt(mask)
