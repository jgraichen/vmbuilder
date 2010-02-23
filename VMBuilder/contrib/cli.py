#    Uncomplicated VM Builder
#    Copyright (C) 2007-2009 Canonical Ltd.
#    
#    See AUTHORS for list of contributors
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    CLI plugin
import logging
import optparse
import os
import pwd
import sys
import VMBuilder
import VMBuilder.util as util
from   VMBuilder.disk import parse_size
import VMBuilder.hypervisor

class CLI(object):
    arg = 'cli'
       
    def main(self):
        optparser = optparse.OptionParser()

        self.set_usage(optparser)

        optparser.add_option('--version', action='callback', callback=self.versioninfo, help='Show version information')

        group = optparse.OptionGroup(optparser, 'Build options')
        group.add_option('--debug', action='callback', callback=self.set_verbosity, help='Show debug information')
        group.add_option('--verbose', '-v', action='callback', callback=self.set_verbosity, help='Show progress information')
        group.add_option('--quiet', '-q', action='callback', callback=self.set_verbosity, help='Silent operation')
        group.add_option('--config', '-c', type='str', help='Configuration file')
        group.add_option('--destdir', '-d', type='str', help='Destination directory')
        group.add_option('--only-chroot', action='store_true', help="Only build the chroot. Don't install it on disk images or anything.")
        group.add_option('--existing-chroot', help="Use existing chroot.")
        optparser.add_option_group(group)

        group = optparse.OptionGroup(optparser, 'Disk')
        group.add_option('--rootsize', metavar='SIZE', default=4096, help='Size (in MB) of the root filesystem [default: %default]')
        group.add_option('--optsize', metavar='SIZE', default=0, help='Size (in MB) of the /opt filesystem. If not set, no /opt filesystem will be added.')
        group.add_option('--swapsize', metavar='SIZE', default=1024, help='Size (in MB) of the swap partition [default: %default]')
        group.add_option('--raw', metavar='PATH', type='str', help="Specify a file (or block device) to as first disk image.")
        group.add_option('--part', metavar='PATH', type='str', help="Allows to specify a partition table in PATH each line of partfile should specify (root first): \n    mountpoint size \none per line, separated by space, where size is in megabytes. You can have up to 4 virtual disks, a new disk starts on a line containing only '---'. ie: \n    root 2000 \n    /boot 512 \n    swap 1000 \n    --- \n    /var 8000 \n    /var/log 2000")
        optparser.add_option_group(group)
        
        distro_name = sys.argv[2]
        distro_class = VMBuilder.get_distro(distro_name)
        distro = distro_class()
        self.add_settings_from_context(optparser, distro)

        hypervisor_name = sys.argv[1]
        hypervisor_class = VMBuilder.get_hypervisor(hypervisor_name)
        hypervisor = hypervisor_class(distro)
        hypervisor.register_hook('fix_ownership', self.fix_ownership)
        self.add_settings_from_context(optparser, hypervisor)

        config_files = ['/etc/vmbuilder.cfg', os.path.expanduser('~/.vmbuilder.cfg')]
        (self.options, args) = optparser.parse_args(sys.argv[2:])

        if self.options.config:
            config_files.append(self.options.config)
        util.apply_config_files_to_context(config_files, distro)
        util.apply_config_files_to_context(config_files, hypervisor)

        for option in dir(self.options):
            if option.startswith('_') or option in ['ensure_value', 'read_module', 'read_file']:
                continue
            val = getattr(self.options, option)
            if val:
                if distro.has_setting(option):
                    distro.set_setting(option, val)
                elif hypervisor.has_setting(option):
                    hypervisor.set_setting(option, val)
        
        if self.options.existing_chroot:
            distro.set_chroot_dir(self.options.existing_chroot)
            distro.call_hooks('preflight_check')
        else:
            chroot_dir = util.tmpdir()
            distro.set_chroot_dir(chroot_dir)
            distro.build_chroot()

        if self.options.only_chroot:
            print 'Chroot can be found in %s' % distro.chroot_dir
            sys.exit(0)

        self.set_disk_layout(hypervisor)
        hypervisor.install_os()

        destdir = self.options.destdir or ('%s-%s' % (distro_name, hypervisor_name))
        os.mkdir(destdir)
        self.fix_ownership(destdir)
        hypervisor.finalise(destdir)
        sys.exit(0)

    def fix_ownership(self, filename):
        """
        Change ownership of file to $SUDO_USER.

        @type  path: string
        @param path: file or directory to give to $SUDO_USER
        """
        if 'SUDO_USER' in os.environ:
            logging.debug('Changing ownership of %s to %s' % (filename, os.environ['SUDO_USER']))
            (uid, gid) = pwd.getpwnam(os.environ['SUDO_USER'])[2:4]
            os.chown(filename, uid, gid)

    def add_settings_from_context(self, optparser, context):
        setting_groups = set([setting.setting_group for setting in context._config.values()])
        for setting_group in setting_groups:
            optgroup = optparse.OptionGroup(optparser, setting_group.name)
            for setting in setting_group._settings:
                args = ['--%s' % setting.name]
                args += setting.extra_args
                kwargs = {}
                if setting.help:
                    kwargs['help'] = setting.help
                    if len(setting.extra_args) > 0:
                        setting.help += " Config option: %s" % setting.name
                if setting.metavar:
                    kwargs['metavar'] = setting.metavar
                if setting.get_default():
                    kwargs['default'] = setting.get_default()
                if type(setting) == VMBuilder.plugins.Plugin.BooleanSetting:
                    kwargs['action'] = 'store_true'
                if type(setting) == VMBuilder.plugins.Plugin.ListSetting:
                    kwargs['action'] = 'append'
                optgroup.add_option(*args, **kwargs)
            optparser.add_option_group(optgroup)

    def versioninfo(self, option, opt, value, parser):
        print '%(major)d.%(minor)d.%(micro)s.r%(revno)d' % VMBuilder.get_version_info()
        sys.exit(0)

    def set_usage(self, optparser):
        optparser.set_usage('%prog hypervisor distro [options]')
