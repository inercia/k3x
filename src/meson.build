app_id = 'com.github.inercia.k3dv'
pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
moduledir = join_paths(pkgdatadir, 'k3dv')
gnome = import('gnome')

gnome.compile_resources('k3dv',
  'k3dv.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', join_paths(get_option('prefix'), get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'k3dv.in',
  output: 'k3dv',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir')
)

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

k3dv_sources = [
  '__init__.py',
  'cluster_view.py',
  'config.py',
  'docker.py',
  'helm.py',
  'k3d.py',
  'keybindings.py',
  'kubectl.py',
  'main.py',
  'menu.py',
  'preferences.py',
  'utils.py',
  'utils_ui.py',
]

install_data(k3dv_sources, install_dir: moduledir)
