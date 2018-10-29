#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Author: Niccolò Bonacchi
# @Date:   2018-06-08 11:04:05
# @Last Modified by:   Niccolò Bonacchi
# @Last Modified time: 2018-07-12 17:10:22
"""
Usage:
    update.py
        Will fetch changes from origin. Nothing is updated yet!
        Calling update.py will display information on the available versions
    update.py -h | --help | ?
        Displays this docstring.
    update.py <version>
        Will backup pybpod_projects folder where local configurations live.
        Will checkout the <version> release, update the submodules, and restore
        the pybpod_projects folder from backup.
    update.py tasks
        Will checkout any task file not present in the local tasks folder.
    update.py tasks <branch>
        Will checkout any task file from <branch> not present in local folder.
    update.py update
        Will update itself to the latest revision on master.
    update.py update <branch>
        Will update itself to the latest revision on <branch>.
    update.py reinstall
        Will reinstall the rig to the latest revision on master.

"""
import subprocess
import sys
import os
import shutil
from pathlib import Path


def get_versions():
    vers = subprocess.check_output(["git", "ls-remote",
                                    "--tags", "origin"]).decode().split()
    vers = [x for x in vers[1::2] if '{' not in x]
    vers = [x.split('/')[-1] for x in vers]
    available = [x for x in vers if x >= '1.1.5']
    print("\nAvailable versions: {}\n".format(available))
    return vers


def get_branches():
    branches = subprocess.check_output(["git", "ls-remote",
                                        "--heads", "origin"]).decode().split()
    branches = [x.split('heads')[-1] for x in branches[1::2]]
    branches = [x[1:] for x in branches]
    print("\nAvailable branches: {}\n".format(branches))

    return branches


def get_current_version():
    tag = subprocess.check_output(["git", "tag",
                                   "--points-at", "HEAD"]).decode().strip()
    print("\nCurrent version: {}".format(tag))
    return tag


def submodule_update():
    print("Running: git submodule update")
    subprocess.call(['git', 'submodule', 'update'])


def pull():
    subprocess.call(['git', 'pull', 'origin', 'master'])
    submodule_update()


def pybpod_projects_path():
    return os.path.join(os.getcwd(), 'pybpod_projects')


def backup_pybpod_projects(filename='pybpod_projects.bk'):
    print("Backing up current pybpod_projects configuration")
    src = pybpod_projects_path()
    dst = os.path.join(os.path.expanduser('~'), filename)
    if os.path.exists(dst):
        if not str.isdigit(dst[-1]):
            dst = dst + '0'
        else:
            dst = dst + str(int(dst[-1]) + 1)
    shutil.copytree(src, dst,
                    ignore=shutil.ignore_patterns('sessions'))


def restore_pybpod_projects_from_backup():
    print("Restoring pybpod_projects")
    src = os.path.join(os.path.expanduser('~'), 'pybpod_projects.bk')
    dst = os.getcwd()
    shutil.rmtree(os.path.join(os.getcwd(), 'pybpod_projects'))
    shutil.move(src, dst)
    os.rename(os.path.join(os.getcwd(), 'pybpod_projects.bk'),
              pybpod_projects_path())


def get_tasks(branch='master', only_missing=True):
    print("Checking for new tasks on {}:".format(branch))
    local_tasks_dir = os.path.join(
        os.getcwd(), 'pybpod_projects', 'IBL', 'tasks')

    ltp = Path(local_tasks_dir)
    local_tasks = [str(x).split(os.sep)[-1]
                   for x in ltp.glob('*') if x.is_dir()]

    subprocess.call("git fetch".split())
    all_files = subprocess.check_output(
        "git ls-tree -r --name-only origin/{}".format(
            branch).split()).decode().split('\n')

    remote_task_files = [x for x in all_files if 'tasks' in x]

    found_files = []
    for lt in local_tasks:
        found_files.extend([x for x in remote_task_files if lt in x])

    if only_missing:
        missing_files = list(set(remote_task_files) - set(found_files))
        # Remove tasks.json file
        missing_files = [x for x in missing_files if "tasks.json" not in x]
        print("Found {} new files:".format(len(missing_files)), missing_files)
        return missing_files
    else:
        return found_files


def checkout_missing_task_files(missing_files, branch='master'):
    for file in missing_files:
        subprocess.call("git checkout origin/{} -- {}".format(branch,
                                                              file).split())
        print("Checked out:", file)


def checkout_single_file(file=None, branch='master'):
    subprocess.call("git checkout origin/{} -- {}".format(branch,
                                                          file).split())

    print("Checked out", file, "from branch", branch)

def checkout_version(ver):
    print("\nChecking out {}".format(ver))
    subprocess.call(['git', 'stash'])
    subprocess.call(['git', 'checkout', 'tags/' + ver])
    submodule_update()


def pop_stash():
    print("\nPopping stash")
    subprocess.call(['git', 'stash', 'pop'])


def update_remotes():
    subprocess.call(['git', 'remote', 'update'])


def branch_info():
    print("Current availiable branches:")
    print(subprocess.check_output(["git", "branch", "-avv"]).decode())


def info():
    update_remotes()
    # branch_info()
    ver = get_current_version()
    versions = get_versions()
    if not ver:
        print("WARNING: You appear to be on an untagged release.",
              "\n         Try updating to a specific version")
        print()
    else:
        idx = sorted(versions).index(ver) if ver in versions else None
        if idx + 1 == len(versions):
            print("\nThe version you have checked out is the latest version\n")
        else:
            print("Newest version |{}| type:\n\npython update.py {}\n".format(
                sorted(versions)[-1], sorted(versions)[-1]))


if __name__ == '__main__':
    # TODO: Use argparse!!
    # If called alone
    if len(sys.argv) == 1:
        info()
    # If called with something in front
    elif len(sys.argv) == 2:
        versions = get_versions()
        help_args = ['-h', '--help', '?']
        # HELP
        if sys.argv[1] in help_args:
            print(__doc__)
        # UPDATE TO VERSION
        elif sys.argv[1] in versions:
            backup_pybpod_projects()
            checkout_version(sys.argv[1])
            # restore_pybpod_projects_from_backup()
            task_files = get_tasks(branch='master', only_missing=False)
            checkout_missing_task_files(task_files, branch='master')
            pop_stash()
        # UPDATE TASKS
        elif sys.argv[1] == 'tasks':
            task_files = get_tasks(branch='master', only_missing=False)
            checkout_missing_task_files(task_files, branch='master')
        # UPDATE UPDATE
        elif sys.argv[1] == 'update':
            checkout_single_file(file='update.py', branch='master')
        elif sys.argv[1] == 'reinstall':
            subprocess.call(['python', 'install.py'])
        # UNKNOWN COMMANDS
        else:
            print("ERROR:", sys.argv[1],
                  "is not a  valid command or version number.")
            raise ValueError
    # If called with something in front of something in front :P
    elif len(sys.argv) == 3:
        branches = get_branches()
        commands = ['tasks', 'update']
        # Command checks
        if sys.argv[1] not in commands:
            print("ERROR:", "Unknown command...")
            raise ValueError
        if sys.argv[2] not in branches:
            print("ERROR:", sys.argv[2], "is not a valid branch.")
            raise ValueError
        # Commands
        if sys.argv[1] == 'tasks' and sys.argv[2] in branches:
            task_files = get_tasks(branch=sys.argv[2], only_missing=False)
            checkout_missing_task_files(task_files, branch=sys.argv[2])
        if sys.argv[1] == 'update' and sys.argv[2] in branches:
            checkout_single_file(file='update.py', branch=sys.argv[2])
    print("\n")
