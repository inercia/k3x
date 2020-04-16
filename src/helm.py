# helm.py
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
import shutil
from typing import Iterator, Optional

import yaml

from .config import ApplicationSettings, APP_ID
from .utils import find_executable, run_command_stdout

helm_exe = find_executable("helm", extra_paths=["/app"])
logging.debug(f"helm found at {helm_exe}")


def run_helm_command(*args) -> Iterator[str]:
    """
    Run a k3d command
    """
    logging.debug(f"Running k3d command: {args}")
    yield from run_command_stdout(helm_exe, *args)


def get_chart_dir_for(owner: str) -> str:
    """
    Get (and create) a directory for storying Helm charts for some cluster
    """
    res = os.path.abspath(os.path.join(ApplicationSettings.get_cache_dir(), "helm", owner))
    os.makedirs(res, exist_ok=True)
    return res


def get_chart_filename_for(owner: str, chart: str) -> str:
    """
    Get a full path for storying a Chart
    """
    return os.path.abspath(os.path.join(get_chart_dir_for(owner), f"{chart}.yaml"))


def cleanup_for_owner(owner: str):
    """
    Remove the directory where charts are saved for an owner
    """
    d = get_chart_dir_for(owner)
    if os.path.exists(d) and os.path.isdir(d):
        shutil.rmtree(d)


class HelmChart(object):
    """
    A Helm chart
    """

    # see https://rancher.com/docs/k3s/latest/en/helm/

    def __init__(self, name: str, chart: str, namespace: str = "default",
                 repo: Optional[str] = None, version: Optional[str] = None,
                 values=None,
                 extra_manifests=None):

        if extra_manifests is None:
            extra_manifests = []
        if values is None:
            values = {}

        self.name = name
        self.namespace = namespace
        self.chart = chart
        self.values = values
        self.file = None
        self.version = version
        self.repo = repo
        self.extra_manifests = extra_manifests

    def generate(self, cluster) -> str:
        self.file = get_chart_filename_for(cluster.name, self.name)

        # see https://rancher.com/docs/k3s/latest/en/helm/#using-the-helm-crd
        chart_contents = {
            "apiVersion": "helm.cattle.io/v1",
            "kind": "HelmChart",
            "metadata": {
                "name": self.name,
                "namespace": "kube-system",
            },
            "spec": {
                "chart": self.chart,
                "set": {},
                "targetNamespace": self.namespace,
            }
        }

        if self.version:
            chart_contents["spec"]["version"] = self.version

        if self.repo:
            chart_contents["spec"]["repo"] = self.repo

        if self.values:
            chart_contents["spec"]["set"] = self.values

        with open(self.file, 'w') as outfile:
            logging.debug(f"[CHART] Saving YAML file for {self.name} in {self.file}")
            outfile.write("---\n")
            yaml.dump(chart_contents, outfile)

            for manifest in self.extra_manifests:
                outfile.write("\n---\n")
                outfile.write(manifest + "\n")

        with open(self.file, 'r') as infile:
            logging.debug(f"[CHART] Chart file contents on {self.file}")
            lines = infile.readlines()
            for line in lines:
                logging.debug(f"[CHART] " + line.rstrip())

        return self.file

    def __str__(self) -> str:
        return self.name


class HelmChartKubernetesDashboard(HelmChart):
    """
    A Helm Chart for installing the Kubernetes Dashboard
    """

    def __init__(self):
        # see https://github.com/helm/charts/tree/master/stable/kubernetes-dashboard
        super().__init__(name="dashboard",
                         chart="stable/kubernetes-dashboard",
                         namespace="kube-system",
                         values={
                             "enableSkipLogin": "true",
                             "enableInsecureLogin": "true",
                             "ingress.enabled": "true",
                             # https://docs.traefik.io/v1.7/configuration/backends/kubernetes/#annotations
                             r"ingress.annotations.kubernetes\.io/ingress\.class": "traefik",
                         })


class HelmChartRancher(HelmChart):
    """
    A Helm Chart for installing Rancher
    """

    # NOTE: we cannot rely on Rancher's Chart Ingress, as it requires a valid, external name
    #       for the `host` in the Ingress, and we don't have that, we only have
    #       an IP address (and it is not really necessary)

    ingress_manifest = f"""
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  name: rancher-ingress
  namespace: kube-system
  annotations:
    kubernetes.io/ingress.class: traefik
  labels:
    created-by: "{APP_ID}"
spec:
  rules:
  - http:
      paths:
      - backend:
          serviceName: rancher
          servicePort: 80
"""

    def __init__(self):
        # see https://rancher.com/docs/rancher/v2.x/en/installation/k8s-install/helm-rancher/
        super().__init__(name="rancher",
                         chart="rancher",
                         repo="https://releases.rancher.com/server-charts/latest",
                         namespace="kube-system",
                         # see https://rancher.com/docs/rancher/v2.x/en/installation/options/chart-options/
                         values={
                             "addLocal": "true",
                             "tls": "external",
                         },
                         extra_manifests=[self.ingress_manifest],
                         )


def get_charts_for_cluster(cluster_view):
    """
    Return a list of charts to install in the cluster
    """
    charts = []
    if cluster_view.install_dashboard:
        logging.debug("Creating chart for the Dashboard")
        charts.append(HelmChartRancher())

        # see our create_ingress_rule_to() for creating an ingress

    return charts
