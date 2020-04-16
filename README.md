
<p align="center">
<img src="data/icons/hicolor/128x128/apps/com.github.inercia.k3x.svg" width="150">
</p>

# k3x

[![Build Status](https://travis-ci.org/inercia/k3x.svg?branch=master)](https://travis-ci.org/inercia/k3x)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/4603391d30854d2381b09bb0df64710d)](https://www.codacy.com/manual/inercia/k3x?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=inercia/k3x&amp;utm_campaign=Badge_Grade)
[![MIT Licence](https://badges.frapsoft.com/os/mit/mit.svg?v=103)](https://opensource.org/licenses/mit-license.php)
[![](https://img.shields.io/github/downloads/inercia/k3x/total.svg)](https://GitHub.com/inercia/k3x/releases/)

k3x is a graphical user interface for [k3d](https://github.com/rancher/k3d),
making it trivial to have your own local [Kubernetes](https://kubernetes.io/) cluster(s).

k3x is perfect for:

* having a fresh Kubernetes cluster in a couple of seconds.
* trying new deployments before going in production. 
* learning about Kubernetes.

k3x goals are:

* to create/switch-to/destroy Kubernetes clusters easily.
* to drive the most important operations with global keyboard shortcuts.
* to reduce the learning curve of using Kubernetes.

## Pre-requisites

* A **Docker** daemon. It can be both a local or a remote one... but things
  are easier with a local one. Follow [these instructions](https://docs.docker.com/engine/install/)
  for installing it in your machine.
* Some Linux distribution where you can install **[Flatpak](https://flatpak.org) packages**.
  * Install Flatpack by following [these instructions](https://flatpak.org/setup/).
  * Add the [Flathub repo](https://flathub.org) with
  ```commandline
  $ flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
  ```

## Installation

* Using the `.flatpak` file provided in [our releases page](https://github.com/inercia/k3x/releases).
  * Download the `.flatpak` file.
  * Most modern distributions will install this package automatically when double clicking it.
    However, if this does not work, you can install it from command line with:
    ```commandline
    $ flatpak install --user com.github.inercia.k3x.flatpak
    ```
    When installing from command line, it will probably ask you about installing some
    additional _runtimes_ if they are not already present (like the _GNOME_ runtime).
    In that case, please accept the installation of all the dependencies. 

* Installing from the [Flathub](https://flathub.org): _comming soon!_

## Running it

```commandline
$ flatpak run --user com.github.inercia.k3x
```

## Documentation

* [Creating a new cluster](docs/user-manual-creating-a-new-cluster.md).
* [Preferences](docs/user-manual-preferences.md).
* [Frequently asked questions](docs/faq.md).



