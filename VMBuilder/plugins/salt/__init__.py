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
import io
import yaml
from urllib import urlencode
import urllib2
import tarfile


class Salt(Plugin):
    """
    Plugin to install and bootstrap salt minion, designed for ubuntu trusty
    """
    name = 'salt plugin'

    def register_options(self):
        group = self.setting_group('Salt Minion')
        group.add_setting('salt-minion-install', type='bool', default=False, help='Install salt-minion on vm')
        group.add_setting('salt-api-url', metavar='URL', help='URL for salt-api to generate salt-keys')
        group.add_setting('salt-api-user', metavar='USER', help='username for salt-api')
        group.add_setting('salt-api-passwd', metavar='PASSWORD', help='password for salt-api')
        group.add_setting('salt-minion-id', metavar='NAME', help='designed minion id')
        group.add_setting('salt-master', metavar='master', type='list', help='salt master addresses')

    def post_install(self):
        if not self.context.get_setting('salt-minion-install'):
            return

        # install salt-minion
        logging.info('Installing salt-minion')
        self.context.suite.prevent_daemons_starting()
        self.context.suite.run_in_target('apt-get', '--force-yes', '-y', 'install', 'salt-minion')
        self.context.suite.unprevent_daemons_starting()

        # configure salt-minion
        logging.info('Configuring salt-minion')
        options = {
            'id': self.context.get_setting('salt-minion-id'),
            'master': self.context.get_setting('salt-master')
        }
        self.install_file('/etc/salt/minion.d/vmbuilder.conf', contents=yaml.dump(options))

        # generate salt minion key
        logging.info('Generate salt-minion key')
        minionpkidir = self.context.chroot_dir + '/etc/salt/pki/minion'
        os.makedirs(minionpkidir)
        os.chmod(minionpkidir, 0o700)
        keystar = self.generate_salt_key()
        tar = tarfile.open(fileobj=io.BytesIO(keystar))
        tar.extractall(path=minionpkidir)
        os.chmod(minionpkidir + '/minion.pem', 0o600)
        logging.info('Salt-minion installed and configured')

    def generate_salt_key(self):
        if self.context.get_setting('proxy'):
            opener = urllib2.build_opener(urllib2.ProxyHandler({'http': self.context.get_setting('proxy')}))
        else:
            opener = urllib2.build_opener()
        data = urlencode({
            'mid': self.context.get_setting('salt-minion-id'),
            'username': self.context.get_setting('salt-api-user'),
            'password': self.context.get_setting('salt-api-passwd'),
            'eauth': 'pam'
        }).encode('utf-8')

        print(self.context.get_setting('salt-api-url') + '/keys')
        print(data)
        response = opener.open(self.context.get_setting('salt-api-url') + '/keys', data)
        return response.read()

register_distro_plugin(Salt)
