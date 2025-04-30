# Use a GPU-enabled base image
FROM nvcr.io/nvidia/cuda:12.8.1-runtime-ubuntu24.04

USER root

# Adapted from https://github.com/jeffgillan/agisoft_metashape/blob/main/Dockerfile
LABEL authors="David Russell"
LABEL maintainer="djrussell@ucdavis"

# Create user account with password-less sudo abilities
RUN useradd -s /bin/bash -g 100 -G sudo -m user
RUN /usr/bin/printf '%s\n%s\n' 'password' 'password'| passwd user
RUN echo "user ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

ENV DEBIAN_FRONTEND=noninteractive

# Install libraries/dependencies
RUN apt-get update &&            \
      apt-get install -y \
      libcurl4 \
      wget && \
      rm -rf /var/lib/apt/lists/*

# Install the command line python module. Note that this does not install the GUI
RUN apt-get update -y && apt-get install -y python3-pip
RUN cd /opt && wget https://download.agisoft.com/Metashape-2.2.0-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl && \
      pip3 install Metashape-2.2.0-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl && pip3 install PyYAML && \
      rm -rf *.whl

# Set the container workdir
WORKDIR /app
# Copy files from current directory into /app
COPY . /app

# Set the default command and default arguments
ENTRYPOINT ["python3", "/app/python/metashape_workflow.py"]
CMD ["/data/config.yml"]