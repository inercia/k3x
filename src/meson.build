app_id = 'com.github.inercia.k3x'
pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
moduledir = join_paths(pkgdatadir, 'k3x')

#########################################################
# resources
#########################################################

gnome = import('gnome')

gnome.compile_resources('k3x',
  'k3x.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

#########################################################
# main executable
#########################################################

python = import('python')
conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').path())
conf.set('VERSION', meson.project_version())
conf.set('PREFIX', get_option('prefix'))
conf.set('localedir', join_paths(get_option('prefix'), get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'k3x.in',
  output: 'k3x',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir')
)

#########################################################
# dependencies
#########################################################

appindicator_dep = dependency('ayatana-appindicator3-0.1', required: false)
if appindicator_dep.found()
  enable_appindicator = 'ayatana'
else
  appindicator_dep = dependency('appindicator3-0.1', required: false)
  if appindicator_dep.found()
    enable_appindicator = 'ubuntu'
  else
    assert(appindicator_dep.found(), 'Neither Ubuntu\'s AppIndicator nor Ayatana AppIndicator found.')
  endif
endif

if enable_appindicator == 'ayatana'
  appindicator_dep = dependency('ayatana-appindicator3-0.1')
elif enable_appindicator == 'ubuntu'
  appindicator_dep = dependency('appindicator3-0.1')
endif

#########################################################
# install sources
#########################################################

k3x_sources = [
  '__init__.py',
  'cluster_view.py',
  'config.py',
  'docker.py',
  'helm.py',
  'k3d.py',
  'k3d_controller.py',
  'keybindings.py',
  'kubectl.py',
  'main.py',
  'menu.py',
  'preferences.py',
  'utils.py',
  'utils_ui.py',
]

install_data(k3x_sources, install_dir: moduledir)
