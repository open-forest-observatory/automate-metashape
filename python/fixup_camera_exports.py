import argparse
import os
import typing
import xml.etree.ElementTree as ET
from glob import glob
from pathlib import Path

from tqdm import tqdm

FIXUP_ACTIONS = (
    "common_root",
    "relabel_from_DVC",
    "grouped",
    "old_multi_folder",
    "ensure_images_exists",
)

PATH_TYPE = typing.Union[Path, str]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-camera-file",
        type=Path,
        help="Path to the camera file to be fixed. This is exported by Metashape and ends in a .xml extension",
    )
    parser.add_argument(
        "--output-camera-file",
        type=Path,
        help="Path to save updated file to. If the same as the --input-camera-file, the input will be overwritten.",
    )
    parser.add_argument(
        "--input-image-folder",
        type=Path,
        help="Path to the folder of images that Metashape was run on.",
    )
    parser.add_argument(
        "--input-image-folder-grouped",
        type=Path,
        help="Only applicable with the `grouped` action. The path to images which were added as one group. Applicable to older metashape workflows.",
    )
    parser.add_argument(
        "--action",
        choices=FIXUP_ACTIONS,
        default="common_root",
        help="Which workflow to run.",
    )

    args = parser.parse_args()
    return args


def fix_grouped(
    input_camera_file: PATH_TYPE,
    input_image_folder_grouped: PATH_TYPE,
    input_image_folder_ungrouped: PATH_TYPE,
    output_camera_file: PATH_TYPE,
):
    tree = ET.parse(input_camera_file)
    cameras = tree.getroot().find("chunk").find("cameras")

    all_two_deep_folders = sorted(
        [f for f in Path(input_image_folder_grouped).glob("*/*") if f.is_dir()]
        + [f for f in Path(input_image_folder_grouped).glob("*Patch*") if f.is_dir()]
    )

    group_ind = 0

    for camera_or_group in cameras:
        if camera_or_group.tag == "group":
            label_folder = all_two_deep_folders[group_ind]
            if camera_or_group.get("label") != label_folder.parts[-1]:
                breakpoint()
                raise ValueError()

            for camera in camera_or_group:
                camera_name = camera.get("label")
                camera_path = Path(label_folder, camera_name)
                updated_path_matching = list(
                    camera_path.parent.glob(camera_path.name + "*")
                )
                if len(updated_path_matching) != 1:
                    breakpoint()
                    raise ValueError()
                updated_path = updated_path_matching[0]
                camera.set("label", str(updated_path))

            group_ind += 1
        else:
            camera_path = Path(
                input_image_folder_ungrouped, camera_or_group.get("label")
            )
            updated_path = next(camera_path.parent.glob(camera_path.name + "*"))
            camera_or_group.set("label", str(updated_path))

    Path(output_camera_file).parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_camera_file)


def fix_old_multi_folder(
    input_camera_file: PATH_TYPE,
    input_image_folder: PATH_TYPE,
    output_camera_file: PATH_TYPE,
):
    tree = ET.parse(input_camera_file)
    cameras = tree.getroot().find("chunk").find("cameras")
    labels = [camera.get("label") for camera in cameras]
    aboslute_filename_labels = fixup(labels, input_image_folder)

    # TODO make sure that the cameras iterator isn't used up
    for camera, afl in zip(cameras, aboslute_filename_labels):
        old_label = camera.get("label")
        camera.set("label", str(afl))
        print(f"Changing {old_label} to {str(afl)}")

    Path(output_camera_file).parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_camera_file)


def fixup(
    camera_labels,
    image_folder: PATH_TYPE,
    exclude_str=None,
    validate_existance: bool = True,
):
    # These ones were absolute, just the leading slash was incorrectly removed
    absolute_filenames = [
        "/" + str(camera_label)
        for camera_label in camera_labels
        if camera_label.split("/")[0] == "ofo-share"
    ]

    absolute_camera_labels = []

    # Run through all of them and fixup
    for camera_label in tqdm(camera_labels, desc="Fixing up camera paths"):
        # The path is absolute, add it with the leading slash
        if camera_label.split("/")[0] == "ofo-share":
            absolute_camera_labels.append(Path("/", camera_label))
        # The path isn't absolute, we need to find the corresponding file
        else:
            # We need to recursively search the imagery folder for this label
            search_str = str(Path(image_folder, "**", camera_label))
            # Get the list of matching files
            # TODO it might be possible to speed this up by building a list of all files once,
            # then finding the matching subset at each iteration
            matching_files = glob(search_str, recursive=True)

            # WARNING, absolute_filenames and matching_files must be the same type, (str vs. Path)
            not_already_used_files = list(
                filter(lambda f: f not in absolute_filenames, matching_files)
            )

            # If there's a folder you know you want to exclude
            # TODO make this more robust, like a regex
            if exclude_str is not None:
                not_already_used_files = list(
                    filter(lambda f: exclude_str not in f, not_already_used_files)
                )

            if len(not_already_used_files) != 1:
                print(not_already_used_files)
                raise ValueError(
                    f"Bad match for {search_str} resulted in {len(not_already_used_files)} files"
                )
            absolute_camera_labels.append(not_already_used_files[0])
    # Transform to paths
    absolute_camera_labels = list(map(Path, absolute_camera_labels))

    if validate_existance:
        for acl in absolute_camera_labels:
            if not acl.is_file():
                raise ValueError(f"File {acl} doesn't exist")

    return absolute_camera_labels