#        optparser.arg_help = (('hypervisor', vm.hypervisor_help), ('distro', vm.distro_help))

    def handle_args(self, vm, args):
        if len(args) < 2:
            vm.optparser.error("You need to specify at least the hypervisor type and the distro")
        self.hypervisor = vm.get_hypervisor(args[0])
        self.distro = distro.vm.get_distro(args[1])

    def set_verbosity(self, option, opt_str, value, parser):
        if opt_str == '--debug':
            VMBuilder.set_console_loglevel(logging.DEBUG)
        elif opt_str == '--verbose':
            VMBuilder.set_console_loglevel(logging.INFO)
        elif opt_str == '--quiet':
            VMBuilder.set_console_loglevel(logging.CRITICAL)

    def set_disk_layout(self, hypervisor):
        default_filesystem = hypervisor.distro.preferred_filesystem()
        if not self.options.part:
            rootsize = parse_size(self.options.rootsize)
            swapsize = parse_size(self.options.swapsize)
            optsize = parse_size(self.options.optsize)
            if hypervisor.preferred_storage == VMBuilder.hypervisor.STORAGE_FS_IMAGE:
                hypervisor.add_filesystem(size='%dM' % rootsize, type='ext3', mntpnt='/')
                hypervisor.add_filesystem(size='%dM' % swapsize, type='swap', mntpnt=None)
                if optsize > 0:
                    hypervisor.add_filesystem(size='%dM' % optsize, type='ext3', mntpnt='/opt')
            else:
                if self.options.raw:
                    disk = hypervisor.add_disk(filename=self.options.raw, preallocated=True)
                else:
                    size = rootsize + swapsize + optsize
                    tmpfile = util.tmpfile(keep=False)
                    disk = hypervisor.add_disk(tmpfile, size='%dM' % size)
                offset = 0
                disk.add_part(offset, rootsize, default_filesystem, '/')
                offset += rootsize
                disk.add_part(offset, swapsize, 'swap', 'swap')
                offset += swapsize
                if optsize > 0:
                    disk.add_part(offset, optsize, default_filesystem, '/opt')
        else:
            # We need to parse the file specified
            if vm.hypervisor.preferred_storage == VMBuilder.hypervisor.STORAGE_FS_IMAGE:
                try:
                    for line in file(self.options.part):
                        elements = line.strip().split(' ')
                        if elements[0] == 'root':
                            vm.add_filesystem(elements[1], default_filesystem, mntpnt='/')
                        elif elements[0] == 'swap':
                            vm.add_filesystem(elements[1], type='swap', mntpnt=None)
                        elif elements[0] == '---':
                            # We just ignore the user's attempt to specify multiple disks
                            pass
                        elif len(elements) == 3:
                            vm.add_filesystem(elements[1], type=default_filesystem, mntpnt=elements[0], devletter='', device=elements[2], dummy=(int(elements[1]) == 0))
                        else:
                            vm.add_filesystem(elements[1], type=default_filesystem, mntpnt=elements[0])

                except IOError, (errno, strerror):
                    vm.optparser.error("%s parsing --part option: %s" % (errno, strerror))
            else:
                try:
                    curdisk = list()
                    size = 0
                    for line in file(part):
                        pair = line.strip().split(' ',1) 
                        if pair[0] == '---':
                            self.do_disk(vm, curdisk, size)
                            curdisk = list()
                            size = 0
                        elif pair[0] != '':
                            logging.debug("part: %s, size: %d" % (pair[0], int(pair[1])))
                            curdisk.append((pair[0], pair[1]))
                            size += int(pair[1])

                    self.do_disk(vm, curdisk, size)

                except IOError, (errno, strerror):
                    vm.optparser.error("%s parsing --part option: %s" % (errno, strerror))
    
    def do_disk(self, hypervisor, curdisk, size):
        default_filesystem = hypervisor.distro.preferred_filesystem()
        disk = hypervisor.add_disk(size+1)
        logging.debug("do_disk - size: %d" % size)
        offset = 0
        for pair in curdisk:
            logging.debug("do_disk - part: %s, size: %s, offset: %d" % (pair[0], pair[1], offset))
            if pair[0] == 'root':
                disk.add_part(offset, int(pair[1]), default_filesystem, '/')
            elif pair[0] == 'swap':
                disk.add_part(offset, int(pair[1]), pair[0], pair[0])
            else:
                disk.add_part(offset, int(pair[1]), default_filesystem, pair[0])
            offset += int(pair[1])

class UVB(CLI):
    arg = 'ubuntu-vm-builder'

    def set_usage(self, vm):
        optparser.set_usage('%prog hypervisor suite [options]')
        optparser.arg_help = (('hypervisor', vm.hypervisor_help), ('suite', self.suite_help))

    def suite_help(self):
        return 'Suite. Valid options: %s' % " ".join(VMBuilder.plugins.ubuntu.distro.Ubuntu.suites)

    def handle_args(self, vm, args):
        if len(args) < 2:
            vm.optparser.error("You need to specify at least the hypervisor type and the suite")
        vm.set_hypervisor(args[0])
        vm.set_distro('ubuntu')
        vm.suite = args[1]