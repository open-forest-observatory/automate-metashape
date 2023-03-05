# Function to take a directory of images and normalize their intensities, saving the normalized images in a new directory named {input_dir}_normalized

library(magick)
library(stringr)
library(furrr)

# Function for a single image, to parallelize across within a directory of images
normalize_one_img = function(img_file, img_dir, out_dir) {
  
  # get the relative path below the specified folder (for saving in same folder structure within the "..._normalized" folder)
  rel_path = str_replace(img_file, pattern = fixed(img_dir), replacement = "")
  
  out_file = file.path(out_dir, rel_path)
  
  # if already computed for this image, skip
  if(file.exists(out_file)) return(FALSE)
  
  img = image_read(img_file)
  
  img_norm = image_normalize(img)

  # create dir if doesn't exist
  out_dir_img = dirname(out_file)
  if(!dir.exists(out_dir_img)) dir.create(out_dir_img, recursive = TRUE)
  
  image_write(img_norm, out_file)
  
  gc()
  
}


# Function to parallelize across images in a directory
normalize_images_in_dir = function(img_dir) {

  # What string to append to the input directory name to store the normalized images
  out_dir = paste0(img_dir, "_normalized")
  if(!dir.exists(out_dir)) dir.create(out_dir, recursive=TRUE)
  
  img_files = list.files(img_dir, pattern = "(JPG|jpg|tif|TIF)$", recursive = TRUE, full.names = TRUE)
  
  gc()
  
  plan(multisession)
  
  future_walk(img_files, normalize_one_img, img_dir = img_dir, out_dir = out_dir)

}
