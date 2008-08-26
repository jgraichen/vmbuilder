#
#    Uncomplicated VM Builder
#    Copyright (C) 2007-2008 Canonical
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
#    Virtual disk management

from   VMBuilder.util import run_cmd 
import VMBuilder
import logging
import string
from   exception import VMBuilderUserError, VMBuilderException
import tempfile

TYPE_EXT2 = 0
TYPE_EXT3 = 1
TYPE_XFS = 2
TYPE_SWAP = 3

class Disk(object):
    def __init__(self, vm, size='5G', preallocated=False, filename=None):
        """size is passed to disk.parse_size

        preallocated means that the disk already exists and we shouldn't create it (useful for raw devices)

        filename can be given to force a certain filename or to give the name of the preallocated disk image"""

        # We need this for "introspection"
        self.vm = vm

        # Perhaps this should be the frontend's responsibility?
        self.size = parse_size(size)

        self.preallocated = preallocated

        # If filename isn't given, make one up
        if filename:
            self.filename = filename
        else:
            if self.preallocated:
                raise VMBuilderException('Preallocated was set, but no filename given')
            self.filename = 'disk%d.img' % len(self.vm.disks)

        self.partitions = []

    def devletters(self):
        """Returns the series of letters that ought to correspond to the device inside
        the VM. E.g. the first disk of a VM would return 'a', while the 702nd would return 'zz'"""
        return index_to_devname(self.vm.disks.index(self))

    def create(self, directory):
        """Creates the disk image (unless preallocated), partitions it, creates the partition mapping devices and mkfs's the partitions"""

        if not self.preallocated:
            if directory:
                self.filename = '%s/%s' % (directory, self.filename)
            logging.info('Creating disk image: %s' % self.filename)
            run_cmd('qemu-img', 'create', '-f', 'raw', self.filename, '%dM' % self.size)

        # From here, we assume that self.filename refers to whatever holds the disk image,
        # be it a file, a partition, logical volume, actual disk..

        logging.info('Adding partition table to disk image: %s' % self.filename)
        run_cmd('parted', '--script', self.filename, 'mklabel', 'msdos')

        # Partition the disk 
        for part in self.partitions:
            part.create(self)

        logging.info('Creating loop devices corresponding to the created partitions')
        kpartx_output = run_cmd('kpartx', '-av', self.filename)
        self.vm.add_clean_cb(lambda : self.unmap(ignore_fail=True))
        
        parts = kpartx_output.split('\n')[2:-1]
        mapdevs = []
        for line in parts:
            mapdevs.append(line.split(' ')[2])
        for (part, mapdev) in zip(self.partitions, mapdevs):
            part.mapdev = '/dev/mapper/%s' % mapdev

        # At this point, all partitions are created and their mapping device has been
        # created and set as .mapdev

        # Adds a filesystem to the partition
        logging.info("Creating file systems")
        for part in self.partitions:
            part.mkfs()

    def get_grub_id(self):
        """The name of the disk as known by grub"""
        return '(hd%d)' % self.get_index()

    def get_index(self):
        """Index of the disk (starting from 0)"""
        return self.vm.disks.index(self)

    def unmap(self, ignore_fail=False):
        """Destroy all mapping devices"""
        run_cmd('kpartx', '-d', self.filename, ignore_fail=ignore_fail)
        for part in self.partitions:
            self.mapdev = None

    def add_part(self, begin, length, type, mntpnt):
        """Add a partition to the disk. Sizes are given in megabytes"""
        end = begin+length-1
        for part in self.partitions:
            if (begin >= part.begin and begin <= part.end) or \
                (end >= part.begin and end <= part.end):
                raise Exception('Partitions are overlapping')
            if begin > end:
                raise Exception('Partition\'s last block is before its first')
            if begin < 0 or end > self.size:
                raise Exception('Partition is out of bounds. start=%d, end=%d, disksize=%d' % (begin,end,self.size))
        part = self.Partition(disk=self, begin=begin, end=end, type=str_to_type(type), mntpnt=mntpnt)
        self.partitions.append(part)

        # We always keep the partitions in order, so that the output from kpartx matches our understanding
        self.partitions.sort(cmp=lambda x,y: x.begin - y.begin)

    def convert(self, destination, format):
        """Converts disk image"""
        logging.info('Converting %s to %s, format %s' % (self.filename, format, destination))
        run_cmd('qemu-img', 'convert', '-O', format, self.filename, destination)

    class Partition(object):
        def __init__(self, disk, begin, end, type, mntpnt):
            self.disk = disk
            self.begin = begin
            self.end = end
            self.type = type
            self.mntpnt = mntpnt
            self.mapdev = None

        def parted_fstype(self):
            """Maps type_id to a fstype argument to parted"""
            return { TYPE_EXT2: 'ext2', TYPE_EXT3: 'ext2', TYPE_XFS: 'ext2', TYPE_SWAP: 'linux-swap' }[self.type]

        def create(self, disk):
            """Adds partition to the disk image (does not mkfs or anything like that)"""
            logging.info('Adding type %d partition to disk image: %s' % (self.type, disk.filename))
            run_cmd('parted', '--script', '--', disk.filename, 'mkpart', 'primary', self.parted_fstype(), self.begin, self.end)

        def mkfs(self):
            """Adds Filesystem object"""
            if not self.mapdev:
                raise Exception('We can\'t mkfs before we have a mapper device')
            self.fs = Filesystem(self.disk.vm, preallocated=True, filename=self.mapdev, type=self.type, mntpnt=self.mntpnt)
            self.fs.mkfs()

        def get_grub_id(self):
            """The name of the partition as known by grub"""
            return '(hd%d,%d)' % (self.disk.get_index(), self.get_index())

        def get_suffix(self):
            """Returns 'a4' for a device that would be called /dev/sda4 in the guest. 
               This allows other parts of VMBuilder to set the prefix to something suitable."""
            return '%s%d' % (self.disk.devletters(), self.get_index() + 1)

        def get_index(self):
            """Index of the disk (starting from 0)"""
            return self.disk.partitions.index(self)

