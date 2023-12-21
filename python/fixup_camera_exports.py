import argparse
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from tqdm import tqdm
from glob import glob


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_camera_file", type=Path)
    parser.add_argument("input_image_folder", type=Path)
    parser.add_argument("output_camera_file", type=Path)
    parser.add_argument(
        "--fix-old-style",
        action="store_true",
        help="Fixup style where some are absolute and others aren't",
    )

    args = parser.parse_args()
    return args


def fix_old_multi_folder(input_camera_file, input_image_folder, output_camera_file):
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


def fixup(camera_labels, image_folder, exclude_str=None, validate_existance=True):
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
                    f"Bad match for {search_str} resulted in {len(selected_files)} files"
                )
            absolute_camera_labels.append(not_already_used_files[0])
    # Transform to paths
    absolute_camera_labels = list(map(Path, absolute_camera_labels))

    if validate_existance:
        for acl in absolute_camera_labels:
            if not acl.is_file():
                raise ValueError(f"File {acl} doesn't exist")

    return absolute_camera_labels


def build_dvc_to_raw_dict(image_folder: Path, extension="JPG"):
    files = list(image_folder.rglob("**/*" + extension))
    points_to = [os.path.realpath(file) for file in files]
    mapping_dict = {p: str(f) for p, f in zip(points_to, files)}
    return mapping_dict


def main(input_camera_file, input_image_folder, output_camera_file):
    mapping_dict = build_dvc_to_raw_dict(input_image_folder)
    tree = ET.parse(input_camera_file)
    cameras = tree.getroot().find("chunk").find("cameras")
    for camera in cameras:
        old_label = camera.get("label")
        new_label = mapping_dict[old_label]
        camera.set("label", new_label)

    tree.write(output_camera_file)


if __name__ == "__main__":
    args = parse_args()

    if args.fix_old_style:
        fix_old_multi_folder(
            args.input_camera_file,
            args.input_image_folder,
            args.output_camera_file,
        )
    else:
        main(args.input_camera_file, args.input_image_folder, args.output_camera_file)
