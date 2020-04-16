app_id = 'com.github.inercia.k3x'

################################################
# icon
################################################

# NOTE: make sure this path matches APP_ICON_PATH in config.py
icondir = join_paths('icons', 'hicolor', '128x128', 'apps')

install_data(
  join_paths(icondir, '@0@.svg'.format(app_id)),
  install_dir: join_paths(get_option('datadir'), icondir),
)

################################################
# desktop file
################################################

desktop_conf = configuration_data()
desktop_conf.set('ICON', app_id)
desktop_conf.set('APP_ID', app_id)
desktop_conf.set('VERSION', meson.project_version())

desktop_file = i18n.merge_file(
  input: configure_file(
    input: files('@0@.desktop.in.in'.format(app_id)),
    output: '@0@.desktop.in'.format(app_id),
    configuration: desktop_conf
  ),
  output: '@0@.desktop'.format(app_id),
  type: 'desktop',
  po_dir: '../po',
  install: true,
  install_dir: join_paths(get_option('datadir'), 'applications')
)

desktop_utils = find_program('desktop-file-validate', required: false)
if desktop_utils.found()
  test('Validate desktop file', desktop_utils,
    args: [desktop_file]
  )
endif

################################################
# Appdata file
################################################

appstream_file = i18n.merge_file(
  input: 'com.github.inercia.k3x.appdata.xml.in',
  output: 'com.github.inercia.k3x.appdata.xml',
  po_dir: '../po',
  install: true,
  install_dir: join_paths(get_option('datadir'), 'appdata')
)

appstream_util = find_program('appstream-util', required: false)
if appstream_util.found()
  test('Validate appstream file', appstream_util,
    args: ['validate', appstream_file]
  )
endif

################################################
# GSchema file
################################################

install_data('com.github.inercia.k3x.gschema.xml',
  install_dir: join_paths(get_option('datadir'), 'glib-2.0/schemas')
)

compile_schemas = find_program('glib-compile-schemas', required: false)
if compile_schemas.found()
  test('Validate schema file', compile_schemas,
    args: ['--strict', '--dry-run', meson.current_source_dir()]
  )
endif

