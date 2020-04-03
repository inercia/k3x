
PROJECT_ROOT     = $(shell pwd)

APP_TITLE        = k3dv
APP_ID           = com.github.inercia.$(APP_TITLE)

RUNTIME          = org.gnome.Platform

FLATPAK_MANIFEST = $(PROJECT_ROOT)/com.github.inercia.k3dv.json
BUILD_ROOT       = $(PROJECT_ROOT)/.flatpak-builder

BUNDLE          ?= $(APP_TITLE).flatpak

STATE_DIR        = $(BUILD_ROOT)
CCACHE_DIR       = $(BUILD_ROOT)/ccache
BUILD_DIR        = $(BUILD_ROOT)/build/staging
REPO_DIR         = $(BUILD_ROOT)/repo
DIST_DIR         = $(PROJECT_ROOT)/dist

FLATPAK_RUN_ARGS = \
	--nofilesystem=host \
	--env=NOCONFIGURE=1 \
	--env=LANG=en_US.UTF-8 \
	--env=USER=$$USER \
	--env=HOME=$$HOME \
	--env=PATH=/app/bin:/usr/bin:/bin \
	--env=TERM=xterm-256color \
	--env=V=0 \
	--env=CCACHE_DIR=$(CCACHE_DIR) \
	--filesystem=$(BUILD_ROOT) \
	--filesystem=$(PROJECT_ROOT) \
	--filesystem=$(BUILD_DIR)

FLATPAK_RUN_SHARES = \
	--share=ipc \
	--socket=x11 \
	--share=network \
	--socket=wayland \
	--filesystem=xdg-run/dconf \
	--filesystem=~/.config/dconf:ro \
	--talk-name=ca.desrt.dconf \
	--talk-name=org.freedesktop.Notifications \
	--talk-name=org.kde.StatusNotifierWatcher \
	--env=DCONF_USER_CONFIG_DIR=.config/dconf \
	--filesystem=home \
	--filesystem=/run/docker.sock

FLATPAK_BUILDER_ARGS = \
	--arch=x86_64 --ccache --force-clean --state-dir $(STATE_DIR) --disable-updates

FLATPAK_BUILD_ARGS = \
	$(FLATPAK_RUN_ARGS) $(FLATPAK_RUN_SHARES) $(BUILD_DIR)

##############################
# Help                       #
##############################

RED=\033[1;31m
GRN=\033[1;32m
BLU=\033[1;34m
CYN=\033[1;36m
BLD=\033[1m
END=\033[0m

.PHONY: help
help: ## Show this help screen
	@echo 'Usage: make <OPTIONS> ... <TARGETS>'
	@echo ''
	@echo 'Available targets are:'
	@echo ''
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##############################
# Development                #
##############################

##@ Development

.PHONY: build
build: $(BUILD_DIR)  ## Build the application
	@printf "$(CYN)>>> $(GRN)Downloading dependencies...$(END)\n"
	flatpak-builder $(FLATPAK_BUILDER_ARGS) --download-only --stop-at=k3dv \
		$(BUILD_DIR) $(FLATPAK_MANIFEST)

	@printf "$(CYN)>>> $(GRN)Building dependencies...$(END)\n"
	flatpak-builder $(FLATPAK_BUILDER_ARGS) --disable-download --stop-at=k3dv \
		$(BUILD_DIR) $(FLATPAK_MANIFEST)

	@printf "$(CYN)>>> $(GRN)Building with meson...$(END)\n"
	flatpak build --build-dir=$(BUILD_DIR) $(FLATPAK_BUILD_ARGS) \
		meson --prefix=/app $(PROJECT_ROOT)

	@printf "$(CYN)>>> $(GRN)Running ninja...$(END)\n"
	@cd $(BUILD_DIR) && \
		flatpak build --build-dir=$(BUILD_DIR) $(FLATPAK_BUILD_ARGS) ninja && \
		echo ">>> Running ninja install" && \
		flatpak build --build-dir=$(BUILD_DIR) $(FLATPAK_BUILD_ARGS) ninja install

.PHONY: clean
clean: ## Remove the build dir
	rm -rf $(BUILD_DIR) $(APP_TITLE).flatpak

.PHONY: clean
distclean: ## Clean-up everything
	rm -rf .flatpak-builder

 $(BUILD_DIR):
	@printf "$(CYN)>>> $(GRN)Creating build dir...$(END)\n"
	mkdir -p $(BUILD_DIR)
	-flatpak build-init $(BUILD_DIR) $(APP_ID) org.gnome.Sdk $(RUNTIME) 3.34

##############################
# Run
##############################

##@ Local dev loop

.PHONY: run
run: build ## Run the application locally
	@printf "$(CYN)>>> $(GRN)Running k3dv in a sandbox...$(END)\n"
	@flatpak-builder $(FLATPAK_RUN_ARGS) $(FLATPAK_RUN_SHARES) \
		--run $(BUILD_DIR) $(FLATPAK_MANIFEST) \
		k3dv


##############################
# Packaging
##############################

##@ Packaging and releasing

.PHONY: package
package: $(BUNDLE)    ## Export the Flatpack bundle

$(BUNDLE): build
	@rm -rf $(REPO_DIR)

	@printf "$(CYN)>>> $(GRN)Finishing the build...$(END)\n"
	flatpak build-finish $(FLATPAK_BUILD_ARGS)

	@printf "$(CYN)>>> $(GRN)Exporting bundle: repo_dir=$(REPO_DIR) build_dir=$(BUILD_DIR)$(END)\n"
	flatpak build-export $(REPO_DIR) $(BUILD_DIR)

	@printf "$(CYN)>>> $(GRN)Buidlding bundle: repo_dir=$(REPO_DIR) bundle=$(BUNDLE)$(END)\n"
	flatpak build-bundle $(REPO_DIR) $(BUNDLE) $(APP_ID)

	@printf "$(CYN)>>> $(GRN)Bundle available at $(BUNDLE)$(END)\n"

##############################
# CI
##############################

ci/setup:
	#	@printf "$(CYN)>>> $(GRN)Installing flatpak utils...$(END)\n"
	#	sudo add-apt-repository ppa:alexlarsson/flatpak -y
	#	sudo apt-get update -q
	#	sudo apt-get install -y flatpak flatpak-builder elfutils

	@printf "$(CYN)>>> $(GRN)Adding flatpak remote...$(END)\n"
	flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
	flatpak install -y flathub $(RUNTIME)

ci/build: build

ci/release: package




