#!/usr/bin/python
# vim:fileencoding=utf-8:et:ts=4:sw=4:sts=4
#
# Copyright (C) 2013 Intel Corporation <markus.lehtonen@linux.intel.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.
"""Script for bootstrapping and updating the unittest data"""

import argparse
from fnmatch import fnmatch
from glob import glob
import logging
import os
import shutil
import subprocess
import sys
import tempfile

LOG = logging.getLogger(os.path.basename(sys.argv[0]))
TEST_PKGS = {'gbp-test-native': {'build_branches': ['master']},
             'gbp-test-native2': {'build_branches': ['master']},
             'gbp-test': {'build_branches': ['master', 'fork']},
             'gbp-test2': {'build_branches': ['master']}}


class GitError(Exception):
    """Exception for git errors"""
    pass


def run_cmd(cmd, opts=None, capture_stdout=False):
    """Run command"""
    args = [cmd] + opts if opts else [cmd]
    stdout = subprocess.PIPE if capture_stdout else None
    LOG.debug("Running command: '%s'" % ' '.join(args))
    popen = subprocess.Popen(args, stdout=stdout)
    stdout, _stderr = popen.communicate()
    return (popen.returncode, stdout.splitlines() if stdout else stdout)

def git_cmd(cmd, opts=None, capture_stdout=False):
    """Run git command"""
    git_opts = [cmd] + opts if opts else [cmd]
    ret, stdout = run_cmd('git', git_opts, capture_stdout)
    if ret:
        raise GitError("Git cmd ('%s') failed!" % ('git ' + ' '.join(git_opts)))
    return stdout

def parse_args(argv=None):
    """Argument parser"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Verbose output")
    parser.add_argument('--overwrite', '-o', action='store_true',
                        help="Overwrite existing files")
    parser.add_argument('--update-branches', choices=['no', 'yes', 'force'],
                        default='no',
                        help="Update branches from remote")
    parser.add_argument('--no-build', action='store_true',
                        help="Do not build the packages")
    parser.add_argument('--keep-tmp', '-k', action='store_true',
                        help="Do not remote the temporary data dir")
    return parser.parse_args(argv)

def build_test_pkg(pkg_name, branch, outdir):
    """Build the test package and extract unit test data"""
    if branch == 'master':
        tag_pattern = 'srcdata/%s/release/*' % pkg_name
    else:
        tag_pattern = 'srcdata/%s/%s/release/*' % (pkg_name, branch)

    git_cmd('checkout', ['srcdata/%s/%s' % (pkg_name, branch)])
    # Check for hooks
    hooks = {}
    if os.path.exists('.bootstrap_hooks.py'):
        LOG.info('Loading bootstrap hooks')
        execfile('.bootstrap_hooks.py', hooks, hooks)
    tags = git_cmd('tag', ['-l', tag_pattern], True)
    for ind, tag in enumerate(tags):
        builddir = tempfile.mkdtemp(dir='.',
                                    prefix='build-%s-%s_' % (pkg_name, ind))
        gbp_opts =  ['--git-ignore-untracked','--git-export=%s' % tag,
                     '--git-export-dir=%s' % builddir]
        ret, out = run_cmd('git-buildpackage-rpm', gbp_opts, True)
        if ret:
            for line in out:
                print line
            raise Exception('Building %s / %s failed! Builddata can be found '
                            'in %s' % (pkg_name, tag, builddir))

        # Run postbuild_all hook
        if 'postbuild' in hooks:
            LOG.info('Running postbuild_all() hook for %s / %s' %
                        (pkg_name, tag))
            hooks['postbuild'](builddir, tag, LOG)

        # Create subdirs
        orig_dir = '%s/%s' % (outdir, 'orig')
        if not os.path.isdir(orig_dir):
            os.mkdir(orig_dir)

        for fname in glob('%s/SRPMS/*rpm' % builddir):
            LOG.debug('Copying %s -> %s' % (fname, outdir))
            shutil.copy(fname, outdir)
        for fname in os.listdir('%s/SOURCES' % builddir):
            if (fnmatch(fname, 'gbp*tar.gz') or fnmatch(fname, 'gbp*tar.bz2') or
                    fnmatch(fname, 'gbp*zip')):
                LOG.debug('Copying %s -> %s' % (fname, outdir))

                shutil.copy('%s/SOURCES/%s' % (builddir, fname), orig_dir)
        shutil.rmtree(builddir)

def update_pkg_branches(pkg_name, remote, force=False):
    """Update srcdata branches"""
    brs = git_cmd('branch', ['-r', '--list', '%s/srcdata/%s/*' %
                    (remote, pkg_name)], True)
    branches = [brn.strip().split()[0].replace(remote + '/', '') for brn in brs]
    LOG.info("Updating local branches %s from '%s'" % (branches, remote))

    for branch in branches:
        git_cmd('checkout', [branch])
        remote_branch = '%s/%s' % (remote, branch)
        try:
            git_cmd('merge', ['--ff-only', remote_branch], True)
        except GitError:
            if force:
                LOG.warning('Doing hard reset for branch %s' % branch)
                git_cmd('reset', ['--hard', remote_branch], True)
            else:
                raise Exception('Failed to do fast-forward on %s' % branch)

def update_from_remote(remote, force=False):
    """Update srcdata branches from remote repo"""
    git_cmd('fetch', [remote])
    for pkg in TEST_PKGS:
        update_pkg_branches(pkg, remote, force=force)


def main(argv=None):
    """The main routine"""
    LOG.addHandler(logging.StreamHandler())
    LOG.setLevel(logging.INFO)

    args = parse_args(argv)
    if args.verbose:
        LOG.setLevel(logging.DEBUG)

    outdatadir = tempfile.mkdtemp(prefix='gbp_unittest_outdata_')
    try:
        if args.update_branches != 'no':
            force = True if args.update_branches == 'force' else False
            update_from_remote('origin', force=force)
        if not args.no_build:
            for pkg, pkgconf in TEST_PKGS.iteritems():
                for branch in pkgconf['build_branches']:
                    build_test_pkg(pkg, branch, outdatadir)
            git_cmd('checkout', ['master'])

        for root, dirs, files in os.walk(outdatadir):
            relroot = os.path.relpath(root, outdatadir)
            for dname in dirs:
                relpath = '%s/%s' % (relroot, dname)
                if not os.path.isdir(relpath):
                    os.makedirs(relpath)
            for fname in files:
                relpath = '%s/%s' % (relroot, fname)
                if not os.path.exists(relpath) or args.overwrite:
                    shutil.copy('%s/%s' % (root, fname), relpath)
                else:
                    LOG.debug('Skipping %s' % relpath)
    finally:
        if args.keep_tmp:
            LOG.info('Sparing temporary directory: %s' % outdatadir)
        else:
            shutil.rmtree(outdatadir)
        git_cmd('checkout', ['master'])


if __name__ == '__main__':
    main()
