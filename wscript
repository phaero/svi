# -*- coding: utf-8 -*-
#
# WAF build script - originally made for the wscript in Geany
#

"""
This is a WAF build script (http://code.google.com/p/waf/).

Missing features:
--enable-binreloc, make targets: dist, pdf (in doc/)

Known issues:
* Dependency handling is buggy, e.g. if src/document.h is changed, depending source files are not rebuilt (maybe Waf bug).

Requires WAF 1.6.1 and Python 2.5 (or later).
"""


import sys
import os
import tempfile
from waflib import Logs, Options, Scripting, Utils
from waflib.Configure import ConfigurationContext
from waflib.Errors import ConfigurationError, WafError
from waflib.TaskGen import feature


APPNAME = 'geany'
VERSION = '1.22'
LINGUAS_FILE = 'po/LINGUAS'

top = '.'
out = 'bin'


def configure(conf):
	conf.check_waf_version(mini='1.6.11')

	conf.load('compiler_c')

	conf.check_cc(header_name='fcntl.h', mandatory=False)
	conf.check_cc(header_name='fnmatch.h', mandatory=False)
	conf.check_cc(header_name='glob.h', mandatory=False)
	conf.check_cc(header_name='sys/time.h', mandatory=False)
	conf.check_cc(header_name='sys/types.h', mandatory=False)
	conf.check_cc(header_name='sys/stat.h', mandatory=False)
	conf.define('HAVE_STDLIB_H', 1) # are there systems without stdlib.h?
	conf.define('STDC_HEADERS', 1) # an optimistic guess ;-)
	_add_to_env_and_define(conf, 'HAVE_REGCOMP', 1) # needed for CTags

	conf.check_cc(function_name='fgetpos', header_name='stdio.h',
			mandatory=False)
	conf.check_cc(function_name='ftruncate', header_name='unistd.h',
			mandatory=False)
	conf.check_cc(function_name='gethostname', header_name='unistd.h',
			mandatory=False)
	conf.check_cc(function_name='mkstemp', header_name='stdlib.h',
			mandatory=False)
	conf.check_cc(function_name='strstr', header_name='string.h')

	# check sunOS socket support
	if Options.platform == 'sunos':
		conf.check_cc(function_name='socket', lib='socket',
				header_name='sys/socket.h',
				uselib_store='SUNOS_SOCKET',
				mandatory=True)

	# check for cxx after the header and function checks have been done to ensure they are
	# checked with cc not cxx
	conf.load('compiler_cxx')

	_load_intltool_if_available(conf)

	# GTK / GIO version check
	conf.check_cfg(package='gtk+-2.0', atleast_version='2.16.0',
			uselib_store='GTK', mandatory=True, args='--cflags --libs')
	conf.check_cfg(package='glib-2.0', atleast_version='2.20.0',
			uselib_store='GLIB', mandatory=True, args='--cflags --libs')
	conf.check_cfg(package='gio-2.0', uselib_store='GIO',
			args='--cflags --libs', mandatory=True)

	gtk_version = conf.check_cfg(modversion='gtk+-2.0', uselib_store='GTK') or 'Unknown'
	conf.check_cfg(package='gthread-2.0', uselib_store='GTHREAD',
			args='--cflags --libs')

	# DATADIR and LOCALEDIR are defined by the intltool tool
	# but they are not added to the environment, so we need to
	_add_define_to_env(conf, 'DATADIR')
	_add_define_to_env(conf, 'LOCALEDIR')
	docdir = os.path.join(conf.env['DATADIR'], 'doc', 'geany')
	libdir = os.path.join(conf.env['PREFIX'], 'lib')
	mandir = os.path.join(conf.env['DATADIR'], 'man')
	_define_from_opt(conf, 'DOCDIR', conf.options.docdir, docdir)
	_define_from_opt(conf, 'LIBDIR', conf.options.libdir, libdir)
	_define_from_opt(conf, 'MANDIR', conf.options.mandir, mandir)

	revision = _get_git_rev(conf)

	conf.define('ENABLE_NLS', 1)
	conf.define('GEANY_LOCALEDIR', conf.env['LOCALEDIR'], quote=True)
	conf.define('GEANY_DATADIR',  conf.env['DATADIR'], quote=True)
	conf.define('GEANY_DOCDIR', conf.env['DOCDIR'], quote=True)
	conf.define('GEANY_LIBDIR', conf.env['LIBDIR'], quote=True)
	conf.define('GEANY_PREFIX', conf.env['PREFIX'], quote=True)
	conf.define('PACKAGE', APPNAME, quote=True)
	conf.define('VERSION', VERSION, quote=True)
	conf.define('REVISION', revision or '-1', quote=True)

	conf.define('GETTEXT_PACKAGE', APPNAME, quote=True)

	_define_from_opt(conf, 'HAVE_PLUGINS', not conf.options.no_plugins, None)
	_define_from_opt(conf, 'HAVE_SOCKET', not conf.options.no_socket, None)
	_define_from_opt(conf, 'HAVE_VTE', not conf.options.no_vte, None)

	conf.write_config_header('src/config.h', remove=False)

	# some more compiler flags
	conf.env.append_value('CFLAGS', ['-DHAVE_CONFIG_H'])
	if revision is not None:
		conf.env.append_value('CFLAGS', ['-g', '-DGEANY_DEBUG'])
	# Scintilla flags
	conf.env.append_value('CFLAGS', ['-DGTK'])
	conf.env.append_value('CXXFLAGS',
		['-DNDEBUG', '-DGTK', '-DSCI_LEXER', '-DG_THREADS_IMPL_NONE'])

	# summary
	Logs.pprint('BLUE', 'Summary:')
	conf.msg('Install Geany ' + VERSION + ' in', conf.env['PREFIX'])
	conf.msg('Using GTK version', gtk_version)
	conf.msg('Build with plugin support', conf.options.no_plugins and 'no' or 'yes')
	conf.msg('Use virtual terminal support', conf.options.no_vte and 'no' or 'yes')
	if revision is not None:
		conf.msg('Compiling Git revision', revision)


