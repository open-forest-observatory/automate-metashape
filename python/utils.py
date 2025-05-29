import yaml
import collections.abc
from pathlib import Path


def recursive_update(d, u):
    """ "
    Recursively update dictionary `d` with any keys from `u`. New keys contained in `u` but not in `d`
    will be created.

    Taken from: https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
    """
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = recursive_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def make_derived_yaml(input_path: str, output_path: str, override_options: dict):
    """Create a new config file by reading one file and updating specific values

    Args:
        input_path (str):
            The path to the yaml config file to load from
        output_path (str):
            The path to the yaml config file to write out. Containing folder will be created if needed.
        override_options (dict):
            A potentially-nested dictionary
    """
    # Read the input config
    with open(input_path, "r") as ymlfile:
        base_cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

    # Update the values in the base config
    updated_config = recursive_update(base_cfg, override_options)

    # Create the output folder if needed
    Path(output_path).parent.mkdir(exist_ok=True, parents=True)

    # Write out the updated config
    with open(output_path, "w") as ymlfile:
        # Preserve the initial order of keys for readability
        yaml.dump(updated_config, ymlfile, sort_keys=False)
