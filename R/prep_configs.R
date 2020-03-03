### Author: Derek Young, UC Davis

### This script does the following:
### - Takes a base config YAML template and a set of alternate (derived) parameter values (partial YAMLs that only specify the parameters to change) and composes a set of config files to run in the metashape workflow)

library(tidyverse)
library(yaml)

#### Determine paths and read YAML files ####

# If running manually, specify path to base and derived YAML templates
manual_path = "C:/Users/DYoung/Documents/projects/metashape/temp_dev"

path = manual_path
## TODO: read path from command line argument

base_yaml_path = paste0(manual_path,"/","base.yml")
derived_yaml_path = paste0(manual_path,"/","derived.yml")

base = read_yaml(base_yaml_path)

# read derived confit lines as vector
derived_data = read_lines(derived_yaml_path, skip_empty_rows = TRUE)



#### Store each derived set as a separate R object (interpreted from YAML) ####

# remove newlines at start of each line
derived_data = str_replace(derived_data,"^\n","")

# search for vector elements (lines) that indicate the start of a derived parameter set
start_rows = grep("^####CONFIG_", derived_data)

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
  for(i in 1:length(derived_focal))
  
  
}



## R need to look up how to overwrite only parts of an object. Could do with function below but only if the list object were mutable.








replace = function(base,derived) {
  
  for(i in 1:length(derived)) {
    
    param = names(derived[i])
    
    if(names(derived[i] == names(derived[[i]]))) { ## if we're at the bottom layer
      
      
      
      
      
    }
    value = derived[i]
    
    
    
    
  }
  
  
  
  
  
  
}









derived = read_yaml(derived_yaml_path)