def ensure_file_exists(
    input_camera_file: PATH_TYPE, output_camera_file: PATH_TYPE, image_folder: PATH_TYPE
):
    tree = ET.parse(input_camera_file)
    root = tree.getroot()
    cameras = root.find("chunk").find("cameras")
    for cam_or_group in cameras:
        if cam_or_group.tag == "group":
            for cam in cam_or_group:
                if not Path(image_folder, cam.get("label")).exists():
                    cam_or_group.remove(cam)

        else:
            cam = cam_or_group
            if not Path(image_folder, cam.get("label")).exists():
                cameras.remove(cam)

    tree.write(output_camera_file)


def make_relative_to_common_root(
    input_camera_file: PATH_TYPE, output_camera_file: PATH_TYPE
):
    """Update labels to be relative to the common root of all filepaths

    Args:
        input_camera_file (PATH_TYPE): Path to input camera file
        output_camera_file (PATH_TYPE): Path to write modified camera file to
    """
    # Load the xml file
    tree = ET.parse(input_camera_file)
    # Get the cameras object
    cameras = tree.getroot().find("chunk").find("cameras")

    # Get the list of old labels
    old_labels = []
    # Iterate over all items in the cameras object
    for cam_or_chunk in cameras:
        # They may either be a camera or a group of cameras
        if cam_or_chunk.tag == "group":
            # If it's a group, we know it's only one level deep, so iterate over the individual camera elements
            for cam in cam_or_chunk:
                old_labels.append(cam.get("label"))
        else:
            # Otherwise, it's a camera so we can directly get the label
            old_labels.append(cam_or_chunk.get("label"))

    # Determine the common folder of all the labels.
    # TODO determine what happens if there is no common root. I suspect it will leave everything as-is
    # which seems like reasonable behavior.
    common_folder = Path(os.path.commonpath(old_labels))

    # Convenience function to update the label based on the common root
    # This updates the label in place to be relative to the common root
    def update_label(cam, common_folder):
        old_label = Path(cam.get("label"))
        new_label = str(old_label.relative_to(common_folder))
        cam.set("label", new_label)

    # Iterate over all of the camera to update the label
    for cam_or_chunk in cameras:
        # Same logic as before, some elements may actually be a group of cameras
        if cam_or_chunk.tag == "group":
            # Group, so iterate over elements
            for cam in cam_or_chunk:
                update_label(cam=cam, common_folder=common_folder)
        else:
            # Camera, so use directly
            update_label(cam=cam_or_chunk, common_folder=common_folder)

    # Since the tree was updated in-place, we can just write it out
    tree.write(output_camera_file)


def build_dvc_to_raw_dict(image_folder: PATH_TYPE, extension: str = "JPG"):
    files = list(image_folder.rglob("**/*" + extension))
    points_to = [os.path.realpath(file) for file in files]
    mapping_dict = {p: str(f) for p, f in zip(points_to, files)}
    return mapping_dict


def relabel_from_DVC(
    input_camera_file: PATH_TYPE,
    input_image_folder: PATH_TYPE,
    output_camera_file: PATH_TYPE,
):
    mapping_dict = build_dvc_to_raw_dict(input_image_folder)
    tree = ET.parse(input_camera_file)
    cameras = tree.getroot().find("chunk").find("cameras")
    for camera in cameras:
        old_label = camera.get("label")
        new_label = mapping_dict[old_label]
        camera.set("label", new_label)

    tree.write(output_camera_file)


if __name__ == "__main__":
    # Parse args
    args = parse_args()
    # Extract action for convenience
    action = args.action

    # Determine which workflow to run
    if action == "common_root":
        # Make all labels relative to the common root. Useful for turning absolute filepaths into
        # relative paths which are more portable.
        make_relative_to_common_root(
            args.input_camera_file,
            args.output_camera_file,
        )
    elif action == "grouped":
        fix_grouped(
            args.input_camera_file,
            args.input_image_folder_grouped,
            args.input_image_folder_ungrouped,
            args.output_camera_file,
        )
    elif action == "old_style":
        fix_old_multi_folder(
            args.input_camera_file,
            args.input_image_folder,
            args.output_camera_file,
        )
    elif action == "relabel_from_DVC":
        relabel_from_DVC(
            args.input_camera_file, args.input_image_folder, args.output_camera_file
        )
    elif action == "old_multi_folder":
        fix_old_multi_folder(
            args.input_camera_file, args.input_image_folder, args.output_camera_file
        )
    elif action == "ensure_images_exists":
        ensure_file_exists(
            input_camera_file=args.input_camera_file,
            output_camera_file=args.output_camera_file,
            image_folder=args.input_image_folder,
        )
    else:
        raise ValueError(f"Action {action} not supported")
