# Use a GPU-enabled base image for Ubuntu 24.04
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

# Install basic dependencies
RUN apt-get update &&            \
    apt-get install -y libglib2.0-dev libglib2.0-0 libgl1 libglu1-mesa libcurl4 wget python3-venv python3-full libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Download the Metashape .whl file
RUN cd /opt && wget https://download.agisoft.com/Metashape-2.2.0-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl

# Create a virtual environment for Metashape
RUN python3 -m venv /opt/venv_metashape

# Activate the virtual environment and install Metashape and PyYAML
RUN /opt/venv_metashape/bin/pip install --upgrade pip
RUN /opt/venv_metashape/bin/pip install /opt/Metashape-2.2.0-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl
RUN /opt/venv_metashape/bin/pip install PyYAML psutil nvidia-ml-py

# Remove the downloaded wheel file
RUN rm /opt/*.whl

# Set the container workdir
WORKDIR /app
# Copy files from current directory into /app
COPY . /app

# Set the default command and default arguments
ENV PATH="/opt/venv_metashape/bin:${PATH}"
ENTRYPOINT ["python3", "/app/python/metashape_workflow.py"]
CMD ["/data/config.yml"]