def options(opt):
	opt.tool_options('compiler_cc')
	opt.tool_options('compiler_cxx')
	opt.tool_options('intltool')

	# Features
	opt.add_option('--disable-plugins', action='store_true', default=False,
		help='compile without plugin support [default: No]', dest='no_plugins')
	opt.add_option('--disable-socket', action='store_true', default=False,
		help='compile without support to detect a running instance [[default: No]',
		dest='no_socket')
	opt.add_option('--disable-vte', action='store_true', default=False,
		help='compile without support for an embedded virtual terminal [[default: No]',
		dest='no_vte')
	# Paths
	opt.add_option('--mandir', type='string', default='',
		help='man documentation', dest='mandir')
	opt.add_option('--docdir', type='string', default='',
		help='documentation root', dest='docdir')
	opt.add_option('--libdir', type='string', default='',
		help='object code libraries', dest='libdir')
	# Actions
	opt.add_option('--hackingdoc', action='store_true', default=False,
		help='generate HTML documentation from HACKING file', dest='hackingdoc')

def build(bld):
	if bld.cmd == 'clean':
		_remove_linguas_file()
	if bld.cmd in ('install', 'uninstall'):
		bld.add_post_fun(_post_install)

	bld.recurse( 'src' )
	bld.recurse( 'doc' )
	bld.recurse( 'data' )
	bld.recurse( 'icons' )

	# Translations
	if bld.env['INTLTOOL']:
		bld.new_task_gen(
				features = ['linguas', 'intltool_po'],
				podir = 'po',
				install_path = '${LOCALEDIR}',
				appname = 'geany',
			)

	# geany.pc
	bld.new_task_gen(
			source = 'geany.pc.in',
			dct = {
				'VERSION' : VERSION,
				'prefix': bld.env['PREFIX'],
				'exec_prefix': '${prefix}',
				'libdir': '${exec_prefix}/lib',
				'includedir': '${prefix}/include',
				'datarootdir': '${prefix}/share',
				'datadir': '${datarootdir}',
				'localedir': '${datarootdir}/locale'
			},
		)

	# geany.desktop
	if bld.env['INTLTOOL']:
		bld.new_task_gen(
				features = 'intltool_in',
				source = 'geany.desktop.in',
				flags = [ '-d', '-q', '-u', '-c' ],
				install_path = '${DATADIR}/applications'
			)

	# geany.1
	bld.new_task_gen(
			features = 'subst',
			source = 'doc/geany.1.in',
			target = 'geany.1',
			dct = {
				'VERSION': VERSION,
				'GEANY_DATA_DIR': bld.env['DATADIR'] + '/geany'
				},
			install_path = '${MANDIR}/man1'
		)

	# geany.spec
	bld.new_task_gen(
			features = 'subst',
			source = 'geany.spec.in',
			target = 'geany.spec',
			install_path = None,
			dct = {'VERSION' : VERSION},
		)

	# Doxyfile
	bld.new_task_gen(
			features = 'subst',
			source = 'doc/Doxyfile.in',
			target = 'doc/Doxyfile',
			install_path = None,
			dct = {'VERSION' : VERSION}
		)

def distclean(ctx):
	Scripting.distclean(ctx)
	_remove_linguas_file()

def _remove_linguas_file():
	# remove LINGUAS file as well
	try:
		os.unlink(LINGUAS_FILE)
	except OSError:
		pass

