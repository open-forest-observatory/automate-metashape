### Author: Derek Young, UC Davis

### This script does the following:
### - Takes a base config YAML template and a set of alternate (derived) parameter values (partial YAMLs that only specify the parameters to change) and composes a set of config files to run in the metashape workflow)

library(yaml)
library(readr)
library(stringr)

#### Determine paths and read YAML files ####

# If running manually, specify path to base and derived YAML templates
manual_yaml_path = "/storage/forestuav/configs/set26"
# also the path to metashape repo (this is used only in building the batch job script -- for the call to metashape)
manual_metashape_path = "~/Documents/projects/metashape/python/metashape_workflow.py"

## read paths from command line argument (otherwise use the hard-coded defaults above)
command_args = commandArgs(trailingOnly=TRUE)

if(length(command_args) == 0) {
  yaml_path = manual_yaml_path
  metashape_path = manual_metashape_path
} else if (length(command_args) == 1) {
  yaml_path = command_args[1]
} else {
  metashape_path = command_args[2]
  yaml_path = command_args[1]
}

## Read YAML files
base_yaml_path = paste0(yaml_path,"/","base.yml")
derived_yaml_path = paste0(yaml_path,"/","derived.yml")

base = read_yaml(base_yaml_path)

# read derived config lines as vector
derived_data = read_lines(derived_yaml_path, skip_empty_rows = TRUE)



#### Store each derived set as a separate R object (interpreted from YAML) ####

# remove newlines at start of each line
derived_data = str_replace(derived_data,"^\n","")

# search for vector elements (lines) that indicate the start of a derived parameter set
start_rows = grep("^####CONFIG", derived_data)

# Vector to store config file locations to create a shell script
config_files = NULL

# For each derived parameter set, replace the base parameters with the provided derived parameters, and write a config file
for(i in 1:length(start_rows)) {

  # get first line of the current derived parameter set
  first_line = start_rows[i] + 1

  # get last line of the current derived parameter set
  if(i != length(start_rows)) {
    last_line = start_rows[i+1] - 1
  } else {
    last_line = length(derived_data)
  }


  ## save as R object
  yaml_string = paste(derived_data[first_line:last_line],collapse="\n")
  derived_focal = yaml.load(yaml_string)

  ## take the template and replace each element specified in the derived with the value specified in the derived
  base_derived = modifyList(base,derived_focal)


  ## get the number (ID) of the derived set (just use the run name from the YAML)
  id = base_derived$run_name

  ## write the derived set with its ID number
  filename = paste0(yaml_path,"/cfg_",id,".yml")

  write_yaml(base_derived,filename)

  config_files = c(config_files,filename)


}


## make a shell script to run all the config files (assume WD is the metashape repo)
shell_lines = paste0("python ", metashape_path, " ", config_files)

writeLines(shell_lines,
            con = paste0(yaml_path,"/config_batch.sh"), sep="\n")
