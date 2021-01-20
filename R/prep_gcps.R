### Author: Derek Young, UC Davis

### This script does the following:
### - Loads a user-created data file of the image files (and coordinates in each image) where GCPs are located
### - Loads a geospatial file containing the locations of the GCPs
### - Loads a 10 m DEM and extracts elevation values at each GCP
### - Compiles all of the above into a file needed by Metashape for its GCP workflow
### - Produces a PDF that shows each GCP image and the location of the GCP for QAQC


### This script requires the following folders/files in the main mission imagery directory (the one containing 100MEDIA etc):
### - gcps/raw/gcps.gpkg : geospatial data file with each gcp id in the column "gcp_id". Must be in the same projection as the whole Metashape project, and must be in meters xy (usually a UTM zone).
### - gcps/raw/gcp_imagecoords.csv : data file listing the images and coordinates in each where a GCP is visible (created manually by technician via imagery inspection)
### - dem_usgs/dem_usgs.tif : 10 m USGS dem extending well beyond the project flight area

### This script assumes all images to be linked to GCPs have standard DJI naming and directory structure ("100MEDIA/DJI_xxxx.JPG").
### In input data file gcp_imagecoords.csv, images are specified without "DJI_", leading zeros, and ".JPG". The image directory is specified without "MEDIA"


#### Load packages ####

library(sf)
library(raster)
library(dplyr)
library(stringr)
library(magick)
library(ggplot2)

#### User-defined vars (only used when running interactivesly) ####

dir_manual = "/home/derek/Downloads/crater_gcps"



#### Load data ####

### All relevant GCP data should be in the top-level mission imagery folder
### Load folder from the command line argument


dir = commandArgs(trailingOnly=TRUE)

if(length(dir) == 0) {
  dir = dir_manual
}

gcps = read_sf(paste0(dir,"/gcps/raw/gcps.geojson"))
imagecoords = read.csv(paste0(dir,"/gcps/raw/gcp_imagecoords.csv"),header=TRUE,stringsAsFactors=FALSE)
dem_usgs = raster(paste0(dir,"/dem_usgs/dem_usgs.tif"))

# remove blank lines from image coords file
imagecoords = imagecoords %>%
  filter(!is.na(x))


#### Make prepared data directory if it doesn't ecist ####
dir.create(paste0(dir,"/gcps/prepared"),showWarnings=FALSE)



#### Create GCP table in the format required by metashape_control and metashape_functions ####

# Extract elev
gcp_table = gcps
gcp_table$elev = suppressWarnings(extract(dem_usgs,gcp_table,method="bilinear"))

# Extract coords
coords = st_coordinates(gcp_table)
gcp_table = cbind(gcp_table,coords)

# Remove geospatial info
st_geometry(gcp_table) = NULL

# Reorder columns, add "point" prefix to GCP names
gcp_table = gcp_table %>%
  dplyr::select(gcp_id,x=X,y=Y,elev) %>%
  dplyr::mutate(gcp_id = paste0("point",gcp_id))
  
write.table(gcp_table,paste0(dir,"/gcps/prepared/gcp_table.csv"),row.names=FALSE,col.names=FALSE,sep=",")


#### Create image coordinate-to-gcp table in the format required by metashape_control and metashape_functions ####

imagecoords_table = imagecoords %>%
  mutate(gcp_id = paste0("point",gcp)) %>%
  mutate(image_text = paste0("DJI_",str_pad(image_file,4,pad="0"),".JPG")) %>%
  mutate(part_text = paste0("PART_",str_pad(part_folder,2,pad="0"))) %>%
  mutate(folder_text = paste0(media_folder,"MEDIA")) %>%
  mutate(image_path = paste0(part_text,"/",folder_text,"/",image_text)) %>%
  dplyr::select(gcp_id,image_path,x,y) %>%
  arrange(gcp_id,image_path)

# remove blank lines from image coords file
imagecoords = imagecoords %>%
  filter(!is.na(gcp))


write.table(imagecoords_table,paste0(dir,"/gcps/prepared/gcp_imagecoords_table.csv"),row.names=FALSE,col.names=FALSE,sep=",")


#### Export a PDF of images with the GCP circled on each ####


pdf(paste0(dir,"/gcps/prepared/gcp_qaqc.pdf"))

for(i in 1:nrow(imagecoords_table)) {
  
  imagecoords_row = imagecoords_table[i,]
  
  img = image_read(paste0(dir,"/",imagecoords_row$image_path))
  img = image_scale(img,"10%")
  img = image_flip(img)
  
  img_x = imagecoords_row$x/10
  img_y = imagecoords_row$y/10
  img_gcp = imagecoords_row$gcp_id
  img_path = imagecoords_row$image_path
  
  map = image_ggplot(img) +
    geom_point(x=img_x,y=img_y,size=20,pch=1,fill=NA,color="red",stroke=1) +
    geom_point(x=img_x,y=img_y,size=20,pch=3,fill=NA,color="red",stroke=0.5) +
    labs(title=paste0(img_gcp,"\n",img_path))

  print(map)
  
  cat("Completed GCP ", i, " of ",nrow(imagecoords_table),"\r")
  
}

garbage = dev.off()



