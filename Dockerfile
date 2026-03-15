# Use the specified Ubuntu version as the base image for the build stage
FROM ubuntu:22.04 AS build

# Set the Python version as an argument
ARG PYTHON_VERSION=3.10

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Update packages and install necessary dependencies
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y git \
    && apt-get install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-dev python3-pip \
    && python${PYTHON_VERSION} -m pip install --upgrade pip

# Copy requirements.txt and install Python dependencies
COPY requirements.txt /opt/requirements.txt
RUN python${PYTHON_VERSION} -m pip install --default-timeout=2000 -r /opt/requirements.txt -t /opt/site-packages


# Update symbolic link for python3
RUN rm /usr/bin/python3 \
    && ln -s /usr/bin/python${PYTHON_VERSION} /usr/bin/python3



# Build the final image using a minimal BusyBox with glibc
FROM busybox:1.34-glibc

# Set the Python version as an argument
ARG PYTHON_VERSION=3.10

# Copy necessary files and directories from the build stage
COPY --from=build /usr/bin/python${PYTHON_VERSION} /usr/bin/python${PYTHON_VERSION}
COPY --from=build /usr/lib/python${PYTHON_VERSION} /usr/lib/python${PYTHON_VERSION}/
COPY --from=build /lib/x86_64-linux-gnu /lib/x86_64-linux-gnu/
COPY --from=build /lib64 /lib64/
COPY --from=build /etc/alternatives /etc/alternatives/
COPY --from=build /opt/site-packages /usr/lib/python3/dist-packages/

# Create symbolic link for python3
RUN ln -s /usr/bin/python${PYTHON_VERSION} /usr/bin/python3

# Create a non-root user and set working directory
RUN addgroup -g 10000 friendly && adduser -u 10000 friendly -D -G friendly
USER friendly
WORKDIR /app



# Add configuration files, app files, and version information
ADD config /config
ADD app /app
ADD VERSION.json /app/VERSION.json

# Set environment variables
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1
ENV MPLCONFIGDIR=/tmp
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