@feature('linguas')
def write_linguas_file(self):
	if os.path.exists(LINGUAS_FILE):
		return
	linguas = ''
	if 'LINGUAS' in self.env:
		files = self.env['LINGUAS']
		for po_filename in files.split(' '):
			if os.path.exists ('po/%s.po' % po_filename):
				linguas += '%s ' % po_filename
	else:
		files = os.listdir('%s/po' % self.path.abspath())
		files.sort()
		for filename in files:
			if filename.endswith('.po'):
				linguas += '%s ' % filename[:-3]
	file_h = open(LINGUAS_FILE, 'w')
	file_h.write('# This file is autogenerated. Do not edit.\n%s\n' % linguas)
	file_h.close()

def _post_install(ctx):
	theme_dir = Utils.subst_vars('${DATADIR}/icons/hicolor', ctx.env)
	icon_cache_updated = False
	if not ctx.options.destdir:
		ctx.exec_command('gtk-update-icon-cache -q -f -t %s' % theme_dir)
		Logs.pprint('GREEN', 'GTK icon cache updated.')
		icon_cache_updated = True
	if not icon_cache_updated:
		Logs.pprint('YELLOW', 'Icon cache not updated. After install, run this:')
		Logs.pprint('YELLOW', 'gtk-update-icon-cache -q -f -t %s' % theme_dir)

def updatepo(ctx):
	"""update the message catalogs for internationalization"""
	potfile = '%s.pot' % APPNAME
	os.chdir('%s/po' % top)
	try:
		try:
			old_size = os.stat(potfile).st_size
		except OSError:
			old_size = 0
		ctx.exec_command('intltool-update --pot -g %s' % APPNAME)
		size_new = os.stat(potfile).st_size
		if size_new != old_size:
			Logs.pprint('CYAN', 'Updated POT file.')
			Logs.pprint('CYAN', 'Updating translations')
			ret = ctx.exec_command('intltool-update -r -g %s' % APPNAME)
			if ret != 0:
				Logs.pprint('RED', 'Updating translations failed')
		else:
			Logs.pprint('CYAN', 'POT file is up to date.')
	except OSError:
		Logs.pprint('RED', 'Failed to generate pot file.')

def apidoc(ctx):
	"""generate API reference documentation"""
	basedir = ctx.path.abspath()
	doxygen = _find_program(ctx, 'doxygen')
	doxyfile = '%s/%s/doc/Doxyfile' % (basedir, out)
	os.chdir('doc')
	Logs.pprint('CYAN', 'Generating API documentation')
	ret = ctx.exec_command('%s %s' % (doxygen, doxyfile))
	if ret != 0:
		raise WafError('Generating API documentation failed')
	# update hacking.html
	cmd = _find_rst2html(ctx)
	ctx.exec_command('%s  -stg --stylesheet=geany.css %s %s' % (cmd, '../HACKING', 'hacking.html'))
	os.chdir('..')

def htmldoc(ctx):
	"""generate HTML documentation"""
	# first try rst2html.py as it is the upstream default, fall back to rst2html
	cmd = _find_rst2html(ctx)
	os.chdir('doc')
	Logs.pprint('CYAN', 'Generating HTML documentation')
	ctx.exec_command('%s  -stg --stylesheet=geany.css %s %s' % (cmd, 'geany.txt', 'geany.html'))
	os.chdir('..')

def _find_program(ctx, cmd, **kw):
	def noop(*args):
		pass

	ctx = ConfigurationContext()
	ctx.to_log = noop
	ctx.msg = noop
	return ctx.find_program(cmd, **kw)

def _find_rst2html(ctx):
	cmds = ['rst2html.py', 'rst2html']
	for command in cmds:
		cmd = _find_program(ctx, command, mandatory=False)
		if cmd:
			break
	if not cmd:
		raise WafError(
			'rst2html.py could not be found. Please install the Python docutils package.')
	return cmd

def _add_define_to_env(conf, key):
	value = conf.get_define(key)
	# strip quotes
	value = value.replace('"', '')
	conf.env[key] = value

def _add_to_env_and_define(conf, key, value, quote=False):
	conf.define(key, value, quote)
	conf.env[key] = value

def _define_from_opt(conf, define_name, opt_value, default_value, quote=1):
	value = default_value
	if opt_value:
		if isinstance(opt_value, bool):
			opt_value = 1
		value = opt_value

	if value is not None:
		_add_to_env_and_define(conf, define_name, value, quote)
	else:
		conf.undefine(define_name)

def _get_git_rev(conf):
	if not os.path.isdir('.git'):
		return

	try:
		cmd = 'git rev-parse --short --revs-only HEAD'
		revision = conf.cmd_and_log(cmd).strip()
	except WafError:
		return None
	else:
		return revision

def _load_intltool_if_available(conf):
	try:
		conf.check_tool('intltool')
		if 'LINGUAS' in os.environ:
			conf.env['LINGUAS'] = os.environ['LINGUAS']
	except WafError:
		raise
