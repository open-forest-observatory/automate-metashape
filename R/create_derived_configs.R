# Take a base YML and a data frame with alternate values (one per row) for a specific key in the base YML and make all the derived YMLs
# Currently, this just works for (any) single key, which must be in the top level of the YML hierarchy.

library(yaml)
library(here)
library(dplyr)

# Function to take a base config with default values and a data frame of replacement values for one or more keys and create a derived config file using those replacements (one derived config file per row of the data frame).

# `base_cfg_path`: Path to the base config file that will be updated with value replacements

# `save_dir`: Directory to save the derived config files to

# `replacements`: Replacement data frame. First col ("name") will be the filename (sans extension) of the derived YML. The remaining cols are the YML keys to replace the values for.
# Each row will translate to a different derived YML.
# Each row of the DF must contain a name (for the resulting yml file) and at elast one YML key to replace the values of.

create_derived_configs = function(base_cfg_path, save_dir, replacements) {
    
    #### Prep
    
    # Read base YML
    base_config = read_yaml(base_cfg_path)
    
    # Create output dir
    if(!dir.exists(save_dir)) dir.create(save_dir, recursive = TRUE)
    
    
    #### Run
    # For each row of the replacements, replace the specified keys (col names) with the specified values and save a derived YML
    
    for(i in 1:nrow(replacements)) {
      
        replacement = replacements[i, ]
        
        derived_filename = paste0(replacement$name, ".yml")
        replacement_keysvals = replacement |> select(-name)
        
        derived_config = base_config
        
        for(j in 1:ncol(replacement_keysvals)) {
          
          replacement_key = colnames(replacement_keysvals)[j]
          replacement_val = replacement_keysvals[, j]
          derived_config[replacement_key] = replacement_val
          
        }
    
        write_yaml(derived_config, file.path(save_dir, derived_filename))
      
    }
}
