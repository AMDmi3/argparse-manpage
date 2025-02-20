"""
build_manpages command -- generate set of manual pages by the setup()
command.
"""

import os
import shutil

try:
    import tomllib
    from tomllib import TOMLDecodeError
except ImportError:
    try:
        import tomli as tomllib
        from tomli import TOMLDecodeError
    except ImportError:
        import toml as tomllib
        from toml import TomlDecodeError as TOMLDecodeError

from argparse_manpage.compat import ConfigParser, NoSectionError
from argparse_manpage.tooling import get_parser, write_to_filename
from argparse_manpage.manpage import (
    Manpage,
    MANPAGE_DATA_ATTRS,
    get_manpage_data_from_distribution,
)

from .compat import (
    build_py,
    Command,
    DistutilsOptionError,
    install,
)

DEFAULT_CMD_NAME = 'build_manpages'

def parse_manpages_spec(string):
    manpages_data = {}
    for spec in string.strip().split('\n'):
        manpagedata = {}
        output = True
        for option in spec.split(':'):
            if output:
                outputfile = option
                output = False
                continue

            oname, ovalue = option.split('=')

            if oname == 'function' or oname == 'object':
                assert(not 'objtype' in manpagedata)
                manpagedata['objtype'] = oname
                manpagedata['objname'] = ovalue

            elif oname == 'pyfile' or oname == 'module':
                assert(not 'import_type' in manpagedata)
                manpagedata['import_type'] = oname
                manpagedata['import_from'] = ovalue
                if oname == 'pyfile':
                    manpagedata['prog'] = os.path.basename(ovalue)

            elif oname == 'format':
                assert(not 'format' in manpagedata)
                manpagedata[oname] = ovalue

            elif oname == 'author':
                manpagedata.setdefault("authors", []).append(ovalue)

            elif oname in MANPAGE_DATA_ATTRS and oname != "authors":
                assert(not oname in manpagedata)
                manpagedata[oname] = ovalue

            else:
                raise ValueError("Unknown manpage configuration option: {}".format(oname))

        manpages_data[outputfile] = manpagedata

    return manpages_data

def get_pyproject_settings():
    """Parse and handle errors of a toml configuration file."""
    try:
        with open("pyproject.toml", mode="r") as fp:
            content = tomllib.loads(fp.read())
    except TOMLDecodeError:
        return None

    try:
        value = content["tool"][DEFAULT_CMD_NAME]["manpages"]
        if isinstance(value, list):
            value = "\n".join(value)
        return str(value)
    except KeyError:
        return None

class build_manpages(Command):
    description = 'Generate set of man pages from setup().'
    user_options = [
        ('manpages=', 'O', 'list man pages specifications'),
    ]

    def initialize_options(self):
        self.manpages = None


    def finalize_options(self):
        manpages = self.manpages or get_pyproject_settings()
        if not manpages:
            raise DistutilsOptionError('\'manpages\' option is required')
        self.manpages_data = parse_manpages_spec(manpages)

        # if a value wasn't set in setup.cfg, use the value from setup.py
        for page, data in self.manpages_data.items():
            get_manpage_data_from_distribution(self.distribution, data)

    def run(self):
        for page, data in self.manpages_data.items():
            if data.get('manfile'):
                print ("using pre-written " + page)
                return
            print ("generating " + page)
            parser = get_parser(data['import_type'], data['import_from'], data['objname'], data['objtype'], data.get('prog', None))
            format = data.get('format', 'pretty')
            if format in ('pretty', 'single-commands-section'):
                manpage = Manpage(parser, format=format, _data=data)
                write_to_filename(str(manpage), page)
            elif format == 'old':
                # TODO: drop the "old" format support, and stop depending on ManPageWriter
                # pylint: disable=import-outside-toplevel
                from .build_manpage import ManPageWriter
                mw = ManPageWriter(parser, data)
                mw.write(page)
            else:
                raise ValueError("Unknown format: {}".format(format))


def get_build_py_cmd(command=build_py):
    """
    Override the default 'setup.py build_py' command with one that automatically
    generates manual pages.  By default we use an overridden
    'setuptools.command.build_py' (class).  If your project already uses an
    overridden class, specify the optional 'command=YourCommandClass`.
    """
    class _build_manpages_build_py(command):
        def run(self):
            self.run_command(DEFAULT_CMD_NAME)
            command.run(self)

    return _build_manpages_build_py


def get_install_cmd(command=install):
    """
    Override the default 'setup.py install' command with one that automatically
    installs the manual pages generated by `build_manpages`, see
    'build_manpages.get_build_py_cmd()'.  By default we use the
    'setuptools.command.install' class as the base.  If you already use an
    such an overridden class, set the optional 'command=YourCommandClass'.
    """
    class _build_manpages_install(command):
        def install_manual_pages(self):
            """
            Additional logic for installing the generated manual pages
            """
            config = ConfigParser()
            config.read('setup.cfg')
            try:
                spec = config.get(DEFAULT_CMD_NAME, 'manpages')
            except NoSectionError:
                spec = get_pyproject_settings()
            if spec is None:
                raise ValueError("'manpage' configuration not found in setup.cfg or pyproject.toml")

            data = parse_manpages_spec(spec)

            mandir = os.path.join(self.install_data, 'share/man/man1')
            if not os.path.exists(mandir):
                os.makedirs(mandir)
            for key, _ in data.items():
                print ('installing {0}'.format(key))
                shutil.copy(key, mandir)

        def run(self):
            command.run(self)
            self.install_manual_pages()

    return _build_manpages_install
