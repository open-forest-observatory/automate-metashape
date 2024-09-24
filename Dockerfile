# Start with a python base image
FROM python:3.9
WORKDIR /app
# Copy files from current directory into /app
COPY . /app
# Install GLU dependencies
RUN apt update
RUN apt install -y libglu1-mesa
RUN apt install -y libgl1-mesa-glx
# Download the wheel
RUN curl https://download.agisoft.com/Metashape-2.1.3-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl --output Metashape-2.1.3-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl
# And install
RUN python3 -m pip install Metashape-2.1.3-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl