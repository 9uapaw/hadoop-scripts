import argparse
import os
import re

import sh
from typing import List
from zipfile import ZipFile
import requests

REVISION_RANGE_SEPARATOR = "-"
GERRIT_PATCHSET_SEPARATOR = "/"

PATCH_ZIP = "patch?zip"
COMMIT_MESSAGE_PREFIX = "Subject"
COMMIT_JIRA_REGEX = re.compile(".*?(YARN-\d+|HADOOP-\d+|MAPREDUCE-\d+).*")
PATH_PREFIX = "diff --git"
GITHUB_COMMIT_API = "https://api.github.com/repos/apache/hadoop/commits"
GITHUB_COMMIT_URL_TEMPLATE = "https://github.com/apache/hadoop/commit/{sha}.diff"
PATH_LIMIT = 20


def download_file(url) -> str or None:
    local_filename = url.split('/')[-1]
    write_mode = 'w'
    with requests.get(url) as r:
        content = r.text
        if 'zip' in local_filename:
            write_mode = 'wb'
            content = r.content

        if r.status_code != 200:
            return None

        with open(local_filename, write_mode) as f:
            f.write(content)

    return local_filename


def process(revision: str, max_change_num: int = None):
    revision: List[str] = revision.split("/")
    revision_no = revision[0]
    patch_set = revision[1]
    patchset_trial = range(max_change_num, 0, -1) if max_change_num else {patch_set}

    for patch in patchset_trial:
        print("Trying to download revision {} of Patchset {} ".format(revision_no, patch))
        patch_set = patch
        if download_gerrit_revision(patch, revision_no):
            break

    with ZipFile(PATCH_ZIP, 'r') as zip:
        gerrit_file = zip.filelist[0].filename
        zip.extractall()

    jira = ""
    os.remove(PATCH_ZIP)
    print("Extracting information from gerrit file {}".format(gerrit_file))
    paths = []

    with open(gerrit_file, 'r') as file:
        content = file.readlines()
        for line in content:
            if line.startswith(COMMIT_MESSAGE_PREFIX):
                jira = COMMIT_JIRA_REGEX.match(line).groups()[0]
            elif line.startswith(PATH_PREFIX):
                path = line.lstrip(PATH_PREFIX).split(" ")[0].lstrip("a/ ")
                if path:
                    paths.append(path)

    if len(paths) > PATH_LIMIT:
        paths = paths[:PATH_LIMIT]

    upstream_commit_candidates = requests.get(GITHUB_COMMIT_API, params={"path": paths}).json()
    upstream_commit = ""
    for commit in upstream_commit_candidates:
        if commit['commit']['message'].startswith(jira):
            upstream_commit = commit['sha']

    if upstream_commit:
        print("Found {} upstream commit: {}".format(jira, upstream_commit))
    else:
        return False

    print("Downloading upstream commit {}".format(upstream_commit))
    download_file(GITHUB_COMMIT_URL_TEMPLATE.format(sha=upstream_commit))
    html_name = f"{revision_no}-{patch_set}_{jira}"

    vim = sh.vim("-d", "-c", "TOhtml", "-c", "w! {}.html".format(html_name), "-c", "qa!", gerrit_file, "{}.diff".format(upstream_commit))

    os.remove(gerrit_file)
    os.remove("{}.diff".format(upstream_commit))

    print("Created diff HTML {}.html".format(html_name))
    # UNCOMMENT THIS TO PRINT THE COMMAND WAS RUNNING
    # print(vim.cmd)
    # print(vim.call_args)

    return True


def download_gerrit_revision(patch_set, revision_no) -> str or None:
    return download_file("https://gerrit.sjc.cloudera.com/changes/cdh%2Fhadoop~{revision}/revisions/{patch_set}/patch?zip".format(
        revision=revision_no, patch_set=patch_set))


def validate_revision(rev):
    if GERRIT_PATCHSET_SEPARATOR not in rev:
        raise ValueError("Invalid revision: '{}'. Must contain character '{}'".format(rev, GERRIT_PATCHSET_SEPARATOR))


if __name__ == "__main__":
    """
    Example usage: backport-diff-generator 140697/1
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("revision", nargs="+")
    parser.add_argument("--file")
    args = parser.parse_args()
    revisions = args.revision
    rev_copy = revisions.copy()
    max_change_num = None

    if args.file:
        with open(args.file, 'r') as f:
            revisions = f.readlines()

    for i, rev in enumerate(rev_copy):
        if REVISION_RANGE_SEPARATOR in rev:
            start_rev, end_rev = rev.split(REVISION_RANGE_SEPARATOR)
            validate_revision(start_rev)
            validate_revision(end_rev)

            start_change_num, start_patchset_num = map(int, start_rev.split(GERRIT_PATCHSET_SEPARATOR))
            end_change_num, end_patchset_num = map(int, end_rev.split(GERRIT_PATCHSET_SEPARATOR))
            max_change_num = max(start_patchset_num, end_patchset_num)
            revisions.remove(rev)
            converted_gerrit_revision = [f"{i}/{start_patchset_num}" for i in range(start_change_num, end_change_num + 1)]
            revisions.extend(converted_gerrit_revision)

    unsuccessful = []
    for rev in revisions:
        validate_revision(rev)
        if not process(rev, max_change_num):
            unsuccessful.append(rev)

    if unsuccessful:
        print("Unsuccessful revision comparison:")
        [print(rev) for rev in unsuccessful]
        exit(2)
    else:
        print("All revision comparison generation were successful")
        exit(0)
