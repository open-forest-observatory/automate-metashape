FROM python:3.9
WORKDIR /app
RUN apt-get update && apt-get install libglu1 -y
COPY . /app
RUN curl https://download.agisoft.com/Metashape-2.1.3-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl --output Metashape-2.1.3-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl
RUN python3 -m pip install Metashape-2.1.3-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl
