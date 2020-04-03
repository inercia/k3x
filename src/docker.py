# docker.py
#
# MIT License
#
# Copyright (c) 2020 Alvaro Saurin <alvaro.saurin@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import logging
import os
from typing import Optional

from .config import ApplicationSettings, SETTINGS_KEY_DOCKER_ENDPOINT


class DockerController(object):
    def __init__(self, settings: ApplicationSettings):
        super().__init__()

        self._client = None
        self._settings = settings
        self._recreate_client()
        settings.connect(f"changed::{SETTINGS_KEY_DOCKER_ENDPOINT}", lambda s, k: self._recreate_client())

    def _recreate_client(self):
        dh = self.docker_host
        logging.info(f"Creating/recreating docker client with DOCKER_HOST={dh}")
        os.environ.update(DOCKER_HOST=dh)

        import docker
        self._client = docker.from_env()

    @property
    def docker_host(self) -> str:
        """
        Returns the current DOCKER_HOST stored in the preferences.
        """
        return str(self._settings.get_string(SETTINGS_KEY_DOCKER_ENDPOINT).strip("\'").strip("\""))

    @property
    def default_docker_host(self) -> str:
        """
        Returns the default value for the DOCKER_HOST
        """
        return str(self._settings.get_default_value(SETTINGS_KEY_DOCKER_ENDPOINT)).strip('\'').strip('\"')

    def get_container_by_name(self, name: str) -> Optional[str]:
        """
        Return the container with the given name, or None if it could not be found.
        """
        for c in self._client.containers.list():
            if c.name == name:
                return c
        return None

    def get_container_ip(self, container, network_name: str) -> str:
        """
        Return the container IP

        The network will be something like 'k3d-k3s-cluster-690'
        """
        return container.attrs['NetworkSettings']['Networks'][network_name]['IPAddress']

    def get_official_k3s_images(self):
        # should return the same as https://hub.docker.com/r/rancher/k3s/tags
        return self._client.images.list("rancher/k3s")