class Filesystem(object):
    def __init__(self, vm, size=0, preallocated=False, type=None, mntpnt=None, filename=None):
        self.vm = vm
        self.filename = filename
        self.size = parse_size(size)
        self.preallocated = preallocated
           
        try:
            if int(type) == type:
                self.type = type
            else:
                self.type = str_to_type(type)
        except ValueError, e:
            self.type = str_to_type(type)

        self.mntpnt = mntpnt

    def create(self):
        logging.info('Creating filesystem')
        if not self.preallocated:
            logging.info('Not preallocated, so we create it.')
            if not self.filename:
                self.filename = tempfile.mktemp(dir=self.vm.workdir)
                logging.info('A name wasn\'t specified either, so we make one up: %s' % self.filename)
            run_cmd('qemu-img', 'create', '-f', 'raw', self.filename, '%dM' % self.size)
        self.mkfs()

    def mkfs(self):
        cmd = self.mkfs_fstype() + [self.filename]
        run_cmd(*cmd)
        self.uuid = run_cmd('vol_id', '--uuid', self.filename).rstrip()

    def mkfs_fstype(self):
        return { TYPE_EXT2: ['mkfs.ext2', '-F'], TYPE_EXT3: ['mkfs.ext3', '-F'], TYPE_XFS: ['mkfs.xfs'], TYPE_SWAP: ['mkswap'] }[self.type]

    def fstab_fstype(self):
        return { TYPE_EXT2: 'ext2', TYPE_EXT3: 'ext3', TYPE_XFS: 'xfs', TYPE_SWAP: 'swap' }[self.type]

    def fstab_options(self):
        return 'defaults'

def parse_size(size_str):
    """Takes a size like qemu-img would accept it and returns the size in MB"""
    try:
        return int(size_str)
    except ValueError, e:
        pass

    try:
        num = int(size_str[:-1])
    except ValueError, e:
        raise VMBuilderUserError("Invalid size: %s" % size_str)

    if size_str[-1:] == 'g' or size_str[-1:] == 'G':
        return num * 1024
    if size_str[-1:] == 'm' or size_str[-1:] == 'M':
        return num
    if size_str[-1:] == 'k' or size_str[-1:] == 'K':
        return num / 1024

def str_to_type(type):
    try:
        return { 'ext2': TYPE_EXT2,
                 'ext3': TYPE_EXT3,
                 'xfs': TYPE_XFS,
                 'swap': TYPE_SWAP,
                 'linux-swap': TYPE_SWAP }[type]
    except KeyError, e:
        raise Exception('Unknown partition type: %s' % type)

def bootpart(disks):
    """Returns the partition which contains /boot"""
    return path_to_partition(disks, '/boot/foo')

def path_to_partition(disks, path):
    parts = get_ordered_partitions(disks)
    parts.reverse()
    for part in parts:
        if path.startswith(part.mntpnt):
            return part
    raise VMBuilderException("Couldn't find partition path %s belongs to" % path)

def create_filesystems(vm):
    for filesystem in vm.filesystems:
        filesystem.create()

def create_partitions(vm):
    for disk in vm.disks:
        disk.create(vm.workdir)

def get_ordered_filesystems(vm):
    """Returns filesystems in an order suitable for mounting them"""
    fss = vm.filesystems
    for disk in vm.disks:
        fss += [part.fs for part in disk.partitions]
    fss.sort(lambda x,y: len(x.mntpnt or '')-len(y.mntpnt or ''))
    return fss

def get_ordered_partitions(disks):
    """Returns partitions from disks array in an order suitable for mounting them"""
    parts = []
    for disk in disks:
        parts += disk.partitions
    parts.sort(lambda x,y: len(x.mntpnt or '')-len(y.mntpnt or ''))
    return parts

def devname_to_index(devname):
    return devname_to_index_rec(devname) - 1

def devname_to_index_rec(devname):
    if not devname:
        return 0
    return 26 * devname_to_index_rec(devname[:-1]) + (string.ascii_lowercase.index(devname[-1]) + 1) 

def index_to_devname(index, suffix=''):
    if index < 0:
        return suffix
    return suffix + index_to_devname(index / 26 -1, string.ascii_lowercase[index % 26])