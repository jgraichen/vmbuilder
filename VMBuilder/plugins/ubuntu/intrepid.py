#
#    Uncomplicated VM Builder
#    Copyright (C) 2007-2008 Canonical Ltd.
#    
#    See AUTHORS for list of contributors
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import suite
import logging
import VMBuilder.disk as disk
from   VMBuilder.util import run_cmd
from   VMBuilder.plugins.ubuntu.hardy import Hardy

class Intrepid(Hardy):
    valid_flavours = { 'i386' :  ['386', 'generic', 'server', 'virtual'],
                       'amd64' : ['generic', 'server', 'virtual'],
                       'lpia'  : ['lpia', 'lpiacompat'] }
    default_flavour = { 'i386' : 'virtual', 'amd64' : 'virtual', 'lpia' : 'lpia' }
    xen_kernel_flavour = 'virtual'
    ec2_kernel_info = { 'i386' : 'aki-714daa18', 'amd64' : 'aki-4f4daa26' }
    ec2_ramdisk_info = { 'i386': 'ari-7e4daa17', 'amd64' : 'ari-4c4daa25' }

    def install_ec2(self):
        if not self.vm.ec2:
            return False

        if not self.vm.addpkg:
            self.vm.addpkg = []

        self.vm.addpkg += ['policykit', '^server']
        self.install_from_template('/etc/update-motd.d/51_update-motd', '51_update-motd')
        self.run_in_target('chmod', '755', '/etc/update-motd.d/51_update-motd')

    def mangle_grub_menu_lst(self):
        bootdev = disk.bootpart(self.vm.disks)
        run_cmd('sed', '-ie', 's/^# kopt=root=\([^ ]*\)\(.*\)/# kopt=root=UUID=%s\\2/g' % bootdev.fs.uuid, '%s/boot/grub/menu.lst' % self.destdir)
        run_cmd('sed', '-ie', 's/^# groot.*/# groot=%s/g' % bootdev.fs.uuid, '%s/boot/grub/menu.lst' % self.destdir)
        run_cmd('sed', '-ie', '/^# kopt_2_6/ d', '%s/boot/grub/menu.lst' % self.destdir)
