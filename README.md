# simple-reg-cleaner

Simple Docker registry cleaner written in Python

## Features

* Asynchronous and fast: Utilizes asyncio for efficient concurrent processing, ensuring speedy cleanup of Docker images.
* Proxy support: Built-in HTTPS proxy support for seamless communication with remote container registries.
* Manual and automatic mode: Offers flexibility with manual job selection or automated periodic cleanup.
* Based on periodic jobs: Customizable cleanup strategies through scheduled repository scans.

## Limitations

* No built-in support for detailed reports yet.
* No notification system for cleanup events.
* Lacks OS signal handling for graceful shutdowns.

## Introduction

The Docker Registry Cleaner is a command-line application designed to automatically clean up old docker images from a Docker registry. It provides a flexible and configurable way to define cleanup jobs based on various criteria.

## Installation

The Docker Registry Cleaner can be installed and run using Python 3.11 or higher. Follow these steps to install and run the application:

1. Clone the repository or download the source code from the GitHub repository.

2. Install the required dependencies by running the following command or just use `Pipenv` tool:

    ```text
    pip install -r requirements.txt
    ```

3. All dependencies including dev

   ```text
   pip install -r requirements.all.txt
   ```

## Configuration

The Docker Registry Cleaner requires 3 configuration files: `config/config.yaml`, `config/jobs.yaml` and `config/manual.yaml`.  
You can find examples in repository

### config.yaml

Exmaple:

```yaml
# Your docker registry url. 
registry_url: https://your.registry.com/
# Environment variables works only for username, password and proxy
# Format: <field>: "__ENV: <YOUR_ENV_NAME>"
# or you can use strings
# username: your_username
username: "__ENV: ENV_VAR_NAME"
password: "__ENV: ENV_VAR_NAME2"
# Optional; Format: <scheme>://[username:password@]<address>[:port]
proxy: "__ENV: PROXY"
# Optional, default 20, max 120, min 1
timeout: 20
# Optional; default 20
max_concurrent_requests: 20
```

* `registry_url`: The URL of the Docker registry to be cleaned.
* `username`: The username used for authentication with the Docker registry.
* `password`: The password used for authentication with the Docker registry.
* `max_concurrent_requests`: The maximum number of concurrent requests the application can make to the registry. Default value: 20.
* `proxy`: The URL of the proxy server to be used for making requests to the registry. If not needed, leave blank or delete.
* `timeout`: The timeout for each HTTP request in seconds. Default value: 20.
* **`username`, `registry` and `proxy` can be set using environment variables, as shown in the example**

### jobs.yaml

A list of cleanup jobs defined in `jobs.yaml`. Each job is defined by the following parameters:

```yaml
- name: clean-dev-tags
  # Optional
  description: Clean dev tags every 72 hours
  # List of repositories to clean
  repositories:
    - dependency-scanner-dev
    - scheduler-dev
    - admin-panel-dev
  # Pythonic regular expressions to match the tag name
  # Be careful using this. Check your regexp at https://regex101.com/
  tag_regexps:
    - v5\.\d+\.\d+-dev$
    - develop-[\d\w]+$
  # Do not delete the last n tags, even
  # if they are older than the specified number of days
  save_last: 5
  # Perform checks and do cleanup every x hours
  clean_every_n_hours: 24
  # Delete tags if their creation date is older than y days
  older_than_days: 5
```

* `name`: The name of the job.
* `description`: An optional description of the job.
* `repositories`: String array of repository names to clean up images from.
* `tag_regexps`: String array of regular expressions to match tags in the repositories. Only tags that match these regex patterns will be considered for cleanup. Be careful using this option. Check your regexp at https://regex101.com/
* `save_last`: The number of the most recent tags to be saved (excluded from cleanup) in each repository.
* `clean_every_n_hours`: The interval in hours between consecutive cleanup runs for this job.
* `older_than_days`: The age in days beyond which tags will be considered for cleanup.

### manual.yaml

Differences from `jobs.yaml`:

* The field clean_every_n_hours is not required as it will always be set to 0.
* This file is used exclusively with the `--jobs` option, allowing you to specify jobs declared in `manual.yaml`.
* There is no need to wait until the next run; the next cleanup can be performed immediately after the previous one.

## Usage

To run the Docker Registry Cleaner, use the following command:

```text
python main.py [OPTIONS]
```

### Options

```text
$ python -h
usage: main.py [-h] [--debug] [--watch] [--jobs JOBS [JOBS ...]] [--http-logs]

Automatic cleaner of old docker images

options:
  -h, --help            show this help message and exit
  --debug               The application will generate logs without actually deleting the images
  --watch               Endless operation of the application for auto cleanup. Will be used 'config.yaml'
  --jobs JOBS [JOBS ...]
                        List of jobs in `manual.yaml` to run. Example: --jobs clean-dev-tags clean-prod-older-15
  --http-logs           Enable http logs for every request
```

The Docker Registry Cleaner accepts the following options:

* `--debug`: If provided, the application will generate logs without actually deleting the images. **Use this option if you need to check the images the app will delete**
* `--watch`: If provided, the application will run in an endless loop, periodically executing cleanup jobs based on the configuration in `config.yaml`.
* `--jobs`: A list of job names defined in manual.yaml that you want to run. For example: `--jobs clean-dev-tags clean-prod-older-15`.
* `--http-logs`: If provided, HTTP logs will be enabled for every request made by the application.
* **Args 'watch' and 'jobs' are mutually exclusive. Please use one of them**

### Debug Mode

If you have used the application with the `--debug` option and need to immediately trigger the cleanup process, you might need to clean the `latest_cleanup.json` file or delete a specific section with the job result you are interested in. Performing this step enables you to trigger the next cleanup immediately without waiting for the next automatic cleanup cycle.

After running the application with the `--debug` mode, you need to stop the application using `Ctrl + C` and then restart it without the `--debug` option to resume the normal cleanup process.

### Logs and cache files

* App logs stored in `logs/cleaner.log`
* Every performed check and runs with timestamps in `cache/history.log`
* Every latest cleanup info about jobs and deleted images in `cache/latest_cleanup.json`

## Docker Image Options

This repository includes two Dockerfiles located in the root directory: `Dockerfile` based on Alpine Linux and `Dockerfile.bullseye` based on Debian 11.

Both Docker containers are designed to execute the same command: `python3 main.py --watch --http-logs`, which initiates the cleanup process in an infinite loop. Once you start the container, it will continue running indefinitely, requiring no further intervention. This setup ensures a hassle-free and continuous Docker images cleanup process.

### Build

Alpine:

```text
docker build -t cleaner:alpine .
```

Debian:

```text
docker build -t cleaner:debian -f Dockerfile.bullseye .
```

### Run

To run the Docker Registry Cleaner, you need to provide the required environment variables for authentication and, if necessary, mount fresh configuration files inside the container:

```text
docker run \                   
  -v ./config/config.yaml:/app/config/config.yaml \
  -v ./config/jobs.yaml:/app/config/jobs.yaml \
  cleaner
```

Stop:

```text
docker container stop <container_name> -s KILL
```