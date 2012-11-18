#
#    Uncomplicated VM Builder
#    Copyright (C) 2007-2010 Canonical Ltd.
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
from VMBuilder import register_distro_plugin, Plugin, VMBuilderUserError

import logging
import os
import urllib

class Chef(Plugin):
    """
    Plugin to install and bootstrap chef client, designed for ubuntu precise
    """
    name = 'chef plugin'

    def register_options(self):
        group = self.setting_group('Chef')
        group.add_setting('install-chef', type='bool', default=False, help='Install chef-client on vm (via opscode-ppa)')
        group.add_setting('chef-server-url', metavar='URL', help='URL to chef server')
        group.add_setting('validation-file', metavar='FILE', help='Path to validation.pem to register new chef node')
        group.add_setting('node-name', metavar='NAME', help='use custum name insteaf of fqdn as chef node name')
        group.add_setting('run-item', type='list', metavar='RUN', help='run-list item (recipe, role)')

    def post_install(self):
        if not self.context.get_setting('install-chef'):
            return

        # install chef
        self.install_from_template('/etc/apt/sources.list.d/opscode.list', 'opscode-source', { 'suite': self.context.get_setting('suite') })
        self.context.suite.run_in_target('debconf-set-selections', stdin='chef chef/chef_server_url string ' + self.context.get_setting('chef-server-url'), env={ 'DEBIAN_FRONTEND' : 'noninteractive' })
        self.context.suite.run_in_target('apt-key', 'add', '-', stdin=urllib.urlopen('http://apt.opscode.com/packages@opscode.com.gpg.key').read())
        self.context.suite.run_in_target('apt-get', 'update')
        self.context.install_file('/usr/sbin/policy-rc.d', contents="#!/bin/sh\nexit 101", mode=755)
        self.context.suite.run_in_target('apt-get', '--force-yes', '-y', 'install', 'chef', 'opscode-keyring', env={ 'DEBIAN_FRONTEND' : 'noninteractive' })
        self.context.suite.run_in_target('rm', '/usr/sbin/policy-rc.d')

        # configure chef
        self.context.install_file('/etc/chef/validation.pem', source=self.context.get_setting('validation-file'), mode=0700)
        self.install_from_template('/etc/chef/client.rb', 'client.rb', {
            'node_name': self.context.get_setting('node-name'),
            'chef_server_url': self.context.get_setting('chef-server-url')
        })
        self.install_from_template('/etc/chef/first-boot.json', 'first-boot.json', {'run_list': self.context.get_setting('run-item') })

register_distro_plugin(Chef)
