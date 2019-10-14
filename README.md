# metashape-scripts

A library of scripts to make it easier to run metashape in batch on individual computers, or as jobs on a compute cluster.

## Software

You need a license for Metashape. UC Davis users see []()

If you have a node locked license copy the auth.template file and call it auth.auth, replace the #### with your key code.
Should look like this.

```
#!/bin/sh
KEY="#####-#####-#####-#####-#####"
```

## Usage

Command line:
1. Path to metashape program
2. Path to python script
3. Path to project folder which contains photos

### Linux

```
```

### Windows

```
& 'C:\Program Files\Agisoft\Metashape Pro\metashape.exe' -r C:\Users\vulpes\Documents\metashapebenchmark\benchmark_simple.py D:\Public\Pictures\Latimer_lab\thinned_set_subset >> nightfury-20190827.out
```

## Analysis

A log recording the times of each major step is written in the following format.
See the R scripts in the reports folder for ways to work with the results data.
