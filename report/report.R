# Summarize the Agisoft Metashape Benchmark Data
# TODO: Convert to use current benchmark file format
# TODO: Convert to an Rmarkdown for nicely formatted reports

library(plyr)
library(dplyr)

#### Functions ####

subset_results <- function(i, index, txt){
  # split into chunks
  subtxt <- txt[index[i,][1]:index[i,][2],]
  
  return(subtxt)
}

make_index <- function(starts, end) {
  # Given the start of sections and the total size of data, create an index of chunks
  ends <- c((starts-1)[2:length(starts)], (end))
  index <- cbind(starts, ends)
  
  return(index)
}

tdf <- function(dfv) {
  # Tranpose a dataframe taking col 1 as the colnames
  dfh <- as.data.frame(t(dfv[,2]), stringsAsFactors = FALSE)
  colnames(dfh) <- dfv[,1]
  
  return(dfh)
}

organize_results <- function(fulltests){
  require(plyr)
  # Each results contains multiple tests, split each of those out and convert to wide format, then rbind back together
  test_start <- grep("Project", fulltests$name)
  
  if (length(test_start) >= 1) {
    # TODO: test what happens if only 1 test is present
    # Note if the length is not greater than 1 there is not test data
    index <- make_index(test_start, nrow(fulltests))
    
    # Take all the field from before the tests and transpose making key
    header <- (fulltests[1:(index[1,1]-1),])
    
    # Take each test transpose, column bind with key fields
    row_header <- tdf(header)
    
    each <- lapply(1:nrow(index), subset_results, index, fulltests)
    teach <- lapply(each, tdf)
    
    # Add all the test rows together
    test_records <- do.call(rbind.fill, teach)
    
    # Bind the row header
    test_results <- cbind(row_header, test_records)
    
    return(test_results)
  } else {
    
    print("No test results")
    return(NULL)
  }
  
}

parse_results <- function(txt){
  # convert into a table, by splitting on :&nbsp
  
  # First add a :&nbsp to Benchmark Started, and Benchmark Completed
  txt <- sub("Benchmark Started ", "Benchmark Started: ", txt)
  txt <- sub("Benchmark Completed ", "Benchmark Completed: ", txt)
  
  parsed <- as.data.frame(do.call(rbind, strsplit(txt, ": ")), stringsAsFactors = FALSE)
  names(parsed) <- c("name","value")
  
  # Trim all pre and post whitespace
  # TODO: do we need this?
  #parsed %>% mutate_if(is.character, trimws)
  
  
  row_results <- organize_results(parsed)
  return(row_results)
}

read_results <- function(rfile){
  # Read the txt files results
  print(rfile)
  txt <- readLines(rfile)
  
  # If there are multiple runs split the file, Agisoft is the start of a new test
  test_start <- grep("Agisoft", txt)
  
  if (length(test_start) > 1 ){
    
    # Compute the end of each test segment
    index <- make_index(test_start, length(txt))
    
    # Process each subset
    each <- lapply(1:nrow(index), subset_results, index, txt)    
    all <- lapply(each, parse_results)

    
    # For now only keep things with 29 lines
    valid_results <- all[(lapply(all, nrow) >=29)]
  } else {
    valid_results <- parse_results(txt)
  }
  
  # Include the file name as a UID?
  # TODO: print the hostname in the log
  valid_results <- cbind(basename(rfile), valid_results, stringsAsFactors = FALSE)
  names(valid_results)[1]  <- "NodeFile"
  
  return(valid_results)
}

find_numeric_characters <- function(x) {
  # convert numeric columns to numbers
  # https://stackoverflow.com/a/49054046/237354
  !all(is.na(suppressWarnings(as.numeric(x, na.rm=TRUE)))) & is.character(x)
}

#### Script ####

# List of the files with results
results <- list.files("data", pattern="^benchmark*.*txt$",  full.names = TRUE)

# Skip results which contain multiple tests.

# Parse the results into something useful
# Skipping Benchmark_Results.txt which is a copy before rename from one of the machines
parsed_files <- sapply(results, read_results)

# TODO: Collapse all the Benchmark Completed ... into 1 column

result_table <- do.call(rbind.fill, parsed_files)

# Clean up, convert numeric columns to numbers
numeric_cols <- sapply(1:ncol(result_table), function(i){ find_numeric_characters(result_table[,i]) })
result_table[ ,numeric_cols] <- sapply(result_table[ ,numeric_cols], as.numeric, na.rm = TRUE)


#### Visuals ####

# Make charts showing the different cumulative times per run across different hardware

tests <- unique(result_table$Project)


# The order of the fields changed with a new test
# TODO: set the field ordering, for now +1
pr_cols <- list(
  'Rock Model'=(c(8,9,10,11,12,13)+1),
  'Rock Model using Depth Maps'=(c(8,9,12,13,15)+1),
  'School Map'=(c(8,9,10,16,17,18)+1)
)

png_path <- "results"

# TODO loop over the project results, making a plot for each
for (i in 1:length(tests)){
  plot_file <- file.path(png_path,paste0(gsub(" ", "_", tests[i]), ".png"))
  png(filename = plot_file)
  #pr1 <- as.matrix(result_table[result_table$Project==tests[1], c(8:13)])
  pr1 <- as.matrix(result_table[result_table$Project==tests[i], unlist(unname(pr_cols[tests[i]]))])
  rownames(pr1) <- sapply(strsplit(result_table[as.numeric(rownames(pr1)), 1], "-|\\."), `[[`, 2)
  
  pr1 <- pr1[order(rowSums(pr1)), ]
  barplot(t(pr1), 
          horiz = TRUE,
          las=2,
          legend = TRUE,
          args.legend = list(x="bottomright", cex=1),
          cex.names = 0.8,
          names.arg = sub("_","\n", rownames(pr1)), 
          main = tests[i],
          xlab = "Time (seconds, lower is better)"
  )
  
  dev.off()  
}
