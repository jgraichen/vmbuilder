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
from VMBuilder import register_distro_plugin, Plugin

import logging
import os
import urllib2
import shutil
import json


class Chef(Plugin):
    """
    Plugin to install and bootstrap chef client, designed for ubuntu precise
    """
    name = 'chef plugin'

    arch_mapping = { 'amd64' : 'x86_64', 'i386' :'i686' }

    def register_options(self):
        group = self.setting_group('Chef')
        group.add_setting('install-chef', type='bool', default=False, help='Install chef-client on vm (via opscode package)')
        group.add_setting('chef-server-url', metavar='URL', help='URL to chef server')
        group.add_setting('validation-file', metavar='FILE', help='Path to validation.pem to register new chef node')
        group.add_setting('environment', metavar='ENV', help='Predefine chef node environment')
        group.add_setting('node-name', metavar='NAME', help='use custum name insteaf of fqdn as chef node name')
        group.add_setting('run-item', type='list', metavar='RUN', help='run-list item (recipe, role)')
        group.add_setting('attribute', type='list', metavar='DICT.KEY=VALUE', help='preset node attribute')

    def post_install(self):
        if not self.context.get_setting('install-chef'):
            return

        # downloading chef
        logging.info('Downloading chef')
        suiteStartPos = ord(self.context.get_setting('suite')[0])
        if self.context.get_setting('proxy'):
            opener = urllib2.build_opener(urllib2.ProxyHandler({'http': self.context.get_setting('proxy')}))
        else:
            opener = urllib2.build_opener()
        f = opener.open('http://www.opscode.com/chef/download?m={arch}&p={platform}&pv={version}'.format(
            arch=self.arch_mapping[self.context.get_setting('arch')],
            platform='ubuntu',
            version=str(suiteStartPos / 2 - 44) + '.' + ('04' if ( suiteStartPos % 2 == 0 ) else '10' )))
        with open(self.context.chroot_dir + '/tmp/chef.deb', 'wb') as fp:
            shutil.copyfileobj(f, fp)

        # install chef
        logging.info('Installing chef')
        self.context.suite.run_in_target('dpkg', '-i', '/tmp/chef.deb')

        # configure chef
        self.context.install_file('/etc/chef/validation.pem', source=self.context.get_setting('validation-file'), mode=0700)
        self.install_from_template('/etc/chef/client.rb', 'client.rb', {
            'node_name': self.context.get_setting('node-name'),
            'chef_server_url': self.context.get_setting('chef-server-url')
        })

        # prepare first/auto start of chef-client
        options = self._parse_options(self.context.get_setting('attribute'))
        options['run_list'] = self.context.get_setting('run-item')
        self.install_file('/etc/chef/first-boot.json', contents=json.dumps(options))
        self.install_from_template('/etc/init/chef-setup.conf', 'first-start.conf',
            { 'environment': self.context.get_setting('environment') }, mode=0755)
        logging.info('Chef configured')

    @staticmethod
    def _parse_options(lines):
        options = {}
        for line in lines:
            option, value = line.split('=', 1)
            groups = option.split('.')
            name = groups.pop()
            current_group = options
            for group in groups:
                if group not in current_group or type(current_group[group]) is not dict:
                    current_group[group] = {}
                current_group = current_group[group]
            current_group[name] = value
        return options

register_distro_plugin(Chef)
